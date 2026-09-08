from __future__ import annotations

import json

import pytest

import testence.contracts as contracts_module
from testence.assurance import POLICY_DIGEST
from testence.cli import main
from testence.contracts import (
    PLAN_SCHEMA,
    REPAIR_SCHEMA,
    VERDICT_SCHEMA,
    PlanSpec,
    RepairProposal,
    Verdict,
    ensure_no_weakening,
    file_digest,
    protected_plan_digest,
    validate_repair,
)
from testence.contracts._validation import ContractError
from testence.evidence import EvidenceWriter


def _plan() -> PlanSpec:
    return PlanSpec.from_dict(
        {
            "schema": PLAN_SCHEMA,
            "project_id": "shop",
            "id": "shop.create",
            "title": "Create widget",
            "claims": [
                {
                    "id": "widget.persisted",
                    "statement": "Widget persists.",
                    "oracles": ["api"],
                    "required": True,
                }
            ],
            "assertions": [
                {
                    "id": "assert.widget.persisted",
                    "claim_id": "widget.persisted",
                    "oracle": "api",
                    "required": True,
                }
            ],
            "scenarios": [{"id": "create", "title": "Create", "claims": ["widget.persisted"]}],
            "actor_role": "editor",
        },
        digest="sha256:" + "a" * 64,
    )


def _verdict_document(plan: PlanSpec, verdict="ui_change"):
    return {
        "schema": VERDICT_SCHEMA,
        "project_id": "shop",
        "case_id": "create",
        "variant_id": "default",
        "attempt_id": "attempt-controller-1",
        "run_id": "run-1",
        "proof_id": "proof-1",
        "plan_digest": plan.digest,
        "test_digest": "sha256:" + "b" * 64,
        "policy_digest": "sha256:" + "c" * 64,
        "pack_digest": "sha256:" + "d" * 64,
        "plan_id": plan.id,
        "test_id": "tests/test_widgets.py::test_create",
        "verdict": verdict,
        "confidence": 0.9,
        "summary": "The button was renamed while the capability remains.",
        "claim_results": [
            {
                "claim_id": "widget.persisted",
                "status": "failed",
                "reason": "The old semantic address no longer exists.",
                "evidence": ["heal.json#/new_target"],
            }
        ],
        "blocked_on": [],
    }


def _proposal_document(plan, verdict_path, base_path):
    return {
        "schema": REPAIR_SCHEMA,
        "project_id": "shop",
        "case_id": "create",
        "variant_id": "default",
        "attempt_id": "attempt-controller-1",
        "run_id": "run-1",
        "proof_id": "proof-1",
        "verdict_digest": file_digest(verdict_path),
        "plan_digest": plan.digest,
        "protected_plan_digest": protected_plan_digest(plan),
        "base_digest": file_digest(base_path),
        "kind": "locator",
        "summary": "Update the renamed Save button address.",
        "patch": "- Target('role', 'button', name='Save')\n+ Target('role', 'button', name='Store')",
        "changed_claims": [],
        "locator_changes": [
            {
                "intent": "save widget",
                "old": "role=button name=Save",
                "new": "role=button name=Store",
                "source": "tests/test_widgets.py:20",
            }
        ],
        "proof_runs": [
            {
                "kind": "healthy",
                "run_id": "proof-healthy",
                "execution": "passed",
                "assurance": "verified",
                "evidence": "proof-healthy/manifest.json",
            },
            {
                "kind": "defect",
                "run_id": "proof-defect",
                "execution": "failed",
                "assurance": "violated",
                "evidence": "proof-defect/manifest.json",
            },
            {
                "kind": "harmless",
                "run_id": "proof-harmless",
                "execution": "passed",
                "assurance": "verified",
                "evidence": "proof-harmless/manifest.json",
            },
        ],
    }


def _files(tmp_path, verdict_kind="ui_change", *, healthy_failed=False):
    tmp_path.mkdir(parents=True, exist_ok=True)
    plan = _plan()
    verdict_path = tmp_path / "verdict.json"
    verdict_path.write_text(json.dumps(_verdict_document(plan, verdict_kind)), encoding="utf-8")
    verdict = Verdict.from_dict(json.loads(verdict_path.read_text(encoding="utf-8")))
    base = tmp_path / "test_widgets.py"
    base.write_text("SAVE = Target('role', 'button', name='Save')\n", encoding="utf-8")
    evidence = tmp_path / "proof"
    for name in ("healthy", "defect", "harmless"):
        run_id = f"proof-{name}"
        test_id = "tests/test_widgets.py::test_create"
        writer = EvidenceWriter(evidence, run_id=run_id, worker="", project_id="shop")
        writer.bind_test(
            test_id,
            identity={
                "project_id": "shop",
                "case_id": "create",
                "variant_id": "default",
                "attempt_id": "attempt-controller-1",
                "run_id": run_id,
                "proof_id": f"proof-{name}-id",
                "parameters": {},
            },
            plan={"schema": PLAN_SCHEMA, "id": plan.id, "digest": plan.digest},
            claims=["widget.persisted"],
            assertions=[
                {
                    "id": "assert.widget.persisted",
                    "claim_id": "widget.persisted",
                    "oracle": "api",
                    "required": True,
                }
            ],
            plan_digest=plan.digest,
            test_digest="sha256:" + "b" * 64,
            policy_digest=POLICY_DIGEST,
        )
        failed = name == "defect" or (name == "healthy" and healthy_failed)
        writer.emit("run.start", testence="test")
        writer.emit("test.start", test=test_id, nodeid=test_id)
        writer.emit(
            "assertion",
            test=test_id,
            assertion_id="assert.widget.persisted",
            claim_id="widget.persisted",
            oracle_kind="api",
            outcome="failed" if failed else "passed",
            expected={"persisted": True},
            actual={"persisted": not failed},
            source="test_widgets.py:20",
        )
        writer.emit(
            "test.end",
            test=test_id,
            nodeid=test_id,
            status="failed" if failed else "passed",
            duration_ms=1,
        )
        writer.emit(
            "run.end",
            duration_ms=1,
            exit_code=1 if failed else 0,
            run_status="failed" if failed else "passed",
        )
        writer.close()
    return plan, verdict, verdict_path, base, evidence


def test_bound_repair_with_three_proof_runs_validates(tmp_path):
    plan, verdict, verdict_path, base, evidence = _files(tmp_path)
    proposal = RepairProposal.from_dict(_proposal_document(plan, verdict_path, base))

    validate_repair(
        proposal,
        verdict=verdict,
        verdict_path=verdict_path,
        plan=plan,
        base_path=base,
        evidence_root=evidence,
    )


def test_repair_validate_cli_emits_machine_summary(tmp_path, monkeypatch, capsys):
    plan, verdict, verdict_path, base, _evidence = _files(tmp_path)
    proposal = RepairProposal.from_dict(_proposal_document(plan, verdict_path, base))
    monkeypatch.setattr(contracts_module, "load_plan", lambda _path: plan)
    monkeypatch.setattr(contracts_module, "load_verdict", lambda *args, **kwargs: verdict)
    monkeypatch.setattr(contracts_module, "load_repair", lambda _path: proposal)
    monkeypatch.setattr(contracts_module, "validate_repair", lambda *args, **kwargs: None)

    result = main(
        [
            "repair",
            "validate",
            str(tmp_path / "repair.json"),
            "--verdict",
            str(verdict_path),
            "--plan",
            str(tmp_path / "plan.md"),
            "--base",
            str(base),
            "--evidence-root",
            str(tmp_path / "proof"),
            "--json",
        ]
    )

    assert result == 0
    assert json.loads(capsys.readouterr().out) == proposal.summary_document()


def test_repair_rejects_claim_change_and_incomplete_proof_matrix(tmp_path):
    plan, _verdict, verdict_path, base, _evidence = _files(tmp_path)
    document = _proposal_document(plan, verdict_path, base)
    document["changed_claims"] = ["widget.persisted"]
    with pytest.raises(ContractError, match="cannot change claims"):
        RepairProposal.from_dict(document)

    document = _proposal_document(plan, verdict_path, base)
    document["proof_runs"].pop()
    with pytest.raises(ContractError, match="exactly one"):
        RepairProposal.from_dict(document)


def test_repair_rejects_green_defect_control(tmp_path):
    plan, _verdict, verdict_path, base, _evidence = _files(tmp_path)
    document = _proposal_document(plan, verdict_path, base)
    document["proof_runs"][1].update(execution="passed", assurance="verified")

    with pytest.raises(ContractError, match="defect proof"):
        RepairProposal.from_dict(document)


def test_repair_rejects_stale_base_and_nonrepair_verdict(tmp_path):
    plan, verdict, verdict_path, base, evidence = _files(tmp_path)
    proposal = RepairProposal.from_dict(_proposal_document(plan, verdict_path, base))
    base.write_text("changed concurrently\n", encoding="utf-8")
    with pytest.raises(ContractError, match="base_digest is stale"):
        validate_repair(
            proposal,
            verdict=verdict,
            verdict_path=verdict_path,
            plan=plan,
            base_path=base,
            evidence_root=evidence,
        )

    plan, verdict, verdict_path, base, evidence = _files(tmp_path / "bug", "real_bug")
    proposal = RepairProposal.from_dict(_proposal_document(plan, verdict_path, base))
    with pytest.raises(ContractError, match="does not authorize"):
        validate_repair(
            proposal,
            verdict=verdict,
            verdict_path=verdict_path,
            plan=plan,
            base_path=base,
            evidence_root=evidence,
        )


def test_repair_rejects_proof_declaration_that_disagrees_with_ledger(tmp_path):
    plan, verdict, verdict_path, base, evidence = _files(tmp_path, healthy_failed=True)
    proposal = RepairProposal.from_dict(_proposal_document(plan, verdict_path, base))

    with pytest.raises(ContractError, match="declaration does not match ledger"):
        validate_repair(
            proposal,
            verdict=verdict,
            verdict_path=verdict_path,
            plan=plan,
            base_path=base,
            evidence_root=evidence,
        )


@pytest.mark.parametrize(
    "field", ["claims", "actor_role", "scope", "skip_policy", "retry_policy", "required_evidence"]
)
def test_protected_test_contract_cannot_be_weakened(field):
    before = {
        name: "same"
        for name in (
            "claims",
            "actor_role",
            "scope",
            "skip_policy",
            "retry_policy",
            "required_evidence",
        )
    }
    after = dict(before)
    after[field] = "weakened"

    with pytest.raises(ContractError, match=field):
        ensure_no_weakening(before, after)
