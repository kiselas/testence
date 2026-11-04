"""``--testence-schedule longest-first``: start the slowest tests first under xdist.

xdist hands tests out in collection order. A suite whose slowest tests sit at the end
finishes on one busy worker while the others idle: the classic tail of a parallel run.
Longest-processing-time-first ordering removes most of it, and the durations are
already on disk: every ``test.end`` of earlier runs records ``duration_ms``.

The controller reads the history once and hands it to every worker, so all workers
reorder their collection identically (xdist refuses differing collections). Under
``--dist loadgroup`` the tests of one ``xdist_group`` stay together and the groups are
ordered by their total duration. Without history nothing is reordered.
"""

from __future__ import annotations

import json
import statistics
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any, TypeVar

SCHEDULES = ("default", "longest-first")
#: Recent runs read for durations, newest first; enough to smooth one slow run.
HISTORY_RUNS = 20
#: Observations of one test kept, newest first; their median is its duration.
OBSERVATIONS = 5

Item = TypeVar("Item")


def durations_from_history(
    runs_root: Path | str, *, exclude_run: str = "", runs: int = HISTORY_RUNS
) -> dict[str, float]:
    """Median ``duration_ms`` of each test over its recent ``test.end`` events.

    Reads the newest ``runs`` run directories under ``runs_root`` (by modification
    time), skipping ``exclude_run`` (the run being started). Repeated attempts
    (``rerun: true``) and tests that did not run are not durations of the test.
    """
    root = Path(runs_root)
    if not root.is_dir():
        return {}
    directories = [path for path in root.iterdir() if path.is_dir() and path.name != exclude_run]
    directories.sort(key=_mtime, reverse=True)
    seen: dict[str, list[float]] = {}
    for directory in directories[:runs]:
        for ledger in sorted(directory.glob("run*.jsonl")):
            for event in _test_ends(ledger):
                nodeid = event.get("nodeid")
                duration = event.get("duration_ms")
                if not isinstance(nodeid, str) or not isinstance(duration, (int, float)):
                    continue
                if event.get("rerun") or event.get("status") in ("skipped", "not_run"):
                    continue
                observed = seen.setdefault(nodeid, [])
                if len(observed) < OBSERVATIONS:
                    observed.append(float(duration))
    return {nodeid: round(statistics.median(values), 1) for nodeid, values in seen.items()}


def longest_first(
    items: Sequence[Item],
    durations: dict[str, float],
    *,
    nodeid: Callable[[Item], str],
    group: Callable[[Item], str | None] = lambda _item: None,
) -> list[Item]:
    """``items`` with the longest work first; the order of equals is kept.

    A unit is one test, or every test of one ``group`` (``xdist_group``), whose
    duration is the sum of its tests. A test without history counts as the median
    known test: neither first nor last by accident.
    """
    if not durations:
        return list(items)
    fallback = statistics.median(durations.values())
    units: dict[str, list[Item]] = {}
    for item in items:
        name = group(item)
        units.setdefault(f"group:{name}" if name else f"test:{nodeid(item)}", []).append(item)

    def cost(members: Iterable[Item]) -> float:
        return sum(durations.get(nodeid(member), fallback) for member in members)

    ordered = sorted(units.values(), key=lambda members: -cost(members))
    return [item for members in ordered for item in members]


def _test_ends(ledger: Path) -> Iterable[dict[str, Any]]:
    try:
        lines = ledger.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    events = []
    for line in lines:
        if '"test.end"' not in line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue  # a torn last line of an interrupted run
        if isinstance(event, dict) and event.get("kind") == "test.end":
            events.append(event)
    return events


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0
