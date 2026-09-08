"""Proof assurance is evaluated independently from pytest execution outcome."""

from __future__ import annotations

import hashlib
import json
from typing import Any

ASSURANCE_STATUSES = frozenset({"verified", "violated", "inconclusive", "unverified"})
ASSERTION_OUTCOMES = frozenset({"passed", "failed", "inconclusive"})
ASSERTION_ORACLES = frozenset({"ui", "network", "api", "a11y", "visual", "custom"})
ASSURANCE_POLICY_SCHEMA = "testence/assurance-policy/1"

DEFAULT_POLICY = {
    "schema": ASSURANCE_POLICY_SCHEMA,
    "required_assertions": "all",
    "duplicate_assertions": "unverified",
    "missing_assertions": "unverified",
    "optional_assertions_in_denominator": False,
}
POLICY_DIGEST = (
    "sha256:"
    + hashlib.sha256(
        json.dumps(DEFAULT_POLICY, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
)


def assertion_errors(event: dict[str, Any]) -> list[str]:
    required = (
        "assertion_id",
        "claim_id",
        "oracle_kind",
        "outcome",
        "expected",
        "actual",
        "source",
    )
    errors = [field for field in required if field not in event]
    if event.get("outcome") not in ASSERTION_OUTCOMES:
        errors.append("outcome")
    if event.get("oracle_kind") not in ASSERTION_ORACLES:
        errors.append("oracle_kind")
    for field in ("assertion_id", "claim_id", "source"):
        if field in event and (not isinstance(event[field], str) or not event[field]):
            errors.append(field)
    return sorted(set(errors))


def evaluate_attempt(events: list[dict[str, Any]], terminal: dict[str, Any]) -> dict[str, Any]:
    """Return an assurance projection without changing the execution status."""

    execution_status = str(terminal.get("status") or "unknown")
    start = next((event for event in events if event.get("kind") == "test.start"), {})
    declared = {
        str(item.get("id")): item
        for item in start.get("assertions") or ()
        if isinstance(item, dict) and item.get("id")
    }
    inventory = {key: item for key, item in declared.items() if item.get("required", True)}
    observed: dict[str, list[dict[str, Any]]] = {}
    unknown: list[str] = []
    for event in events:
        if event.get("kind") != "assertion":
            continue
        assertion_id = str(event.get("assertion_id") or "")
        if assertion_id not in declared:
            unknown.append(assertion_id or "<missing>")
        observed.setdefault(assertion_id, []).append(event)

    missing = sorted(set(inventory) - set(observed))
    duplicates = sorted(key for key, values in observed.items() if len(values) != 1)
    binding_errors = sorted(
        assertion_id
        for assertion_id, assertion_events in observed.items()
        if assertion_id in declared
        and any(
            event.get("claim_id") != declared[assertion_id].get("claim_id")
            or event.get("oracle_kind") != declared[assertion_id].get("oracle")
            for event in assertion_events
        )
    )
    raw_plan = start.get("plan")
    plan: dict[str, Any] = raw_plan if isinstance(raw_plan, dict) else {}
    digest_errors: list[str] = []
    plan_digest = str(start.get("plan_digest") or "")
    test_digest = str(start.get("test_digest") or "")
    if not plan_digest.startswith("sha256:") or plan.get("digest") != plan_digest:
        digest_errors.append("plan_digest")
    if len(test_digest) != 71 or not test_digest.startswith("sha256:"):
        digest_errors.append("test_digest")
    if start.get("policy_digest") != POLICY_DIGEST:
        digest_errors.append("policy_digest")

    reasons: list[str] = []
    weakenings = sorted(
        {
            str(weakening)
            for event in events
            if event.get("kind") == "step.start"
            for weakening in (event.get("weakenings") or ())
        }
    )
    if weakenings:
        reasons.append("actionability weakened: " + ", ".join(weakenings))
    if not inventory:
        reasons.append("no required assertion inventory is bound")
    if missing:
        reasons.append("missing required assertions: " + ", ".join(missing))
    if duplicates:
        reasons.append("duplicate assertions: " + ", ".join(duplicates))
    if unknown:
        reasons.append("unknown assertions: " + ", ".join(sorted(set(unknown))))
    if binding_errors:
        reasons.append("assertion binding mismatch: " + ", ".join(binding_errors))
    if digest_errors:
        reasons.append("missing or stale proof digests: " + ", ".join(digest_errors))

    valid_events = [
        event
        for assertion_id, assertion_events in observed.items()
        for event in assertion_events
        if assertion_id in declared and assertion_id not in binding_errors
    ]
    if execution_status in {"aborted", "not_run", "skipped"}:
        assurance = "inconclusive"
        reasons.append(f"execution ended as {execution_status}")
    elif any(event.get("outcome") == "failed" for event in valid_events):
        if duplicates or unknown or binding_errors or digest_errors:
            assurance = "unverified"
        else:
            assurance = "violated"
            reasons = ["one or more assertions failed"]
    elif any(event.get("outcome") == "inconclusive" for event in valid_events):
        assurance = "inconclusive"
        reasons = ["one or more assertions were inconclusive"]
    elif execution_status != "passed":
        assurance = "inconclusive"
        reasons = ["execution failed without a decisive assertion"]
    elif duplicates or unknown or binding_errors or digest_errors or weakenings:
        assurance = "unverified"
    else:
        assurance = "unverified" if reasons else "verified"

    return {
        "assurance": assurance,
        "assurance_reasons": reasons,
        "required_assertions": len(inventory),
        "observed_required_assertions": sum(
            1
            for assertion_id, assertion_events in observed.items()
            if assertion_id in inventory
            and assertion_id not in binding_errors
            and len(assertion_events) == 1
            and assertion_events[0].get("outcome") == "passed"
        ),
        "weakenings": weakenings,
    }
