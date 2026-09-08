from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from testence.application import (
    ApplicationError,
    doctor,
    init_project,
    inspect_run,
    run_demo,
    submit_verdict,
)
from testence.cli import main
from testence.contracts import load_plan


def test_init_is_idempotent_and_conflict_safe(tmp_path):
    project = tmp_path / "Acme Product"

    first = init_project(project)
    second = init_project(project)

    assert first["project_id"] == "acme-product"
    assert first["created"]
    assert second["created"] == []
    assert (project / ".testence" / "scaffold-manifest.json").is_file()
    (project / "testence.json").write_text("changed", encoding="utf-8")
    with pytest.raises(ApplicationError, match="conflicts"):
        init_project(project)


def test_scaffold_is_opt_in_and_default_run_produces_verified_proof(tmp_path):
    project = tmp_path / "consumer"
    init_project(project)
    (project / "test_existing.py").write_text(
        "def test_existing(): assert True\n", encoding="utf-8"
    )
    environment = os.environ.copy()
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    collected = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=project,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert collected.returncode == 0
    assert "test_existing" in collected.stdout
    assert "test_testence_synthetic_proof" not in collected.stdout

    assert main(["run", "--project", str(project), "--run-id", "r-onboarding"]) == 0
    summary = inspect_run(project / "runs" / "r-onboarding")
    assert summary["run_status"] == "passed"
    assert summary["execution"] == {"passed": 1}
    assert summary["assurance"] == {"verified": 1}


def test_doctor_is_machine_readable_and_checks_required_runtime(tmp_path):
    project = tmp_path / "doctor"
    init_project(project)

    result = doctor(project)

    assert {item["name"] for item in result["checks"]} == {
        "python",
        "settings",
        "schemas",
        "chromium",
        "workspace",
    }
    assert all("PASSWORD" not in item["detail"] for item in result["checks"])


def _bound_pack(tmp_path: Path):
    project = tmp_path / "submit"
    project.mkdir()
    plan_path = project / "plan.md"
    plan_path.write_text(
        """# Plan

```testence-planspec
{
  "schema": "testence/planspec/2",
  "project_id": "shop",
  "id": "shop.create",
  "title": "Create",
  "claims": [{"id":"shop.created","statement":"Created","oracles":["api"]}],
  "assertions": [{"id":"assert.created","claim_id":"shop.created","oracle":"api"}],
  "scenarios": [{"id":"create","title":"Create","claims":["shop.created"]}]
}
```
""",
        encoding="utf-8",
    )
    plan = load_plan(plan_path)
    pack = project / "pack"
    pack.mkdir()
    test_digest = "sha256:" + "b" * 64
    policy_digest = "sha256:" + "c" * 64
    identity = {
        "project_id": "shop",
        "case_id": "create",
        "variant_id": "default",
        "attempt_id": "attempt-controller-1",
        "run_id": "r-submit",
        "proof_id": "proof-submit",
    }
    (pack / "pack.json").write_text(
        json.dumps(
            {
                "schema": "testence/evidence-pack/2",
                **identity,
                "test": "tests/test_create.py::test_create",
                "plan": {"id": plan.id, "digest": plan.digest},
                "plan_digest": plan.digest,
                "test_digest": test_digest,
                "policy_digest": policy_digest,
                "claims": ["shop.created"],
            }
        ),
        encoding="utf-8",
    )
    (pack / "oracle.json").write_text('{"ok":false}', encoding="utf-8")
    artifacts = []
    for path in sorted(pack.iterdir()):
        raw = path.read_bytes()
        artifacts.append(
            {"path": path.name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        )
    manifest = {"schema": "testence/pack-manifest/2", **identity, "artifacts": artifacts}
    (pack / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    pack_digest = "sha256:" + hashlib.sha256((pack / "manifest.json").read_bytes()).hexdigest()
    candidate = project / "candidate.json"
    candidate.write_text(
        json.dumps(
            {
                "schema": "testence/verdict/2",
                **identity,
                "plan_digest": plan.digest,
                "test_digest": test_digest,
                "policy_digest": policy_digest,
                "pack_digest": pack_digest,
                "plan_id": plan.id,
                "test_id": "tests/test_create.py::test_create",
                "verdict": "real_bug",
                "confidence": 0.9,
                "summary": "The API did not persist the entity.",
                "claim_results": [
                    {
                        "claim_id": "shop.created",
                        "status": "failed",
                        "reason": "Authoritative state is absent.",
                        "evidence": ["oracle.json#/ok"],
                    }
                ],
                "blocked_on": [],
            }
        ),
        encoding="utf-8",
    )
    return plan_path, pack, candidate


def test_verdict_submit_is_validated_atomic_and_idempotent(tmp_path, capsys):
    plan, pack, candidate = _bound_pack(tmp_path)

    first = submit_verdict(candidate, plan_path=plan, pack_dir=pack)
    second = submit_verdict(candidate, plan_path=plan, pack_dir=pack)

    assert first["verdict_digest"] == second["verdict_digest"]
    assert (pack / "verdict.json").read_bytes() == candidate.read_bytes()
    assert (
        json.loads((pack / "verdict.submission.json").read_text(encoding="utf-8"))["schema"]
        == "testence/verdict-submission/1"
    )
    assert (
        main(
            [
                "verdict",
                "submit",
                str(candidate),
                "--plan",
                str(plan),
                "--pack",
                str(pack),
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["schema"] == "testence/verdict-submission/1"
    changed = json.loads(candidate.read_text(encoding="utf-8"))
    changed["summary"] = "A different valid summary."
    candidate.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ApplicationError, match="different content"):
        submit_verdict(candidate, plan_path=plan, pack_dir=pack)


def test_init_and_inspect_cli_return_clean_json(tmp_path, capsys):
    project = tmp_path / "cli"
    assert main(["init", str(project), "--json"]) == 0
    initialized = json.loads(capsys.readouterr().out)
    assert initialized["schema"] == "testence/scaffold-manifest/1"

    assert main(["run", "--project", str(project), "--run-id", "r-cli"]) == 0
    capsys.readouterr()
    assert main(["inspect", str(project / "runs" / "r-cli"), "--json"]) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["run_id"] == "r-cli"


def test_demo_run_accepts_green_and_expected_failure_and_renders_reports(tmp_path):
    result = run_demo(tmp_path / "demo", run_prefix="acceptance")

    assert result["schema"] == "testence/demo-run/1"
    assert result["status"] == "passed"
    assert [(item["name"], item["test_exit"]) for item in result["runs"]] == [
        ("healthy", 0),
        ("intentional_failure", 1),
        ("harmless_change", 0),
    ]
    assert [item["summary"]["assurance"] for item in result["runs"]] == [
        {"verified": 1},
        {"violated": 1},
        {"verified": 1},
    ]
    assert all(Path(item["report"]).is_file() for item in result["runs"])
    failure = result["runs"][1]
    assert failure["pack"] is not None and Path(failure["pack"]).is_dir()
    assert {"pack.json", "manifest.json", "oracle.json", "screenshot.png"} <= set(
        failure["pack_files"]
    )


def test_demo_cli_emits_one_machine_readable_receipt(tmp_path, capsys):
    assert (
        main(
            [
                "demo",
                "run",
                "--project",
                str(tmp_path / "cli-demo"),
                "--run-prefix",
                "cli",
                "--json",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "passed"
    assert all(item["accepted"] for item in result["runs"])


def test_demo_refuses_to_append_to_an_existing_run(tmp_path):
    project = tmp_path / "demo"
    run_demo(project, run_prefix="same")

    with pytest.raises(ApplicationError, match="already exists"):
        run_demo(project, run_prefix="same")
