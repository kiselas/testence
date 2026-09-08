"""Build one fail-closed logical run from controller and worker ledgers."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from testence.assurance import evaluate_attempt
from testence.status import normalize_execution_status

_RUN_STATUS_PRIORITY = {
    "passed": 0,
    "no_tests": 1,
    "incomplete": 2,
    "failed": 2,
    "interrupted": 3,
    "usage_error": 4,
    "internal_error": 5,
    "unknown": 6,
}


def _case_key(event: dict[str, Any]) -> str:
    identity = tuple(
        str(event.get(field) or "")
        for field in ("project_id", "case_id", "variant_id", "attempt_id")
    )
    if all(identity):
        return "|".join(identity)
    return str(event.get("nodeid") or event.get("test") or "")


def _display_name(nodeid: str) -> str:
    return nodeid.rsplit("::", 1)[-1] if "::" in nodeid else nodeid


def _logical_run_status(run_ends: list[dict[str, Any]], statuses: Iterable[str]) -> str:
    recorded = max(
        (str(event.get("run_status") or "unknown") for event in run_ends),
        key=lambda status: _RUN_STATUS_PRIORITY.get(status, _RUN_STATUS_PRIORITY["unknown"]),
        default="unknown",
    )
    statuses = set(statuses)
    if {"failed", "broken"} & statuses and _RUN_STATUS_PRIORITY.get(recorded, 6) < 2:
        return "failed"
    if {"aborted", "not_run"} & statuses and recorded == "passed":
        return "incomplete"
    return recorded


def reconcile_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize statuses, synthesize missing terminals, and keep one run end.

    Raw JSONL stays append-only.  This is the common read projection consumed by
    reports, metrics, exporters and the correctness corpus.
    """
    if not events:
        return []

    normalized: list[dict[str, Any]] = []
    run_ends: list[dict[str, Any]] = []
    selected: dict[str, str] = {}
    selected_details: dict[str, dict[str, Any]] = {}
    started: dict[str, dict[str, Any]] = {}
    terminal: dict[str, dict[str, Any]] = {}
    crashes: list[dict[str, Any]] = []
    damage: list[dict[str, Any]] = []
    aliases: dict[str, str] = {}
    alias_identity: dict[str, dict[str, Any]] = {}
    alias_locator: dict[str, str] = {}

    for source in events:
        event = dict(source)
        kind = event.get("kind")
        if kind == "run.end":
            run_ends.append(event)
            continue
        if kind == "collection.end":
            for nodeid in event.get("nodeids") or ():
                key = str(nodeid)
                selected.setdefault(key, _display_name(key))
            for case in event.get("cases") or ():
                if not isinstance(case, dict) or not case.get("nodeid"):
                    continue
                locator = str(case["nodeid"])
                selected[locator] = str(case.get("display_name") or _display_name(locator))
                selected_details[locator] = dict(case)
        if kind == "worker.crash":
            crashes.append(event)
        if kind == "ledger.damage":
            damage.append(event)
        if kind == "test.start":
            key = _case_key(event)
            if key:
                raw_test = str(event.get("test") or key)
                locator = str(event.get("nodeid") or raw_test)
                aliases[raw_test] = key
                alias_locator[raw_test] = locator
                alias_identity[raw_test] = {
                    field: event[field]
                    for field in (
                        "project_id",
                        "case_id",
                        "variant_id",
                        "attempt_id",
                        "proof_id",
                        "parameters",
                    )
                    if field in event
                }
                event.setdefault("nodeid", locator)
                event.setdefault("display_name", _display_name(locator))
                started[key] = event
                selected.setdefault(locator, str(event["display_name"]))
        elif event.get("test"):
            raw_test = str(event["test"])
            if event.get("source_schema") and raw_test in alias_identity:
                event.update(alias_identity[raw_test])
            if raw_test in alias_locator:
                event.setdefault("nodeid", alias_locator[raw_test])
            key = (
                _case_key(event)
                if event.get("case_id") and event.get("attempt_id")
                else str(event.get("nodeid") or aliases.get(raw_test) or raw_test)
            )
            if kind in {"test.phase", "test.end"} and key:
                event.setdefault("nodeid", key)
                locator = str(event.get("nodeid") or raw_test)
                event.setdefault("display_name", selected.get(locator, _display_name(locator)))
            if kind == "test.end":
                event["status"] = normalize_execution_status(event.get("status"))
                terminal[key] = event
        normalized.append(event)

    template = next((event for event in normalized if event.get("kind") == "run.start"), events[0])
    run_id = str(template.get("run_id") or template.get("run") or "")
    version = template.get("v")
    last_seq = max((int(event.get("seq") or 0) for event in events), default=0)
    last_ts = max((str(event.get("ts") or "") for event in events), default="")

    def synthetic(
        nodeid: str,
        status: str,
        reason: str,
        identity: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        nonlocal last_seq
        last_seq += 1
        identity = identity or {}
        case_id = str(identity.get("case_id") or nodeid)
        variant_id = str(identity.get("variant_id") or "default")
        attempt_id = str(identity.get("attempt_id") or "attempt-not-started-1")
        project_id = str(identity.get("project_id") or template.get("project_id") or "legacy")
        event: dict[str, Any] = {
            "v": version,
            "run": run_id,
            "run_id": run_id,
            "project_id": project_id,
            "case_id": case_id,
            "variant_id": variant_id,
            "attempt_id": attempt_id,
            "proof_id": str(identity.get("proof_id") or "unknown"),
            "parameters": dict(identity.get("parameters") or {}),
            "event_id": f"reconcile:{last_seq}",
            "seq": last_seq,
            "ts": last_ts,
            "kind": "test.end",
            "test": nodeid,
            "nodeid": nodeid,
            "display_name": selected.get(nodeid, _display_name(nodeid)),
            "status": status,
            "phase": "unknown",
            "duration_ms": 0.0,
            "error": reason,
            "synthetic": True,
        }
        terminal[_case_key(event)] = event
        return event

    crash_reason = "; ".join(str(event.get("error") or "worker crashed") for event in crashes)
    observed_nodeids = {
        str(event.get("nodeid") or event.get("test") or "")
        for event in (*started.values(), *terminal.values())
    }
    for nodeid in selected:
        if nodeid in observed_nodeids:
            continue
        normalized.append(
            synthetic(
                nodeid,
                "not_run",
                "selected test was not started",
                selected_details.get(nodeid),
            )
        )

    # A legacy truncated ledger may have no collection inventory.
    for case_key, start_event in started.items():
        if case_key not in terminal:
            nodeid = str(start_event.get("nodeid") or start_event.get("test") or case_key)
            selected.setdefault(
                nodeid, str(start_event.get("display_name") or _display_name(nodeid))
            )
            normalized.append(
                synthetic(
                    nodeid,
                    "aborted",
                    crash_reason or "test started but no terminal event was recorded",
                    start_event,
                )
            )

    attempt_events: dict[str, list[dict[str, Any]]] = {}
    for event in normalized:
        if event.get("test"):
            attempt_events.setdefault(_case_key(event), []).append(event)
    for case_key, terminal_event in terminal.items():
        terminal_event.update(evaluate_attempt(attempt_events.get(case_key, []), terminal_event))

    if run_ends:
        final_event: dict[str, Any] = max(
            run_ends,
            key=lambda event: _RUN_STATUS_PRIORITY.get(
                str(event.get("run_status") or "unknown"), _RUN_STATUS_PRIORITY["unknown"]
            ),
        )
        final = dict(final_event)
    else:
        final = {
            "v": version,
            "run": run_id,
            "run_id": run_id,
            "project_id": str(template.get("project_id") or "legacy"),
            "event_id": f"reconcile:{last_seq + 1}",
            "seq": last_seq + 1,
            "ts": last_ts,
            "kind": "run.end",
            "exit_code": -1,
            "synthetic": True,
            "error": "run has no terminal event",
        }
    counts = {
        status: 0 for status in ("passed", "failed", "broken", "skipped", "aborted", "not_run")
    }
    for event in terminal.values():
        counts[normalize_execution_status(event.get("status"))] += 1
    final.update(counts)
    status_values = [status for status, count in counts.items() for _ in range(count)]
    final["run_status"] = _logical_run_status(run_ends, status_values)
    # A missing run.end must never become a successful logical run.
    if not run_ends:
        final["run_status"] = "incomplete"
    if damage:
        final["run_status"] = "incomplete"
        final["integrity_errors"] = [
            {
                "code": str(event.get("integrity_code") or "unknown"),
                "error": str(event.get("error") or "ledger integrity failure"),
                **({"path": event["path"]} if event.get("path") else {}),
            }
            for event in damage
        ]
    normalized.append(final)
    return normalized
