"""Metric aggregation over run ledgers.

Field names here are the public metric vocabulary (metrics-as-code):
``step_latency_ms``, ``case_duration_s``, ``suite_duration_min``,
``interaction_flake_rate``, ``evidence_pack_tokens``. Every run is its own benchmark
because timings ride in the ledger; this module only aggregates.

Two counting rules that a metric is worthless without:

**Leaves only.** An ActionMap method composes primitives, so steps nest and a
composite step's duration *contains* its children's. Summing every ``step.end``
counts the same milliseconds twice and can make the step total exceed test time. Only steps
that had no children are a per-interaction latency.

**Same code, or it is not a flake.** A test that goes fail -> pass while it is being
written is not flaky, it is being written. Keying outcomes by (test, code hash)
stops authoring changes from being reported as instability.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from testence import SCHEMA_VERSION, kernels
from testence.evidence import ledger_paths


def percentile(values: list[float], pct: float) -> float | None:
    return kernels.percentiles(values, [pct])[0]


def load_run(run_dir: Path) -> list[dict[str, Any]]:
    """Read a run's ledgers, merged in time order.

    A parallel run has one file per worker (see ``evidence.writer``); a serial run
    has exactly one. Parsing is kernel-dispatched (hot when aggregating many runs).
    """
    events: list[dict[str, Any]] = []
    for path in ledger_paths(run_dir):
        events.extend(kernels.parse_ledger(path.read_bytes()))
    for event in events:
        if event.get("v") != SCHEMA_VERSION:
            raise ValueError(f"unsupported schema version: {event.get('v')!r}")
    # `seq` restarts per process, so it orders within a file, never across them.
    events.sort(key=lambda doc: (doc.get("ts", ""), doc.get("seq", 0)))
    return events


def _is_leaf(doc: dict[str, Any]) -> bool:
    """Whether a step.end is a leaf interaction rather than a composite.

    Ledgers written before the field carry no ``children``; they are counted as
    before (every step), because inventing a value for them would silently rewrite
    history in the other direction.
    """
    return doc.get("children", 0) == 0


def aggregate(run_dirs: list[Path]) -> dict[str, Any]:
    step_ms: list[float] = []
    case_s: list[float] = []
    suite_min: list[float] = []
    pack_tokens: list[int] = []
    #: (test, code hash) -> statuses. The code hash scopes a flake to one version
    #: of the test; see the module docstring.
    outcomes: dict[tuple[str, str], set[str]] = {}

    for run_dir in run_dirs:
        code_of: dict[str, str] = {}
        for doc in load_run(run_dir):
            kind = doc["kind"]
            if kind == "step.end" and doc.get("status") == "ok" and _is_leaf(doc):
                step_ms.append(doc["duration_ms"])
            elif kind == "test.start":
                code_of[doc["test"]] = str(doc.get("code") or "")
            elif kind == "test.end":
                case_s.append(doc["duration_ms"] / 1000)
                key = (doc["test"], code_of.get(doc["test"], ""))
                outcomes.setdefault(key, set()).add(doc["status"])
            elif kind == "run.end":
                suite_min.append(doc["duration_ms"] / 60000)
            elif kind == "pack":
                pack_tokens.append(sum(doc.get("sections_est_tokens", {}).values()))

    flaky = sorted({test for (test, _), statuses in outcomes.items() if len(statuses) > 1})
    tests = {test for test, _ in outcomes}
    step_p50, step_p95 = kernels.percentiles(step_ms, [50, 95])
    case_p50, case_p95 = kernels.percentiles(case_s, [50, 95])
    return {
        "runs": len(run_dirs),
        "kernels": kernels.active_backend(),
        "step_latency_ms": {"p50": step_p50, "p95": step_p95, "n": len(step_ms)},
        "case_duration_s": {"p50": case_p50, "p95": case_p95, "n": len(case_s)},
        "suite_duration_min": {"p50": percentile(suite_min, 50), "n": len(suite_min)},
        "interaction_flake_rate": (round(len(flaky) / len(tests), 4) if tests else None),
        "flaky_tests": flaky,
        "evidence_pack_tokens": {"p95": percentile([float(t) for t in pack_tokens], 95),
                                 "n": len(pack_tokens)},
    }


def write_metrics(run_dirs: list[Path], out: Path) -> dict[str, Any]:
    doc = aggregate(run_dirs)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    return doc
