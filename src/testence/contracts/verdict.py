"""Typed, evidence-backed verdict produced by an agent after deterministic replay."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from ._validation import (
    ContractError,
    identifier,
    known_fields,
    mapping,
    string_list,
    text,
)
from .plan import PlanSpec

VERDICT_SCHEMA = "testence/verdict/1"
VERDICT_KINDS = (
    "real_bug",
    "test_bug",
    "behaviour_change",
    "ui_change",
    "flaky_timing",
    "environment",
)
CLAIM_STATUSES = ("passed", "failed", "blocked", "not_evaluated")


@dataclass(frozen=True)
class ClaimResult:
    claim_id: str
    status: str
    reason: str
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class Verdict:
    schema: str
    plan_id: str
    test_id: str
    verdict: str | None
    confidence: float
    summary: str
    claim_results: tuple[ClaimResult, ...]
    blocked_on: tuple[str, ...] = ()
    path: Path | None = None

    @property
    def claim_ids(self) -> tuple[str, ...]:
        return tuple(result.claim_id for result in self.claim_results)

    def summary_document(self) -> dict[str, Any]:
        return {
            "valid": True,
            "schema": self.schema,
            "plan_id": self.plan_id,
            "test_id": self.test_id,
            "verdict": self.verdict,
            "confidence": self.confidence,
            "claims": {result.claim_id: result.status for result in self.claim_results},
            "blocked_on": list(self.blocked_on),
            "path": str(self.path) if self.path else None,
        }

    @classmethod
    def from_dict(cls, value: Any, *, path: Path | None = None) -> Verdict:
        doc = mapping(value, "verdict")
        known_fields(
            doc,
            {
                "schema",
                "plan_id",
                "test_id",
                "verdict",
                "confidence",
                "summary",
                "claim_results",
                "blocked_on",
            },
            "verdict",
        )
        schema = text(doc, "schema", "verdict", max_length=64)
        if schema != VERDICT_SCHEMA:
            raise ContractError(f"unsupported verdict schema: {schema!r}")
        plan_id = identifier(doc, "plan_id", "verdict")
        test_id = text(doc, "test_id", "verdict", max_length=500)
        verdict_value = doc.get("verdict")
        if verdict_value is not None and verdict_value not in VERDICT_KINDS:
            raise ContractError(
                "verdict.verdict must be null or one of: " + ", ".join(VERDICT_KINDS)
            )
        confidence = doc.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise ContractError("verdict.confidence must be a number from 0 to 1")
        confidence = float(confidence)
        if not 0.0 <= confidence <= 1.0:
            raise ContractError("verdict.confidence must be a number from 0 to 1")
        summary_value = text(doc, "summary", "verdict", max_length=2000)
        blocked_on = string_list(doc.get("blocked_on", []), "verdict.blocked_on")
        if verdict_value is None and not blocked_on:
            raise ContractError("a null verdict requires at least one blocked_on item")

        raw_results = doc.get("claim_results")
        if not isinstance(raw_results, list) or not raw_results:
            raise ContractError("verdict.claim_results must be a non-empty array")
        results = tuple(_claim_result(item, index) for index, item in enumerate(raw_results))
        result_ids = [result.claim_id for result in results]
        if len(set(result_ids)) != len(result_ids):
            raise ContractError("verdict.claim_results must have unique claim IDs")
        if verdict_value not in (None, "test_bug") and not any(
            result.status in ("failed", "blocked") for result in results
        ):
            raise ContractError("a failure verdict requires a failed or blocked claim")
        if verdict_value == "test_bug" and not any(result.status == "passed" for result in results):
            raise ContractError("a test_bug verdict requires at least one passed claim")
        return cls(
            schema,
            plan_id,
            test_id,
            verdict_value,
            confidence,
            summary_value,
            results,
            blocked_on,
            path,
        )


def _claim_result(value: Any, index: int) -> ClaimResult:
    path = f"verdict.claim_results[{index}]"
    doc = mapping(value, path)
    known_fields(doc, {"claim_id", "status", "reason", "evidence"}, path)
    claim_id = identifier(doc, "claim_id", path)
    status = text(doc, "status", path, max_length=32)
    if status not in CLAIM_STATUSES:
        raise ContractError(f"{path}.status must be one of: {', '.join(CLAIM_STATUSES)}")
    reason = text(doc, "reason", path, max_length=2000)
    evidence = string_list(doc.get("evidence", []), f"{path}.evidence")
    if status in ("passed", "failed") and not evidence:
        raise ContractError(f"{path}.evidence is required for {status!r} status")
    for ref in evidence:
        _evidence_path(ref, f"{path}.evidence")
    return ClaimResult(claim_id, status, reason, evidence)


def _evidence_path(reference: str, path: str) -> PurePosixPath:
    file_part = reference.split("#", 1)[0]
    if not file_part or "\\" in file_part or "://" in file_part:
        raise ContractError(f"{path} contains an unsafe evidence reference: {reference!r}")
    candidate = PurePosixPath(file_part)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ContractError(f"{path} contains an unsafe evidence reference: {reference!r}")
    return candidate


def _validate_against_pack(verdict: Verdict, pack_dir: Path) -> None:
    pack_root = pack_dir.resolve()
    index_path = pack_root / "pack.json"
    try:
        raw_index = json.loads(index_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ContractError(f"cannot read evidence pack index {index_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid evidence pack index {index_path}: {exc}") from exc

    index = mapping(raw_index, "pack")
    pack_test = text(index, "test", "pack", max_length=500)
    if verdict.test_id != pack_test:
        raise ContractError(
            f"verdict test_id {verdict.test_id!r} does not match pack test {pack_test!r}"
        )
    plan = mapping(index.get("plan"), "pack.plan")
    pack_plan_id = identifier(plan, "id", "pack.plan")
    if verdict.plan_id != pack_plan_id:
        raise ContractError(
            f"verdict plan_id {verdict.plan_id!r} does not match pack plan {pack_plan_id!r}"
        )
    pack_claims = string_list(index.get("claims"), "pack.claims", non_empty=True, identifiers=True)
    if set(verdict.claim_ids) != set(pack_claims):
        missing = sorted(set(pack_claims) - set(verdict.claim_ids))
        extra = sorted(set(verdict.claim_ids) - set(pack_claims))
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if extra:
            details.append("unknown " + ", ".join(extra))
        raise ContractError("verdict claim coverage does not match pack: " + "; ".join(details))

    for result in verdict.claim_results:
        for reference in result.evidence:
            relative = _evidence_path(reference, "evidence")
            candidate = pack_root.joinpath(*relative.parts).resolve()
            if pack_root not in candidate.parents:
                raise ContractError(
                    f"evidence reference for {result.claim_id!r} escapes the pack: {reference}"
                )
            if not candidate.is_file():
                raise ContractError(
                    f"evidence reference for {result.claim_id!r} does not exist: {reference}"
                )


def _validate_against_plan(verdict: Verdict, plan: PlanSpec) -> None:
    if verdict.plan_id != plan.id:
        raise ContractError(
            f"verdict plan_id {verdict.plan_id!r} does not match PlanSpec {plan.id!r}"
        )
    unknown = sorted(set(verdict.claim_ids) - set(plan.claim_ids))
    if unknown:
        raise ContractError("verdict references unknown PlanSpec claim(s): " + ", ".join(unknown))


def load_verdict(
    path: Path | str,
    *,
    pack_dir: Path | str | None = None,
    plan: PlanSpec | None = None,
) -> Verdict:
    source = Path(path)
    try:
        document = json.loads(source.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ContractError(f"cannot read verdict {source}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ContractError(
            f"invalid verdict JSON in {source}: line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    verdict = Verdict.from_dict(document, path=source)
    if plan is not None:
        _validate_against_plan(verdict, plan)
    if pack_dir is not None:
        _validate_against_pack(verdict, Path(pack_dir))
    return verdict
