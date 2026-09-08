"""Integrity-aware reader for controller and worker evidence ledgers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from testence import kernels
from testence.assurance import assertion_errors
from testence.contracts.versions import RUN_MANIFEST_SCHEMA
from testence.identity import EVIDENCE_SCHEMA, adapt_event

from .writer import ledger_paths


class LedgerIntegrityError(ValueError):
    """A ledger cannot be safely interpreted, even as an incomplete run."""


@dataclass(frozen=True)
class IntegrityIssue:
    code: str
    detail: str
    path: str | None = None


def _parse_complete_prefix(path: Path) -> tuple[list[dict[str, Any]], list[IntegrityIssue]]:
    data = path.read_bytes()
    issues: list[IntegrityIssue] = []
    if not data:
        return [], [IntegrityIssue("empty_ledger", "ledger is empty", path.name)]

    complete = data
    if not data.endswith(b"\n"):
        boundary = data.rfind(b"\n")
        complete = data[: boundary + 1] if boundary >= 0 else b""
        dropped = data[boundary + 1 :]
        issues.append(
            IntegrityIssue(
                "torn_tail",
                f"ignored {len(dropped)} unterminated byte(s) "
                f"(sha256:{hashlib.sha256(dropped).hexdigest()})",
                path.name,
            )
        )
    if not complete.strip():
        return [], issues
    try:
        parsed = kernels.parse_ledger(complete)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise LedgerIntegrityError(f"{path.name}: corrupt complete JSONL record: {exc}") from exc
    events: list[dict[str, Any]] = []
    for index, document in enumerate(parsed, start=1):
        try:
            events.append(adapt_event(document))
        except (TypeError, ValueError) as exc:
            raise LedgerIntegrityError(f"{path.name}: event {index}: {exc}") from exc
    return events, issues


def _manifest_issues(
    run_dir: Path,
    paths: list[Path],
    events: list[dict[str, Any]],
) -> list[IntegrityIssue]:
    manifest_path = run_dir / "manifest.json"
    current_schema = any(event.get("source_schema") is None for event in events)
    if not manifest_path.is_file():
        return (
            [IntegrityIssue("missing_manifest", "testence/2 run has no run manifest")]
            if current_schema
            else []
        )
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [IntegrityIssue("invalid_manifest", f"run manifest cannot be read: {exc}")]
    if not isinstance(document, dict):
        return [IntegrityIssue("invalid_manifest", "run manifest must be an object")]

    issues: list[IntegrityIssue] = []
    if document.get("schema") != RUN_MANIFEST_SCHEMA:
        issues.append(
            IntegrityIssue(
                "manifest_schema",
                f"unsupported run manifest schema: {document.get('schema')!r}",
            )
        )
    status = document.get("status")
    if status != "complete":
        issues.append(IntegrityIssue("run_not_complete", f"manifest status is {status!r}"))

    run_ids = {str(event.get("run_id")) for event in events if event.get("run_id")}
    project_ids = {str(event.get("project_id")) for event in events if event.get("project_id")}
    if run_ids and document.get("run_id") not in run_ids:
        issues.append(IntegrityIssue("manifest_run_id", "manifest run_id does not match ledgers"))
    if project_ids and document.get("project_id") not in project_ids:
        issues.append(
            IntegrityIssue("manifest_project_id", "manifest project_id does not match ledgers")
        )

    entries = document.get("ledgers")
    if not isinstance(entries, list):
        issues.append(IntegrityIssue("manifest_ledgers", "manifest ledgers must be an array"))
        return issues
    expected: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            issues.append(IntegrityIssue("manifest_entry", "manifest has an invalid ledger entry"))
            continue
        name = entry["path"]
        if name in expected:
            issues.append(IntegrityIssue("manifest_duplicate", f"duplicate manifest entry: {name}"))
        expected[name] = entry
    actual = {path.name: path for path in paths}
    if set(expected) != set(actual):
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        issues.append(
            IntegrityIssue(
                "manifest_shards",
                f"ledger set mismatch; missing={missing}, unlisted={extra}",
            )
        )
    for name in sorted(set(expected) & set(actual)):
        content = actual[name].read_bytes()
        entry = expected[name]
        digest = hashlib.sha256(content).hexdigest()
        if entry.get("bytes") != len(content) or entry.get("sha256") != digest:
            issues.append(IntegrityIssue("manifest_digest", "ledger size or digest mismatch", name))
    return issues


def _event_issues(events: list[dict[str, Any]]) -> list[IntegrityIssue]:
    issues: list[IntegrityIssue] = []
    run_ids = {str(event.get("run_id")) for event in events if event.get("run_id")}
    project_ids = {str(event.get("project_id")) for event in events if event.get("project_id")}
    if len(run_ids) > 1:
        issues.append(IntegrityIssue("mixed_run_ids", f"multiple run IDs: {sorted(run_ids)}"))
    if len(project_ids) > 1:
        issues.append(
            IntegrityIssue("mixed_project_ids", f"multiple project IDs: {sorted(project_ids)}")
        )

    seen_event_ids: set[str] = set()
    terminal_attempts: set[tuple[str, str, str, str]] = set()
    for event in events:
        event_id = str(event.get("event_id") or "")
        if event_id in seen_event_ids:
            issues.append(IntegrityIssue("duplicate_event_id", f"duplicate event_id: {event_id}"))
        seen_event_ids.add(event_id)
        if event.get("kind") == "assertion" and (errors := assertion_errors(event)):
            issues.append(
                IntegrityIssue(
                    "invalid_assertion",
                    "assertion has invalid field(s): " + ", ".join(errors),
                )
            )
        if event.get("kind") != "test.end":
            continue
        identity = (
            str(event.get("project_id") or ""),
            str(event.get("case_id") or ""),
            str(event.get("variant_id") or ""),
            str(event.get("attempt_id") or ""),
        )
        if all(identity):
            if identity in terminal_attempts:
                issues.append(
                    IntegrityIssue(
                        "duplicate_terminal",
                        "attempt has more than one terminal test.end: " + "|".join(identity),
                    )
                )
            terminal_attempts.add(identity)
    return issues


def _damage_events(
    events: list[dict[str, Any]], run_dir: Path, issues: list[IntegrityIssue]
) -> list[dict[str, Any]]:
    if not issues:
        return []
    template = events[0] if events else {}
    run_id = str(template.get("run_id") or run_dir.name or "unknown-run")
    project_id = str(template.get("project_id") or "unconfigured")
    last_seq = max((int(event.get("seq") or 0) for event in events), default=0)
    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return [
        {
            "v": EVIDENCE_SCHEMA,
            "run": run_id,
            "run_id": run_id,
            "project_id": project_id,
            "worker": "reader",
            "event_id": f"reader:{last_seq + index}",
            "seq": last_seq + index,
            "ts": now,
            "kind": "ledger.damage",
            "integrity_code": issue.code,
            "error": issue.detail,
            **({"path": issue.path} if issue.path else {}),
        }
        for index, issue in enumerate(issues, start=1)
    ]


def read_run_ledgers(run_dir: Path | str) -> list[dict[str, Any]]:
    """Read valid records and attach explicit damage events for recoverable faults."""

    root = Path(run_dir)
    paths = ledger_paths(root)
    if not paths:
        return _damage_events(
            [], root, [IntegrityIssue("missing_ledgers", "run has no contained ledger files")]
        )

    events: list[dict[str, Any]] = []
    issues: list[IntegrityIssue] = []
    for path in paths:
        parsed, path_issues = _parse_complete_prefix(path)
        events.extend(parsed)
        issues.extend(path_issues)
    issues.extend(_event_issues(events))
    issues.extend(_manifest_issues(root, paths, events))
    events.extend(_damage_events(events, root, issues))
    # ``seq`` restarts per process and is only a stable within-shard order.
    events.sort(key=lambda document: (str(document.get("ts") or ""), int(document.get("seq") or 0)))
    return events
