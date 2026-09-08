"""Stable identities shared by the ledger, packs, verdicts and exporters."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

EVIDENCE_SCHEMA = "testence/2"
LEGACY_EVIDENCE_SCHEMAS = frozenset({"testence/1"})
UNKNOWN_PROJECT_ID = "unconfigured"

_PARAM_SUFFIX = re.compile(r"^(?P<case>.*)\[(?P<variant>.*)]$")
_SAFE_ID = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?$")


def _digest(value: str, *, prefix: str) -> str:
    return f"{prefix}-{hashlib.sha256(value.encode('utf-8')).hexdigest()[:20]}"


def validate_identity(value: str, field: str) -> str:
    """Validate a repo-owned public identifier."""

    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise ValueError(
            f"{field} must use lowercase letters, numbers, '.', '_' or '-' and be <=128 chars"
        )
    return value


def source_case_id(nodeid: str) -> str:
    """Deterministic fallback case ID; an explicit ID is required to survive rename."""

    match = _PARAM_SUFFIX.fullmatch(nodeid)
    locator = match.group("case") if match else nodeid
    return _digest(locator, prefix="case")


def parameter_fingerprints(parameters: dict[str, Any]) -> dict[str, str]:
    """Canonical parameter fingerprints without retaining raw values."""

    result: dict[str, str] = {}
    for name, value in sorted(parameters.items(), key=lambda item: str(item[0])):
        try:
            encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError):
            encoded = f"<{type(value).__module__}.{type(value).__qualname__}>"
        result[str(name)] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return result


def variant_id(parameters: dict[str, Any], *, nodeid: str = "") -> tuple[str, dict[str, str]]:
    """Return a stable variant ID and safe, digest-only parameter metadata."""

    fingerprints = parameter_fingerprints(parameters)
    if fingerprints:
        canonical = json.dumps(fingerprints, sort_keys=True, separators=(",", ":"))
        return _digest(canonical, prefix="variant"), fingerprints
    match = _PARAM_SUFFIX.fullmatch(nodeid)
    if match:
        return _digest(match.group("variant"), prefix="variant"), {}
    return "default", {}


def proof_id(run_id: str, case_id: str, variant_id: str, attempt_id: str) -> str:
    return _digest("|".join((run_id, case_id, variant_id, attempt_id)), prefix="proof")


@dataclass(frozen=True)
class TestIdentity:
    project_id: str
    case_id: str
    variant_id: str
    attempt_id: str
    run_id: str
    proof_id: str
    parameters: dict[str, str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "case_id": self.case_id,
            "variant_id": self.variant_id,
            "attempt_id": self.attempt_id,
            "run_id": self.run_id,
            "proof_id": self.proof_id,
            "parameters": dict(self.parameters),
        }


def adapt_event(document: dict[str, Any]) -> dict[str, Any]:
    """Normalize a `/1` or `/2` event to the `/2` reader model.

    Unknown fields are retained. Missing legacy proof fields are marked explicitly;
    they are never inferred as verified evidence.
    """

    event = dict(document)
    schema = event.get("v")
    if schema == EVIDENCE_SCHEMA:
        required = ("project_id", "run_id", "event_id")
        missing = [field for field in required if not event.get(field)]
        if missing:
            raise ValueError("invalid testence/2 event; missing " + ", ".join(missing))
        event.setdefault("run", event["run_id"])
        return event
    if schema not in LEGACY_EVIDENCE_SCHEMAS:
        raise ValueError(f"unsupported schema version: {schema!r}")

    run_id = str(event.get("run") or "legacy-unknown-run")
    locator = str(event.get("nodeid") or event.get("test") or "")
    worker = str(event.get("worker") or "legacy")
    seq = int(event.get("seq") or 0)
    event.update(
        {
            "v": EVIDENCE_SCHEMA,
            "source_schema": schema,
            "project_id": "legacy",
            "run_id": run_id,
            "run": run_id,
            "event_id": f"legacy:{worker}:{seq}",
            "assurance": "unverified",
        }
    )
    if locator:
        legacy_variant, parameters = variant_id({}, nodeid=locator)
        event.setdefault("case_id", source_case_id(locator))
        event.setdefault("variant_id", legacy_variant)
        event.setdefault("attempt_id", "legacy-1")
        event.setdefault("proof_id", "unknown")
        event.setdefault("parameters", parameters)
    return event
