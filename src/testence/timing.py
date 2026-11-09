"""Where a run's time went: setup, call and teardown per test, API calls and waits.

``testence timing RUN_DIR`` answers the question a slow suite asks first: is the time
in preparing data (setup), in the case itself (call) or in cleaning up (teardown), how
much of it is the test's own API calls and how much is waiting for the page. With a
second run it compares the two, test by test. Under xdist the phases of the workers
run side by side, so their sum exceeds the wall time; the wall time comes from
``run.end``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA = "testence/timing/1"
PHASES = ("setup", "call", "teardown")


@dataclass
class TestTiming:
    test: str
    status: str = ""
    phases: dict[str, float] = field(default_factory=dict)
    api_calls: int = 0
    api_ms: float = 0.0
    waited_ms: float = 0.0

    @property
    def total_ms(self) -> float:
        return sum(self.phases.values())


def load(run_dir: Path | str) -> dict[str, Any]:
    """The timing of one run, as a ``testence/timing/1`` document."""
    from testence.metrics import load_run

    events = load_run(Path(run_dir))
    tests: dict[str, TestTiming] = {}
    wall_ms: float | None = None
    run_id = ""

    def of(event: dict[str, Any]) -> TestTiming | None:
        name = event.get("nodeid") or event.get("test")
        if not name:
            return None
        return tests.setdefault(str(name), TestTiming(str(name)))

    for event in events:
        kind = event.get("kind")
        if kind == "run.start":
            run_id = str(event.get("run_id") or event.get("run") or run_id)
        elif kind == "run.end":
            wall_ms = float(event.get("duration_ms") or 0.0)
        elif kind == "test.phase":
            timing = of(event)
            phase = str(event.get("phase") or "")
            if timing is not None and phase in PHASES:
                timing.phases[phase] = timing.phases.get(phase, 0.0) + float(
                    event.get("duration_ms") or 0.0
                )
        elif kind == "api.request":
            timing = of(event)
            if timing is not None:
                timing.api_calls += 1
                timing.api_ms += float(event.get("duration_ms") or 0.0)
        elif kind == "test.waits":
            timing = of(event)
            if timing is not None:
                timing.waited_ms += float(event.get("waited_ms") or 0.0)
        elif kind == "test.end":
            timing = of(event)
            if timing is not None:
                timing.status = str(event.get("status") or "")
    rows = sorted(tests.values(), key=lambda t: t.total_ms, reverse=True)
    totals = {phase: round(sum(t.phases.get(phase, 0.0) for t in rows), 1) for phase in PHASES}
    return {
        "schema": SCHEMA,
        "run_id": run_id,
        "run_dir": str(run_dir),
        "wall_ms": wall_ms,
        "tests": len(rows),
        "phases_ms": totals,
        "api": {
            "calls": sum(t.api_calls for t in rows),
            "ms": round(sum(t.api_ms for t in rows), 1),
        },
        "waited_ms": round(sum(t.waited_ms for t in rows), 1),
        "by_test": [
            {
                "test": t.test,
                "status": t.status,
                "ms": round(t.total_ms, 1),
                **{phase: round(t.phases.get(phase, 0.0), 1) for phase in PHASES},
                "api_calls": t.api_calls,
                "api_ms": round(t.api_ms, 1),
                "waited_ms": round(t.waited_ms, 1),
            }
            for t in rows
        ],
    }


def compare(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    """Test by test, what the second run took compared with the first."""
    before = {row["test"]: row for row in first["by_test"]}
    after = {row["test"]: row for row in second["by_test"]}
    rows = []
    for test in sorted(set(before) | set(after)):
        a, b = before.get(test), after.get(test)
        rows.append(
            {
                "test": test,
                "before_ms": a["ms"] if a else None,
                "after_ms": b["ms"] if b else None,
                "delta_ms": round(b["ms"] - a["ms"], 1) if a and b else None,
            }
        )
    rows.sort(key=lambda row: abs(row["delta_ms"] or 0.0), reverse=True)
    return {
        "schema": SCHEMA,
        "before": {
            key: first[key] for key in ("run_id", "wall_ms", "phases_ms", "api", "waited_ms")
        },
        "after": {
            key: second[key] for key in ("run_id", "wall_ms", "phases_ms", "api", "waited_ms")
        },
        "by_test": rows,
    }


def _s(ms: float | None) -> str:
    return "-" if ms is None else f"{ms / 1000:.1f} s"


def render(document: dict[str, Any], *, top: int = 15) -> str:
    """A terminal view of :func:`load` or :func:`compare`."""
    lines: list[str] = []
    if "before" in document:
        before, after = document["before"], document["after"]
        lines.append(f"{before['run_id']} -> {after['run_id']}")
        lines.append(f"  wall      {_s(before['wall_ms'])} -> {_s(after['wall_ms'])}")
        for phase in PHASES:
            lines.append(
                f"  {phase:<9} {_s(before['phases_ms'][phase])} -> {_s(after['phases_ms'][phase])}"
            )
        lines.append(
            f"  api       {before['api']['calls']} calls {_s(before['api']['ms'])} -> "
            f"{after['api']['calls']} calls {_s(after['api']['ms'])}"
        )
        lines.append(f"  waits     {_s(before['waited_ms'])} -> {_s(after['waited_ms'])}")
        lines.append("largest changes:")
        for row in document["by_test"][:top]:
            delta = row["delta_ms"]
            shown = (
                "new"
                if row["before_ms"] is None
                else "gone"
                if row["after_ms"] is None
                else (f"{delta / 1000:+.1f} s")
            )
            lines.append(
                f"  {shown:>9}  {_s(row['before_ms'])} -> {_s(row['after_ms'])}  {row['test']}"
            )
        return "\n".join(lines)
    phases = document["phases_ms"]
    lines.append(f"{document['run_id']}: {document['tests']} tests, wall {_s(document['wall_ms'])}")
    lines.append(
        "  setup {}, call {}, teardown {} (summed over tests)".format(
            _s(phases["setup"]), _s(phases["call"]), _s(phases["teardown"])
        )
    )
    lines.append(
        f"  api: {document['api']['calls']} calls, {_s(document['api']['ms'])}; "
        f"waiting for the page: {_s(document['waited_ms'])}"
    )
    lines.append("slowest tests (setup / call / teardown, api, waits):")
    for row in document["by_test"][:top]:
        lines.append(
            f"  {_s(row['ms']):>8}  {_s(row['setup'])} / {_s(row['call'])} / {_s(row['teardown'])}"
            f", {row['api_calls']} api {_s(row['api_ms'])}, waits {_s(row['waited_ms'])}"
            f"  {row['test']}"
        )
    return "\n".join(lines)
