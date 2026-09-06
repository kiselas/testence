"""CTRF exporter — one JSON file, and the worked example of the seam (ADR-0013).

CTRF (Common Test Report Format) is the "modern JUnit XML": a single schema-versioned
JSON document that a growing set of CI reporters and dashboards consume. It carries
no step tree and no attachments, which is exactly why it is useful here — it shows
how little an exporter has to be.

Read this module before writing your own: it is the whole contract in ~40 lines of
logic — two module-level symbols, stdlib only, a pure function of the parsed ledger.

The targeted spec version is pinned in :data:`SPEC_VERSION` — one constant, so
checking it against the published schema is a one-line review, not an audit.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ._model import LoadedRun, Step, Test, epoch_ms

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
    doc = {
        "reportFormat": "CTRF",
        "specVersion": SPEC_VERSION,
        "results": {
            "tool": {"name": "testence", "version": run.testence_version},
            "summary": _summary(run),
            "tests": [_test(test) for test in run.tests],
        },
    }
    target = out_dir / "ctrf-report.json"
    target.write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    return [target]


def _summary(run: LoadedRun) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "tests": len(run.tests),
        "passed": run.passed,
        "failed": run.failed,
        "pending": run.pending,
        "skipped": run.skipped,
        "other": run.other,
    }
    start, stop = epoch_ms(run.start), epoch_ms(run.stop)
    if start is not None:
        summary["start"] = start
    if stop is not None:
        summary["stop"] = stop
    return summary


def _test(test: Test) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "name": test.nodeid,
        "status": _STATUS.get(test.status, "other"),
        "duration": int(test.duration_ms),
    }
    if test.file:
        doc["filePath"] = test.file
    if test.markers:
        doc["tags"] = list(test.markers)
    if test.failed and test.error:
        doc["message"] = test.error
    # `extra` is where a format's blind spots go: the step intents keep a flat
    # consumer readable, and the pack path points at the real evidence.
    extra: dict[str, Any] = {}
    if test.steps:
        extra["steps"] = _intents(test.steps)
    if test.pack_dir:
        extra["evidence_pack"] = test.pack_dir
    if test.oracles:
        extra["oracles"] = test.oracles
    if extra:
        doc["extra"] = extra
    return doc


def _intents(steps: list[Step]) -> list[str]:
    """Flatten the step tree to intent sentences, marking failures.

    Indentation carries the nesting a flat format cannot express, so a reader still
    sees which primitive inside a composite action broke.
    """
    lines: list[str] = []

    def walk(items: list[Step], depth: int) -> None:
        for step in items:
            mark = " [FAILED]" if step.failed else ""
            lines.append(f"{'  ' * depth}{step.intent or step.step}{mark}")
            walk(step.substeps, depth + 1)

    walk(steps, 0)
    return lines
