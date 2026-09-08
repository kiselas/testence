"""Reviewable repair proposals bound to a verdict, source base and proof runs."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from ._validation import ContractError, identifier, known_fields, mapping, string_list, text
from .plan import PlanSpec
from .verdict import Verdict

REPAIR_SCHEMA = "testence/repair-proposal/1"
REPAIR_KINDS = ("locator", "timing", "test_implementation")
PROOF_KINDS = ("healthy", "defect", "harmless")
PROTECTED_FIELDS = (
    "claims",
    "actor_role",
    "scope",
    "skip_policy",
    "retry_policy",
    "required_evidence",
)
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def file_digest(path: Path | str) -> str:
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def protected_plan_digest(plan: PlanSpec) -> str:
    return _digest(
        {
            "project_id": plan.project_id,
            "id": plan.id,
            "source": plan.source,
            "owner": plan.owner,
            "requirements": [{"id": item.id, "url": item.url} for item in plan.requirements],
            "issues": [{"id": item.id, "url": item.url} for item in plan.issues],
            "claims": [
                {
                    "id": claim.id,
                    "statement": claim.statement,
                    "oracles": claim.oracles,
                    "required": claim.required,
                }
                for claim in plan.claims
            ],
            "assertions": [
                {
                    "id": assertion.id,
                    "claim_id": assertion.claim_id,
                    "oracle": assertion.oracle,
                    "required": assertion.required,
                    "expected": assertion.expected,
                }
                for assertion in plan.assertions
            ],
            "scenarios": [
                {
                    "id": scenario.id,
                    "claims": scenario.claims,
                    "risk": scenario.risk,
                }
                for scenario in plan.scenarios
            ],
            "extensions": plan.extensions,
        }
    )


def ensure_no_weakening(before: Mapping[str, Any], after: Mapping[str, Any]) -> None:
    """Reject changes to execution/proof policy during a repair."""
    changed = [field for field in PROTECTED_FIELDS if before.get(field) != after.get(field)]
    if changed:
        raise ContractError("repair weakens or changes protected field(s): " + ", ".join(changed))


@dataclass(frozen=True)
class LocatorChange:
    intent: str
    old: str
    new: str
    source: str


@dataclass(frozen=True)
class RepairProofRun:
    kind: str
    run_id: str
    execution: str
    assurance: str
    evidence: str


@dataclass(frozen=True)
class RepairProposal:
    schema: str
    project_id: str
    case_id: str
    variant_id: str
    attempt_id: str
    run_id: str
    proof_id: str
    verdict_digest: str
    plan_digest: str
    protected_plan_digest: str
    base_digest: str
    kind: str
    summary: str
    patch: str
    changed_claims: tuple[str, ...]
    locator_changes: tuple[LocatorChange, ...]
    proof_runs: tuple[RepairProofRun, ...]

    @classmethod
    def from_dict(cls, value: Any) -> RepairProposal:
        doc = mapping(value, "repair")
        known_fields(
            doc,
            {
                "schema",
                "project_id",
                "case_id",
                "variant_id",
                "attempt_id",
                "run_id",
                "proof_id",
                "verdict_digest",
                "plan_digest",
                "protected_plan_digest",
                "base_digest",
                "kind",
                "summary",
                "patch",
                "changed_claims",
                "locator_changes",
                "proof_runs",
            },
            "repair",
        )

        schema = text(doc, "schema", "repair", max_length=64)
        if schema != REPAIR_SCHEMA:
            raise ContractError(f"unsupported repair schema: {schema!r}")
        kind = text(doc, "kind", "repair", max_length=32)
        if kind not in REPAIR_KINDS:
            raise ContractError("repair.kind must be one of: " + ", ".join(REPAIR_KINDS))
        digests = {
            field: _sha256(doc, field)
            for field in (
                "verdict_digest",
                "plan_digest",
                "protected_plan_digest",
                "base_digest",
            )
        }
        changed_claims = string_list(doc.get("changed_claims", []), "repair.changed_claims")
        if changed_claims:
            raise ContractError("repair cannot change claims; update PlanSpec and triage again")
        raw_changes = doc.get("locator_changes", [])
        if not isinstance(raw_changes, list):
            raise ContractError("repair.locator_changes must be an array")
        changes = tuple(_locator_change(item, index) for index, item in enumerate(raw_changes))
        if kind == "locator" and not changes:
            raise ContractError("locator repair requires at least one locator change")
        raw_runs = doc.get("proof_runs")
        if not isinstance(raw_runs, list):
            raise ContractError("repair.proof_runs must be an array")
        runs = tuple(_proof_run(item, index) for index, item in enumerate(raw_runs))
        if {run.kind for run in runs} != set(PROOF_KINDS) or len(runs) != len(PROOF_KINDS):
            raise ContractError(
                "repair requires exactly one healthy, defect and harmless proof run"
            )
        _validate_proof_matrix(runs)
        return cls(
            schema=schema,
            project_id=identifier(doc, "project_id", "repair"),
            case_id=identifier(doc, "case_id", "repair"),
            variant_id=identifier(doc, "variant_id", "repair"),
            attempt_id=identifier(doc, "attempt_id", "repair"),
            run_id=identifier(doc, "run_id", "repair"),
            proof_id=identifier(doc, "proof_id", "repair"),
            verdict_digest=digests["verdict_digest"],
            plan_digest=digests["plan_digest"],
            protected_plan_digest=digests["protected_plan_digest"],
            base_digest=digests["base_digest"],
            kind=kind,
            summary=text(doc, "summary", "repair", max_length=2000),
            patch=text(doc, "patch", "repair", max_length=200_000),
            changed_claims=changed_claims,
            locator_changes=changes,
            proof_runs=runs,
        )

    def summary_document(self) -> dict[str, Any]:
        return {
            "valid": True,
            "schema": self.schema,
            "project_id": self.project_id,
            "case_id": self.case_id,
            "run_id": self.run_id,
            "kind": self.kind,
            "proof_runs": {run.kind: run.run_id for run in self.proof_runs},
        }


def _sha256(doc: Mapping[str, Any], field: str) -> str:
    value = text(doc, field, "repair", max_length=71)
    if _SHA256.fullmatch(value) is None:
        raise ContractError(f"repair.{field} must be a lowercase sha256 digest")
    return value


def _locator_change(value: Any, index: int) -> LocatorChange:
    path = f"repair.locator_changes[{index}]"
    doc = mapping(value, path)
    known_fields(doc, {"intent", "old", "new", "source"}, path)
    return LocatorChange(
        text(doc, "intent", path, max_length=500),
        text(doc, "old", path, max_length=1000),
        text(doc, "new", path, max_length=1000),
        text(doc, "source", path, max_length=500),
    )


def _proof_run(value: Any, index: int) -> RepairProofRun:
    path = f"repair.proof_runs[{index}]"
    doc = mapping(value, path)
    known_fields(doc, {"kind", "run_id", "execution", "assurance", "evidence"}, path)
    kind = text(doc, "kind", path, max_length=32)
    if kind not in PROOF_KINDS:
        raise ContractError(f"{path}.kind must be one of: {', '.join(PROOF_KINDS)}")
    evidence = text(doc, "evidence", path, max_length=500)
    candidate = PurePosixPath(evidence)
    if candidate.is_absolute() or ".." in candidate.parts or "\\" in evidence:
        raise ContractError(f"{path}.evidence must be a safe relative path")
    return RepairProofRun(
        kind,
        identifier(doc, "run_id", path),
        text(doc, "execution", path, max_length=32),
        text(doc, "assurance", path, max_length=32),
        evidence,
    )


def _validate_proof_matrix(runs: tuple[RepairProofRun, ...]) -> None:
    expected = {
        "healthy": ("passed", "verified"),
        "defect": ("failed", "violated"),
        "harmless": ("passed", "verified"),
    }
    for run in runs:
        if (run.execution, run.assurance) != expected[run.kind]:
            raise ContractError(
                f"repair {run.kind} proof must be execution={expected[run.kind][0]} "
                f"and assurance={expected[run.kind][1]}"
            )


def validate_repair(
    proposal: RepairProposal,
    *,
    verdict: Verdict,
    verdict_path: Path | str,
    plan: PlanSpec,
    base_path: Path | str,
    evidence_root: Path | str | None = None,
) -> None:
    if verdict.verdict not in {"ui_change", "flaky_timing", "test_bug"}:
        raise ContractError(f"verdict {verdict.verdict!r} does not authorize a test repair")
    for field in ("project_id", "case_id", "variant_id", "attempt_id", "run_id", "proof_id"):
        if getattr(proposal, field) != getattr(verdict, field):
            raise ContractError(f"repair {field} does not match verdict")
    expected_kind = {
        "ui_change": "locator",
        "flaky_timing": "timing",
        "test_bug": "test_implementation",
    }[str(verdict.verdict)]
    if proposal.kind != expected_kind:
        raise ContractError(f"repair kind {proposal.kind!r} does not match verdict")
    if proposal.verdict_digest != file_digest(verdict_path):
        raise ContractError("repair verdict_digest does not match verdict file")
    if proposal.plan_digest != plan.digest:
        raise ContractError("repair plan_digest does not match PlanSpec")
    if proposal.protected_plan_digest != protected_plan_digest(plan):
        raise ContractError("repair protected_plan_digest does not match PlanSpec semantics")
    if proposal.base_digest != file_digest(base_path):
        raise ContractError("repair base_digest is stale; source changed before apply")
    if evidence_root is None:
        raise ContractError("repair proof evidence root is required")
    root = Path(evidence_root).resolve()
    for run in proposal.proof_runs:
        _validate_proof_artifact(root, run, proposal)


def _validate_proof_artifact(root: Path, run: RepairProofRun, proposal: RepairProposal) -> None:
    from testence.metrics import load_run

    candidate = root.joinpath(*PurePosixPath(run.evidence).parts).resolve()
    if root not in candidate.parents and candidate != root:
        raise ContractError("repair proof evidence escapes evidence root")
    if not candidate.is_file():
        raise ContractError(f"repair proof evidence does not exist: {run.evidence!r}")
    if candidate.name != "manifest.json":
        raise ContractError("repair proof evidence must reference a run manifest.json")
    try:
        events = load_run(candidate.parent)
    except (OSError, ValueError) as exc:
        raise ContractError(f"repair proof run is invalid: {run.evidence!r}: {exc}") from exc
    final = next((event for event in reversed(events) if event.get("kind") == "run.end"), {})
    if final.get("run_status") == "incomplete":
        raise ContractError(f"repair proof run is incomplete: {run.evidence!r}")
    if final.get("run_id") != run.run_id:
        raise ContractError(f"repair proof run_id does not match manifest: {run.kind}")
    matches = [
        event
        for event in events
        if event.get("kind") == "test.end"
        and event.get("project_id") == proposal.project_id
        and event.get("case_id") == proposal.case_id
        and event.get("variant_id") == proposal.variant_id
    ]
    if len(matches) != 1:
        raise ContractError(f"repair {run.kind} proof must contain exactly one bound attempt")
    terminal = matches[0]
    actual = (str(terminal.get("status")), str(terminal.get("assurance")))
    declared = (run.execution, run.assurance)
    if actual != declared:
        raise ContractError(
            f"repair {run.kind} proof declaration does not match ledger: "
            f"declared={declared[0]}/{declared[1]}, actual={actual[0]}/{actual[1]}"
        )


def load_repair(path: Path | str) -> RepairProposal:
    source = Path(path)
    try:
        document = json.loads(source.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ContractError(f"cannot read repair proposal {source}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ContractError(
            f"invalid repair JSON in {source}: line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    return RepairProposal.from_dict(document)
