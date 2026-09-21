"""The versioned contracts that close plan → evidence → verdict."""

from __future__ import annotations

import hashlib
import json
from importlib.resources import files
from pathlib import Path
from types import SimpleNamespace

import pytest

from testence.cli import main
from testence.contracts import (
    LEGACY_PLAN_SCHEMA,
    LEGACY_VERDICT_SCHEMA,
    PLAN_SCHEMA,
    REPAIR_SCHEMA,
    SCHEMA_INVENTORY,
    VERDICT_SCHEMA,
    PlanSpec,
    Verdict,
    load_plan,
    load_verdict,
)
from testence.contracts._validation import ContractError
from testence.export._model import LoadedRun
from testence.pytest_plugin import _resolve_contract

PLAN_DIGEST = "sha256:" + "a" * 64
TEST_DIGEST = "sha256:" + "b" * 64
POLICY_DIGEST = "sha256:" + "c" * 64
PACK_DIGEST = "sha256:" + "d" * 64


def _plan_document(*, claim_id: str = "blocker.create.persisted") -> dict:
    return {
        "schema": PLAN_SCHEMA,
        "project_id": "release-board",
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
        "assertions": [
            {
                "id": "assert.blocker.persisted",
                "claim_id": claim_id,
                "oracle": "api",
                "required": True,
                "expected": "The created blocker is returned by its ID.",
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


def test_planspec_reporting_metadata_is_typed_and_preserved():
    document = _plan_document()
    document.update(
        owner="qa-platform",
        requirements=[{"id": "REQ-7", "url": "https://tms.example/REQ-7"}],
        issues=[{"id": "BUG-9", "url": "https://issues.example/BUG-9"}],
    )

    plan = PlanSpec.from_dict(document)

    assert plan.owner == "qa-platform"
    assert plan.requirements[0].id == "REQ-7"
    assert plan.issues[0].url == "https://issues.example/BUG-9"


def _write_plan(path: Path, document: dict | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(document or _plan_document(), ensure_ascii=False, indent=2)
    path.write_text(
        f"# Create blocker\n\n```testence-planspec\n{body}\n```\n",
        encoding="utf-8",
    )
    return path


def _verdict_document(pack: Path | None = None, *, plan_digest: str = PLAN_DIGEST) -> dict:
    return {
        "schema": VERDICT_SCHEMA,
        "project_id": "release-board",
        "case_id": "create-blocker",
        "variant_id": "default",
        "attempt_id": "attempt-controller-1",
        "run_id": "r-contract-1",
        "proof_id": "proof-contract-1",
        "plan_digest": plan_digest,
        "test_digest": TEST_DIGEST,
        "policy_digest": POLICY_DIGEST,
        "pack_digest": (
            "sha256:" + hashlib.sha256((pack / "manifest.json").read_bytes()).hexdigest()
            if pack is not None
            else PACK_DIGEST
        ),
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


def _refresh_manifest(path: Path) -> None:
    artifacts = []
    for artifact in sorted(path.iterdir()):
        if (
            not artifact.is_file()
            or artifact.name == "manifest.json"
            or artifact.name.startswith("verdict.")
        ):
            continue
        raw = artifact.read_bytes()
        artifacts.append(
            {"path": artifact.name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        )
    (path / "manifest.json").write_text(
        json.dumps(
            {
                "schema": "testence/pack-manifest/2",
                "project_id": "release-board",
                "case_id": "create-blocker",
                "variant_id": "default",
                "attempt_id": "attempt-controller-1",
                "run_id": "r-contract-1",
                "proof_id": "proof-contract-1",
                "artifacts": artifacts,
            }
        ),
        encoding="utf-8",
    )


def _write_pack(path: Path, *, plan_digest: str = PLAN_DIGEST) -> Path:
    path.mkdir(parents=True)
    (path / "pack.json").write_text(
        json.dumps(
            {
                "schema": "testence/evidence-pack/2",
                "project_id": "release-board",
                "case_id": "create-blocker",
                "variant_id": "default",
                "attempt_id": "attempt-controller-1",
                "run_id": "r-contract-1",
                "proof_id": "proof-contract-1",
                "test": "test_create_blocker",
                "plan": {
                    "schema": PLAN_SCHEMA,
                    "project_id": "release-board",
                    "id": "release-board.create-blocker",
                    "path": "specs/create-blocker.md",
                    "digest": plan_digest,
                },
                "plan_digest": plan_digest,
                "test_digest": TEST_DIGEST,
                "policy_digest": POLICY_DIGEST,
                "claims": ["blocker.create.persisted"],
            }
        ),
        encoding="utf-8",
    )
    (path / "oracle.json").write_text('[{"field":"id"}]', encoding="utf-8")
    (path / "network.jsonl").write_text('{"status":404}\n', encoding="utf-8")
    _refresh_manifest(path)
    return path


def test_markdown_planspec_is_strict_and_human_readable(tmp_path):
    path = _write_plan(tmp_path / "specs" / "create-blocker.md")
    plan = load_plan(path)

    assert plan.id == "release-board.create-blocker"
    assert plan.project_id == "release-board"
    assert plan.claim_ids == ("blocker.create.persisted",)
    assert plan.assertions[0].id == "assert.blocker.persisted"
    assert plan.digest.startswith("sha256:")
    assert plan.scenarios[0].claims == plan.claim_ids
    assert plan.summary()["valid"] is True


def test_planspec_v1_adapter_marks_legacy_identity_and_preserves_extensions(tmp_path):
    document = _plan_document()
    document["schema"] = LEGACY_PLAN_SCHEMA
    document.pop("project_id")
    document.pop("assertions")
    document["future_note"] = {"kept": True}

    plan = load_plan(_write_plan(tmp_path / "legacy.md", document))

    assert plan.schema == PLAN_SCHEMA
    assert plan.source_schema == LEGACY_PLAN_SCHEMA
    assert plan.project_id == "legacy"
    assert plan.extensions == {"future_note": {"kept": True}}


def test_planspec_rejects_unknown_claims_and_uncovered_required_claims(tmp_path):
    document = _plan_document()
    document["scenarios"][0]["claims"] = ["blocker.create.visible"]
    path = _write_plan(tmp_path / "bad.md", document)

    with pytest.raises(ContractError, match="unknown claim"):
        load_plan(path)


def test_planspec_requires_one_required_assertion_per_required_claim(tmp_path):
    document = _plan_document()
    document["assertions"] = []
    path = _write_plan(tmp_path / "missing-assertion.md", document)

    with pytest.raises(ContractError, match="no required assertion"):
        load_plan(path)


def test_planspec_rejects_assertions_bound_to_unknown_claims(tmp_path):
    document = _plan_document()
    document["assertions"][0]["claim_id"] = "unknown.claim"
    path = _write_plan(tmp_path / "unknown-assertion-claim.md", document)

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
    assert binding.case_id == "create-blocker"
    assert binding.path == "specs/create-blocker.md"
    assert binding.claims == ("blocker.create.persisted",)


def test_plan_capabilities_are_typed_and_preflighted(tmp_path):
    document = _plan_document()
    document["scenarios"][0]["capabilities"] = ["browser.dom", "browser.files"]
    _write_plan(tmp_path / "specs" / "create-blocker.md", document)
    marker = pytest.mark.testence(
        plan="specs/create-blocker.md", claims=["blocker.create.persisted"]
    ).mark
    item = SimpleNamespace(get_closest_marker=lambda _name: marker)

    with pytest.raises(ContractError, match="unsupported engine capability: browser.files"):
        _resolve_contract(item, tmp_path, frozenset({"browser.dom"}))

    binding = _resolve_contract(item, tmp_path, frozenset({"browser.dom", "browser.files"}))
    assert binding is not None
    assert binding.plan.scenarios[0].capabilities == ("browser.dom", "browser.files")

    document["scenarios"][0]["capabilities"] = ["native.touch"]
    with pytest.raises(ContractError, match="unsupported value"):
        PlanSpec.from_dict(document)


def test_pytest_marker_rejects_paths_outside_repository(tmp_path):
    marker = pytest.mark.testence(plan="../outside.md", claims=["claim.one"]).mark
    item = SimpleNamespace(get_closest_marker=lambda _name: marker)
    with pytest.raises(ContractError, match="inside the repository"):
        _resolve_contract(item, tmp_path)


def test_verdict_is_checked_against_plan_pack_claims_and_evidence(tmp_path):
    plan = load_plan(_write_plan(tmp_path / "specs" / "create-blocker.md"))
    pack = _write_pack(tmp_path / "pack", plan_digest=plan.digest)
    verdict_path = pack / "verdict.json"
    verdict_path.write_text(
        json.dumps(_verdict_document(pack, plan_digest=plan.digest)), encoding="utf-8"
    )

    verdict = load_verdict(verdict_path, pack_dir=pack, plan=plan)

    assert verdict.verdict == "real_bug"
    assert verdict.claim_ids == ("blocker.create.persisted",)
    assert verdict.summary_document()["claims"] == {"blocker.create.persisted": "failed"}


def test_verdict_rejects_missing_or_unsafe_evidence(tmp_path):
    pack = _write_pack(tmp_path / "pack")
    document = _verdict_document(pack)
    document["claim_results"][0]["evidence"] = ["../secret.txt"]
    path = tmp_path / "verdict.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ContractError, match="unsafe evidence"):
        load_verdict(path, pack_dir=pack)

    document["claim_results"][0]["evidence"] = ["missing.json"]
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ContractError, match="does not exist"):
        load_verdict(path, pack_dir=pack)


def test_verdict_resolves_json_pointer_instead_of_only_checking_the_file(tmp_path):
    pack = _write_pack(tmp_path / "pack")
    document = _verdict_document(pack)
    document["claim_results"][0]["evidence"] = ["oracle.json#/999/nonexistent"]
    path = pack / "verdict.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ContractError, match="Pointer does not exist"):
        load_verdict(path, pack_dir=pack)


def test_verdict_rejects_artifact_changed_after_manifest(tmp_path):
    pack = _write_pack(tmp_path / "pack")
    document = _verdict_document(pack)
    (pack / "oracle.json").write_text('[{"field":"changed"}]', encoding="utf-8")
    path = pack / "verdict.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ContractError, match="integrity mismatch"):
        load_verdict(path, pack_dir=pack)


@pytest.mark.parametrize("field", ["plan_digest", "test_digest", "policy_digest", "pack_digest"])
def test_verdict_rejects_stale_proof_digest(tmp_path, field):
    pack = _write_pack(tmp_path / "pack")
    document = _verdict_document(pack)
    document[field] = "sha256:" + "f" * 64
    path = pack / "verdict.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ContractError, match=field):
        load_verdict(path, pack_dir=pack)


def test_verdict_rejects_evidence_event_from_another_attempt(tmp_path):
    pack = _write_pack(tmp_path / "pack")
    (pack / "events.jsonl").write_text(
        json.dumps(
            {
                "run_id": "r-contract-1",
                "attempt_id": "attempt-controller-99",
                "proof_id": "proof-contract-1",
                "kind": "assertion",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    _refresh_manifest(pack)
    document = _verdict_document(pack)
    document["claim_results"][0]["evidence"] = ["events.jsonl#/0"]
    path = pack / "verdict.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ContractError, match="does not belong"):
        load_verdict(path, pack_dir=pack)


def test_verdict_rejects_existing_artifact_outside_manifest(tmp_path):
    pack = _write_pack(tmp_path / "pack")
    (pack / "unbound.json").write_text('{"looks":"valid"}', encoding="utf-8")
    document = _verdict_document(pack)
    document["claim_results"][0]["evidence"] = ["unbound.json#/looks"]
    path = pack / "verdict.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ContractError, match="not bound by the pack manifest"):
        load_verdict(path, pack_dir=pack)


def test_verdict_rejects_a_legacy_pack_without_proof_binding(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / "pack.json").write_text(json.dumps({"test": "test_create_blocker"}), encoding="utf-8")
    (pack / "oracle.json").write_text("[]", encoding="utf-8")
    (pack / "network.jsonl").write_text("", encoding="utf-8")
    path = pack / "verdict.json"
    path.write_text(json.dumps(_verdict_document()), encoding="utf-8")

    with pytest.raises(ContractError, match="requires a testence/evidence-pack/2"):
        load_verdict(path, pack_dir=pack)


def test_null_verdict_requires_an_explicit_blocker():
    document = _verdict_document()
    document["verdict"] = None
    document["blocked_on"] = []
    with pytest.raises(ContractError, match="blocked_on"):
        from testence.contracts import Verdict

        Verdict.from_dict(document)


def test_verdict_v1_adapter_never_invents_run_or_proof_identity():
    document = _verdict_document()
    document["schema"] = LEGACY_VERDICT_SCHEMA
    for field in ("project_id", "case_id", "variant_id", "attempt_id", "run_id", "proof_id"):
        document.pop(field)
    document["future_note"] = "kept"

    verdict = Verdict.from_dict(document)

    assert verdict.schema == VERDICT_SCHEMA
    assert verdict.source_schema == LEGACY_VERDICT_SCHEMA
    assert verdict.run_id == "legacy" and verdict.proof_id == "unknown"
    assert verdict.extensions == {"future_note": "kept"}


def test_verdict_v2_rejects_cross_run_pack_binding(tmp_path):
    pack = _write_pack(tmp_path / "pack")
    document = _verdict_document(pack)
    document["run_id"] = "r-other"
    path = pack / "verdict.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ContractError, match="run_id"):
        load_verdict(path, pack_dir=pack)


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
    path.write_text(json.dumps(_verdict_document(pack)), encoding="utf-8")

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
    evidence_schema = json.loads(root.joinpath("evidence.schema.json").read_text(encoding="utf-8"))
    pack_schema = json.loads(root.joinpath("evidence-pack.schema.json").read_text(encoding="utf-8"))
    manifest_schema = json.loads(
        root.joinpath("pack-manifest.schema.json").read_text(encoding="utf-8")
    )
    run_manifest_schema = json.loads(
        root.joinpath("run-manifest.schema.json").read_text(encoding="utf-8")
    )
    policy_schema = json.loads(
        root.joinpath("assurance-policy.schema.json").read_text(encoding="utf-8")
    )
    repair_schema = json.loads(
        root.joinpath("repair-proposal.schema.json").read_text(encoding="utf-8")
    )
    ci_schema = json.loads(root.joinpath("ci-receipt.schema.json").read_text(encoding="utf-8"))
    delivery_schema = json.loads(
        root.joinpath("delivery-receipt.schema.json").read_text(encoding="utf-8")
    )
    scaffold_schema = json.loads(
        root.joinpath("scaffold-manifest.schema.json").read_text(encoding="utf-8")
    )
    submission_schema = json.loads(
        root.joinpath("verdict-submission.schema.json").read_text(encoding="utf-8")
    )
    capability_schema = json.loads(
        root.joinpath("engine-capabilities.schema.json").read_text(encoding="utf-8")
    )
    quality_schemas = {
        key: json.loads(root.joinpath(filename).read_text(encoding="utf-8"))
        for key, filename in {
            "quality_pack": "quality-pack.schema.json",
            "quality_pack_lock": "quality-pack-lock.schema.json",
            "quality_sync": "quality-sync.schema.json",
            "quality_summary": "quality-summary.schema.json",
        }.items()
    }
    agent_schemas = {
        key: json.loads(root.joinpath(filename).read_text(encoding="utf-8"))
        for key, filename in {
            "agent_install": "agent-install.schema.json",
            "agent_install_receipt": "agent-install-receipt.schema.json",
        }.items()
    }
    corpus_schema = json.loads(
        root.joinpath("correctness-corpus.schema.json").read_text(encoding="utf-8")
    )
    corpus_freeze_schema = json.loads(
        root.joinpath("correctness-corpus-freeze.schema.json").read_text(encoding="utf-8")
    )
    assert plan_schema["properties"]["schema"]["const"] == PLAN_SCHEMA
    assert "assertions" in plan_schema["required"]
    assert verdict_schema["properties"]["schema"]["const"] == VERDICT_SCHEMA
    assert evidence_schema["properties"]["v"]["const"] == SCHEMA_INVENTORY["evidence"]
    assert pack_schema["properties"]["schema"]["const"] == SCHEMA_INVENTORY["evidence_pack"]
    assert manifest_schema["properties"]["schema"]["const"] == SCHEMA_INVENTORY["pack_manifest"]
    assert run_manifest_schema["properties"]["schema"]["const"] == SCHEMA_INVENTORY["run_manifest"]
    assert policy_schema["properties"]["schema"]["const"] == SCHEMA_INVENTORY["assurance_policy"]
    assert repair_schema["properties"]["schema"]["const"] == REPAIR_SCHEMA
    assert SCHEMA_INVENTORY["repair_proposal"] == REPAIR_SCHEMA
    assert ci_schema["properties"]["schema"]["const"] == SCHEMA_INVENTORY["ci_receipt"]
    assert delivery_schema["properties"]["schema"]["const"] == SCHEMA_INVENTORY["delivery_receipt"]
    assert scaffold_schema["properties"]["schema"]["const"] == SCHEMA_INVENTORY["scaffold_manifest"]
    assert (
        submission_schema["properties"]["schema"]["const"] == SCHEMA_INVENTORY["verdict_submission"]
    )
    assert (
        capability_schema["properties"]["schema"]["const"]
        == SCHEMA_INVENTORY["engine_capabilities"]
    )
    for key, schema in quality_schemas.items():
        assert schema["properties"]["schema"]["const"] == SCHEMA_INVENTORY[key]
    for key, schema in agent_schemas.items():
        assert schema["properties"]["schema"]["const"] == SCHEMA_INVENTORY[key]
    assert corpus_schema["properties"]["schema"]["const"] == SCHEMA_INVENTORY["correctness_corpus"]
    assert (
        corpus_freeze_schema["properties"]["schema"]["const"]
        == SCHEMA_INVENTORY["correctness_corpus_freeze"]
    )
    assert root.joinpath("planspec-v1.schema.json").is_file()
    assert root.joinpath("verdict-v1.schema.json").is_file()
    readiness_schema = json.loads(
        root.joinpath("readiness-report.schema.json").read_text(encoding="utf-8")
    )
    assert readiness_schema["properties"]["schema"]["const"] == SCHEMA_INVENTORY["readiness_report"]
    assert "test_bug" in verdict_schema["properties"]["verdict"]["enum"]
