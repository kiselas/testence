"""The versioned contracts that close plan → evidence → verdict."""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path
from types import SimpleNamespace

import pytest

from testence.cli import main
from testence.contracts import PLAN_SCHEMA, VERDICT_SCHEMA, load_plan, load_verdict
from testence.contracts._validation import ContractError
from testence.export._model import LoadedRun
from testence.pytest_plugin import _resolve_contract


def _plan_document(*, claim_id: str = "blocker.create.persisted") -> dict:
    return {
        "schema": PLAN_SCHEMA,
        "id": "release-board.create-blocker",
        "title": "Create a release blocker",
        "source": "DemoSpec",
        "claims": [
            {
                "id": claim_id,
                "statement": "The new blocker exists in authoritative storage.",
                "oracles": ["api"],
                "required": True,
            }
        ],
        "scenarios": [
            {
                "id": "create-blocker",
                "title": "Create one blocker",
                "claims": [claim_id],
                "risk": "false green from optimistic UI",
            }
        ],
    }


def _write_plan(path: Path, document: dict | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(document or _plan_document(), ensure_ascii=False, indent=2)
    path.write_text(
        f"# Create blocker\n\n```testence-planspec\n{body}\n```\n",
        encoding="utf-8",
    )
    return path


def _verdict_document() -> dict:
    return {
        "schema": VERDICT_SCHEMA,
        "plan_id": "release-board.create-blocker",
        "test_id": "test_create_blocker",
        "verdict": "real_bug",
        "confidence": 0.98,
        "summary": "The UI acknowledged the blocker, but the API could not read it.",
        "claim_results": [
            {
                "claim_id": "blocker.create.persisted",
                "status": "failed",
                "reason": "The authoritative read returned no blocker.",
                "evidence": ["oracle.json#/0", "network.jsonl"],
            }
        ],
        "blocked_on": [],
    }


def _write_pack(path: Path) -> Path:
    path.mkdir(parents=True)
    (path / "pack.json").write_text(
        json.dumps(
            {
                "test": "test_create_blocker",
                "plan": {
                    "schema": PLAN_SCHEMA,
                    "id": "release-board.create-blocker",
                    "path": "specs/create-blocker.md",
                },
                "claims": ["blocker.create.persisted"],
            }
        ),
        encoding="utf-8",
    )
    (path / "oracle.json").write_text('[{"field":"id"}]', encoding="utf-8")
    (path / "network.jsonl").write_text('{"status":404}\n', encoding="utf-8")
    return path


def test_markdown_planspec_is_strict_and_human_readable(tmp_path):
    path = _write_plan(tmp_path / "specs" / "create-blocker.md")
    plan = load_plan(path)

    assert plan.id == "release-board.create-blocker"
    assert plan.claim_ids == ("blocker.create.persisted",)
    assert plan.scenarios[0].claims == plan.claim_ids
    assert plan.summary()["valid"] is True


def test_planspec_rejects_unknown_claims_and_uncovered_required_claims(tmp_path):
    document = _plan_document()
    document["scenarios"][0]["claims"] = ["blocker.create.visible"]
    path = _write_plan(tmp_path / "bad.md", document)

    with pytest.raises(ContractError, match="unknown claim"):
        load_plan(path)


def test_planspec_requires_exactly_one_machine_block(tmp_path):
    path = tmp_path / "empty.md"
    path.write_text("# prose only\n", encoding="utf-8")
    with pytest.raises(ContractError, match="exactly one"):
        load_plan(path)


def test_pytest_marker_resolves_and_validates_claims(tmp_path):
    _write_plan(tmp_path / "specs" / "create-blocker.md")
    marker = pytest.mark.testence(
        plan="specs/create-blocker.md", claims=["blocker.create.persisted"]
    ).mark
    item = SimpleNamespace(get_closest_marker=lambda name: marker if name == "testence" else None)

    binding = _resolve_contract(item, tmp_path)

    assert binding is not None
    assert binding.plan.id == "release-board.create-blocker"
    assert binding.path == "specs/create-blocker.md"
    assert binding.claims == ("blocker.create.persisted",)


def test_pytest_marker_rejects_paths_outside_repository(tmp_path):
    marker = pytest.mark.testence(plan="../outside.md", claims=["claim.one"]).mark
    item = SimpleNamespace(get_closest_marker=lambda _name: marker)
    with pytest.raises(ContractError, match="inside the repository"):
        _resolve_contract(item, tmp_path)


def test_verdict_is_checked_against_plan_pack_claims_and_evidence(tmp_path):
    plan = load_plan(_write_plan(tmp_path / "specs" / "create-blocker.md"))
    pack = _write_pack(tmp_path / "pack")
    verdict_path = pack / "verdict.json"
    verdict_path.write_text(json.dumps(_verdict_document()), encoding="utf-8")

    verdict = load_verdict(verdict_path, pack_dir=pack, plan=plan)

    assert verdict.verdict == "real_bug"
    assert verdict.claim_ids == ("blocker.create.persisted",)
    assert verdict.summary_document()["claims"] == {"blocker.create.persisted": "failed"}


def test_verdict_rejects_missing_or_unsafe_evidence(tmp_path):
    pack = _write_pack(tmp_path / "pack")
    document = _verdict_document()
    document["claim_results"][0]["evidence"] = ["../secret.txt"]
    path = tmp_path / "verdict.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ContractError, match="unsafe evidence"):
        load_verdict(path, pack_dir=pack)

    document["claim_results"][0]["evidence"] = ["missing.json"]
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ContractError, match="does not exist"):
        load_verdict(path, pack_dir=pack)


def test_verdict_rejects_a_legacy_pack_without_proof_binding(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / "pack.json").write_text(json.dumps({"test": "test_create_blocker"}), encoding="utf-8")
    (pack / "oracle.json").write_text("[]", encoding="utf-8")
    (pack / "network.jsonl").write_text("", encoding="utf-8")
    path = pack / "verdict.json"
    path.write_text(json.dumps(_verdict_document()), encoding="utf-8")

    with pytest.raises(ContractError, match="pack.plan"):
        load_verdict(path, pack_dir=pack)


def test_null_verdict_requires_an_explicit_blocker():
    document = _verdict_document()
    document["verdict"] = None
    document["blocked_on"] = []
    with pytest.raises(ContractError, match="blocked_on"):
        from testence.contracts import Verdict

        Verdict.from_dict(document)


def test_test_bug_can_preserve_a_proven_product_claim():
    from testence.contracts import Verdict

    document = _verdict_document()
    document["verdict"] = "test_bug"
    document["summary"] = "The product and PlanSpec agree; the assertion is wrong."
    document["claim_results"][0].update(
        status="passed",
        reason="The authoritative API contains the expected blocker.",
        evidence=["oracle.json#/0"],
    )

    verdict = Verdict.from_dict(document)

    assert verdict.verdict == "test_bug"
    assert verdict.claim_results[0].status == "passed"


def test_test_bug_requires_a_proven_claim():
    from testence.contracts import Verdict

    document = _verdict_document()
    document["verdict"] = "test_bug"
    with pytest.raises(ContractError, match="passed claim"):
        Verdict.from_dict(document)


def test_contract_cli_has_machine_readable_success_and_clean_errors(tmp_path, capsys):
    plan_path = _write_plan(tmp_path / "specs" / "create-blocker.md")
    assert main(["plan", "validate", str(plan_path), "--json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["valid"] is True and output["id"] == "release-board.create-blocker"

    bad = tmp_path / "bad.md"
    bad.write_text("not a plan", encoding="utf-8")
    assert main(["plan", "validate", str(bad)]) == 2
    assert "plan invalid:" in capsys.readouterr().err


def test_verdict_cli_validates_the_pack_by_default(tmp_path, capsys):
    pack = _write_pack(tmp_path / "pack")
    path = pack / "verdict.json"
    path.write_text(json.dumps(_verdict_document()), encoding="utf-8")

    assert main(["verdict", "validate", str(path), "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["valid"] is True and result["verdict"] == "real_bug"


def test_loaded_run_preserves_plan_and_claim_traceability():
    events = [
        {"kind": "run.start", "run": "r-proof", "ts": "2026-01-01T00:00:00Z"},
        {
            "kind": "test.start",
            "test": "test_create_blocker",
            "plan": {"id": "release-board.create-blocker", "path": "specs/create.md"},
            "claims": ["blocker.create.persisted"],
            "ts": "2026-01-01T00:00:01Z",
        },
        {"kind": "test.end", "test": "test_create_blocker", "status": "fail"},
    ]
    test = LoadedRun.from_events(events).tests[0]
    assert test.plan_id == "release-board.create-blocker"
    assert test.plan_path == "specs/create.md"
    assert test.claim_ids == ("blocker.create.persisted",)


def test_public_json_schemas_are_packaged_and_versioned():
    root = files("testence.contracts").joinpath("schemas")
    plan_schema = json.loads(root.joinpath("planspec.schema.json").read_text(encoding="utf-8"))
    verdict_schema = json.loads(root.joinpath("verdict.schema.json").read_text(encoding="utf-8"))
    assert plan_schema["properties"]["schema"]["const"] == PLAN_SCHEMA
    assert verdict_schema["properties"]["schema"]["const"] == VERDICT_SCHEMA
    assert "test_bug" in verdict_schema["properties"]["verdict"]["enum"]
