"""CTRF exporter — one JSON file, and the worked example of the seam (ADR-0013).

CTRF (Common Test Report Format) is the "modern JUnit XML": a single schema-versioned
JSON document that a growing set of CI reporters and dashboards consume. Its test
object has native fields for steps, attachments, the suite path, labels, parameters
and the trace; Testence fills those and keeps only its own identity in ``extra``.

Read this module before writing your own: it is the whole contract in ~40 lines of
logic — two module-level symbols, stdlib only, a pure function of the parsed ledger.

The targeted spec version is pinned in :data:`SPEC_VERSION` — one constant, so
checking it against the published schema is a one-line review, not an audit. The
CTRF specification itself is still at 0.0.0 (``spec/ctrf.md``, schema of 15 August
2026); ``tests/schemas/ctrf.schema.json`` is the copy the goldens are validated
against.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ._model import LoadedRun, Step, Test, copy_attachments, epoch_ms

name = "ctrf"

SPEC_VERSION = "0.0.0"

_STATUS = {
    "pass": "passed",
    "passed": "passed",
    "fail": "failed",
    "failed": "failed",
    "broken": "failed",
    "skipped": "skipped",
    "aborted": "other",
    "not_run": "pending",
}


def export(run: LoadedRun, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    tests: list[dict[str, Any]] = []
    written: list[Path] = []
    browser = str(run.fingerprint.get("browser_channel") or "")
    for test in run.tests:
        files = copy_attachments(run, test, out_dir)
        written.extend(out_dir / item.path for item in files)
        document = _test(test)
        if files:
            document["attachments"] = [
                {"name": item.name, "contentType": item.media_type, "path": item.path}
                for item in files
            ]
        if browser:
            document["browser"] = browser
        tests.append(document)
    doc = {
        "reportFormat": "CTRF",
        "specVersion": SPEC_VERSION,
        "results": {
            "tool": {"name": "testence", "version": run.testence_version},
            "summary": _summary(run),
            "tests": tests,
        },
    }
    target = out_dir / "ctrf-report.json"
    target.write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    return [target, *written]


def _summary(run: LoadedRun) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "tests": len(run.tests),
        "passed": run.passed,
        "failed": run.failed,
        "pending": run.pending,
        "skipped": run.skipped,
        "other": run.other,
        "extra": {
            "testence": {
                "run_id": run.run_id,
                "project_id": run.project_id,
                "run_status": run.run_status,
                "integrity_errors": run.integrity_errors,
                **(
                    {"testplan_unresolved": run.testplan_unresolved}
                    if run.testplan_unresolved
                    else {}
                ),
            }
        },
    }
    # Both are required by the schema. A ledger without run boundaries (a killed
    # run) falls back to its tests' own window, then to 0 — never to an omission.
    starts = [value for test in run.tests if (value := epoch_ms(test.start)) is not None]
    stops = [value for test in run.tests if (value := epoch_ms(test.stop)) is not None]
    start = epoch_ms(run.start)
    stop = epoch_ms(run.stop)
    summary["start"] = start if start is not None else min(starts, default=0)
    summary["stop"] = stop if stop is not None else max(stops, default=summary["start"])
    return summary


def _test(test: Test) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "name": test.nodeid,
        "status": _STATUS.get(test.status, "other"),
        "duration": int(test.duration_ms),
    }
    start, stop = epoch_ms(test.start), epoch_ms(test.stop)
    if start is not None:
        doc["start"] = start
    if stop is not None:
        doc["stop"] = stop
    if test.status != doc["status"]:
        doc["rawStatus"] = test.status
    suite = _suite(test)
    if suite:
        doc["suite"] = suite
    if test.file:
        doc["filePath"] = test.file
    if test.markers:
        doc["tags"] = list(test.markers)
    labels = _labels(test)
    if labels:
        doc["labels"] = labels
    if test.parameters:
        doc["parameters"] = dict(test.parameters)
    if test.failed and test.error:
        doc["message"] = test.error
    if test.failed and test.error_trace:
        doc["trace"] = test.error_trace
    if test.steps:
        doc["steps"] = _steps(test.steps)
    # `extra` is where a format's blind spots go: the step intents keep a flat
    # consumer readable, and the pack path points at the real evidence.
    extra: dict[str, Any] = {}
    extra["testence_identity"] = {
        "project_id": test.project_id,
        "case_id": test.case_id,
        "variant_id": test.variant_id,
        "attempt_id": test.attempt_id,
        "proof_id": test.proof_id,
        "parameters": test.parameters,
    }
    extra["testence_assurance"] = {
        "status": test.assurance,
        "reasons": list(test.assurance_reasons),
    }
    if test.pack_dir:
        extra["evidence_pack"] = test.pack_dir
    if test.oracles:
        extra["oracles"] = test.oracles
    if extra:
        doc["extra"] = extra
    return doc


def _steps(steps: list[Step]) -> list[dict[str, Any]]:
    """The step tree flattened in execution order; ``extra.depth`` keeps the nesting
    a flat list cannot express, so a reader still sees which primitive of a composite
    action broke."""
    flat: list[dict[str, Any]] = []

    def walk(items: list[Step], depth: int) -> None:
        for step in items:
            entry: dict[str, Any] = {
                "name": step.intent or step.step,
                "status": "failed" if step.failed else "passed",
            }
            extra: dict[str, Any] = {"depth": depth, "duration": int(step.duration_ms)}
            if step.target:
                extra["target"] = step.target
            if step.error:
                extra["error"] = step.error
            entry["extra"] = extra
            flat.append(entry)
            walk(step.substeps, depth + 1)

    walk(steps, 0)
    return flat


def _suite(test: Test) -> list[str]:
    """allure-pytest's parentSuite / suite / subSuite when known, else the file path."""
    suite = test.allure.get("suite")
    if isinstance(suite, dict):
        parts = [str(suite[key]) for key in ("parentSuite", "suite", "subSuite") if suite.get(key)]
        if parts:
            return parts
    path = test.nodeid.split("::", 1)[0]
    return [part for part in path.split("/") if part] if path else []


def _labels(test: Test) -> dict[str, Any]:
    """Structured metadata: identity, declared Allure labels and case ids per system."""
    labels: dict[str, Any] = {}
    for key, value in (
        ("case_id", test.case_id),
        ("allure_id", test.allure_id or str(test.allure.get("allure_id") or "")),
        ("owner", test.owner),
        ("risk", test.risk),
    ):
        if value:
            labels[key] = value
    for item in test.allure.get("labels", ()):
        if isinstance(item, dict) and item.get("name") and item.get("value") is not None:
            name, value = str(item["name"]), str(item["value"])
            existing = labels.get(name)
            if existing is None:
                labels[name] = value
            elif isinstance(existing, list):
                existing.append(value)
            elif existing != value:
                labels[name] = [existing, value]
    for system, ids in sorted(test.tms.items()):
        labels[f"tms.{system}"] = list(ids) if len(ids) > 1 else ids[0]
    return labels
