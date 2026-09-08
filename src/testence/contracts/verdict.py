"""Typed, evidence-backed verdict produced by an agent after deterministic replay."""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from ._validation import (
    ContractError,
    identifier,
    known_fields,
    mapping,
    string_list,
    text,
)
from .plan import PlanSpec

VERDICT_SCHEMA = "testence/verdict/2"
LEGACY_VERDICT_SCHEMA = "testence/verdict/1"
VERDICT_KINDS = (
    "real_bug",
    "test_bug",
    "behaviour_change",
    "ui_change",
    "flaky_timing",
    "environment",
)
CLAIM_STATUSES = ("passed", "failed", "blocked", "not_evaluated")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class ClaimResult:
    claim_id: str
    status: str
    reason: str
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class Verdict:
    schema: str
    project_id: str
    case_id: str
    variant_id: str
    attempt_id: str
    run_id: str
    proof_id: str
    plan_digest: str
    test_digest: str
    policy_digest: str
    pack_digest: str
    plan_id: str
    test_id: str
    verdict: str | None
    confidence: float
    summary: str
    claim_results: tuple[ClaimResult, ...]
    blocked_on: tuple[str, ...] = ()
    path: Path | None = None
    source_schema: str | None = None
    extensions: dict[str, Any] | None = None

    @property
    def claim_ids(self) -> tuple[str, ...]:
        return tuple(result.claim_id for result in self.claim_results)

    def summary_document(self) -> dict[str, Any]:
        return {
            "valid": True,
            "schema": self.schema,
            "project_id": self.project_id,
            "case_id": self.case_id,
            "variant_id": self.variant_id,
            "attempt_id": self.attempt_id,
            "run_id": self.run_id,
            "proof_id": self.proof_id,
            "plan_digest": self.plan_digest,
            "test_digest": self.test_digest,
            "policy_digest": self.policy_digest,
            "pack_digest": self.pack_digest,
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
        allowed = {
            "schema",
            "project_id",
            "case_id",
            "variant_id",
            "attempt_id",
            "run_id",
            "proof_id",
            "plan_digest",
            "test_digest",
            "policy_digest",
            "pack_digest",
            "plan_id",
            "test_id",
            "verdict",
            "confidence",
            "summary",
            "claim_results",
            "blocked_on",
        }
        schema = text(doc, "schema", "verdict", max_length=64)
        if schema not in (VERDICT_SCHEMA, LEGACY_VERDICT_SCHEMA):
            raise ContractError(f"unsupported verdict schema: {schema!r}")
        if schema == VERDICT_SCHEMA:
            project_id = identifier(doc, "project_id", "verdict")
            case_id = identifier(doc, "case_id", "verdict")
            variant_id = identifier(doc, "variant_id", "verdict")
            attempt_id = identifier(doc, "attempt_id", "verdict")
            run_id = identifier(doc, "run_id", "verdict")
            proof_id = identifier(doc, "proof_id", "verdict")
            plan_digest = _sha256_digest(doc, "plan_digest", "verdict")
            test_digest = _sha256_digest(doc, "test_digest", "verdict")
            policy_digest = _sha256_digest(doc, "policy_digest", "verdict")
            pack_digest = _sha256_digest(doc, "pack_digest", "verdict")
        else:
            project_id = "legacy"
            case_id = "legacy"
            variant_id = "legacy"
            attempt_id = "legacy"
            run_id = "legacy"
            proof_id = "unknown"
            plan_digest = test_digest = policy_digest = pack_digest = "unknown"
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
            schema=VERDICT_SCHEMA,
            project_id=project_id,
            case_id=case_id,
            variant_id=variant_id,
            attempt_id=attempt_id,
            run_id=run_id,
            proof_id=proof_id,
            plan_digest=plan_digest,
            test_digest=test_digest,
            policy_digest=policy_digest,
            pack_digest=pack_digest,
            plan_id=plan_id,
            test_id=test_id,
            verdict=verdict_value,
            confidence=confidence,
            summary=summary_value,
            claim_results=results,
            blocked_on=blocked_on,
            path=path,
            source_schema=schema if schema != VERDICT_SCHEMA else None,
            extensions={key: doc[key] for key in doc if key not in allowed} or None,
        )


def _sha256_digest(document: Mapping[str, Any], field: str, path: str) -> str:
    value = text(document, field, path, max_length=71)
    if not _DIGEST.fullmatch(value):
        raise ContractError(f"{path}.{field} must be a sha256 digest")
    return value


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


def _read_json_artifact(path: Path) -> Any:
    try:
        if path.suffix == ".jsonl":
            return [
                json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line
            ]
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot resolve JSON evidence {path.name}: {exc}") from exc


def _resolve_pointer(path: Path, reference: str) -> Any:
    if "#" not in reference:
        return None
    fragment = urllib.parse.unquote(reference.split("#", 1)[1])
    if not fragment.startswith("/"):
        raise ContractError(f"evidence reference has an invalid JSON Pointer: {reference!r}")
    if path.suffix not in {".json", ".jsonl"}:
        raise ContractError(f"JSON Pointer requires a JSON/JSONL artifact: {reference!r}")
    current = _read_json_artifact(path)
    for raw in fragment[1:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            raise ContractError(f"evidence JSON Pointer does not exist: {reference!r}")
    return current


def _manifest_artifacts(pack_root: Path, manifest: Mapping[str, Any]) -> set[str]:
    raw_artifacts = manifest.get("artifacts")
    if not isinstance(raw_artifacts, list):
        raise ContractError("pack manifest artifacts must be an array")
    artifacts: set[str] = set()
    for index, raw in enumerate(raw_artifacts):
        artifact = mapping(raw, f"pack manifest artifacts[{index}]")
        name = text(artifact, "path", f"pack manifest artifacts[{index}]", max_length=255)
        relative = _evidence_path(name, "pack manifest artifact")
        if len(relative.parts) != 1 or name in artifacts:
            raise ContractError(f"invalid or duplicate pack manifest artifact: {name!r}")
        candidate = pack_root / name
        if not candidate.is_file():
            raise ContractError(f"pack manifest artifact does not exist: {name!r}")
        raw_bytes = candidate.read_bytes()
        expected_bytes = artifact.get("bytes")
        expected_digest = artifact.get("sha256")
        if (
            expected_bytes != len(raw_bytes)
            or expected_digest != hashlib.sha256(raw_bytes).hexdigest()
        ):
            raise ContractError(f"pack manifest integrity mismatch for artifact: {name!r}")
        artifacts.add(name)
    if "pack.json" not in artifacts:
        raise ContractError("pack manifest must bind pack.json")
    return artifacts


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
    pack_schema = index.get("schema")
    if pack_schema == "testence/evidence-pack/2":
        for field in (
            "project_id",
            "case_id",
            "variant_id",
            "attempt_id",
            "run_id",
            "proof_id",
        ):
            pack_value = text(index, field, "pack", max_length=128)
            if getattr(verdict, field) != pack_value:
                raise ContractError(
                    f"verdict {field} {getattr(verdict, field)!r} does not match pack {pack_value!r}"
                )
        manifest_path = pack_root / "manifest.json"
        try:
            manifest_bytes = manifest_path.read_bytes()
            raw_manifest = json.loads(manifest_bytes)
        except (OSError, json.JSONDecodeError) as exc:
            raise ContractError(f"cannot read pack manifest {manifest_path}: {exc}") from exc
        manifest = mapping(raw_manifest, "pack manifest")
        if manifest.get("schema") != "testence/pack-manifest/2":
            raise ContractError("unsupported or missing pack manifest schema")
        for field in (
            "project_id",
            "case_id",
            "variant_id",
            "attempt_id",
            "run_id",
            "proof_id",
        ):
            if manifest.get(field) != getattr(verdict, field):
                raise ContractError(f"pack manifest {field} does not match verdict")
        artifacts = _manifest_artifacts(pack_root, manifest)
        actual_pack_digest = "sha256:" + hashlib.sha256(manifest_bytes).hexdigest()
        if verdict.pack_digest != actual_pack_digest:
            raise ContractError("verdict pack_digest does not match manifest")
        plan = mapping(index.get("plan"), "pack.plan")
        expected_digests = {
            "plan_digest": index.get("plan_digest") or plan.get("digest"),
            "test_digest": index.get("test_digest"),
            "policy_digest": index.get("policy_digest"),
        }
        for field, expected in expected_digests.items():
            if getattr(verdict, field) != expected:
                raise ContractError(f"verdict {field} does not match pack")
    elif verdict.source_schema != LEGACY_VERDICT_SCHEMA:
        raise ContractError("a testence/verdict/2 requires a testence/evidence-pack/2")
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
            if pack_schema == "testence/evidence-pack/2" and candidate.name not in artifacts:
                raise ContractError(
                    f"evidence reference is not bound by the pack manifest: {reference!r}"
                )
            pointed = _resolve_pointer(candidate, reference)
            if isinstance(pointed, dict):
                for field in ("run_id", "attempt_id", "proof_id"):
                    if field in pointed and pointed[field] != getattr(verdict, field):
                        raise ContractError(
                            f"evidence event {field} does not belong to verdict attempt: {reference!r}"
                        )


def _validate_against_plan(verdict: Verdict, plan: PlanSpec) -> None:
    if verdict.plan_id != plan.id:
        raise ContractError(
            f"verdict plan_id {verdict.plan_id!r} does not match PlanSpec {plan.id!r}"
        )
    unknown = sorted(set(verdict.claim_ids) - set(plan.claim_ids))
    if unknown:
        raise ContractError("verdict references unknown PlanSpec claim(s): " + ", ".join(unknown))
    if verdict.source_schema != LEGACY_VERDICT_SCHEMA and verdict.plan_digest != plan.digest:
        raise ContractError("verdict plan_digest does not match the exact PlanSpec file")


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
