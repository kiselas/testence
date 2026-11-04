"""``--testence-schedule longest-first``: the slowest tests start first under xdist.

xdist hands tests out in collection order, so a slow test collected last becomes the
tail of a parallel run. The durations of earlier runs are on disk, in every
``test.end``; the controller reads them and every worker orders its collection by
them, longest first, keeping an ``xdist_group`` together.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from testence.evidence import RUN_ID_ENV
from testence.schedule import durations_from_history, longest_first
from tests.owned_pytest import run_pytest

ROOT = Path(__file__).parents[1]

pytest.importorskip("xdist")


def _history(runs: Path, run_id: str, durations: dict[str, float], **extra: Any) -> None:
    directory = runs / run_id
    directory.mkdir(parents=True)
    lines = [
        json.dumps({"kind": "test.end", "nodeid": nodeid, "duration_ms": ms, **extra})
        for nodeid, ms in durations.items()
    ]
    (directory / "run.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_durations_are_the_median_of_recent_runs(tmp_path):
    _history(tmp_path, "r1", {"t.py::a": 100, "t.py::b": 10})
    _history(tmp_path, "r2", {"t.py::a": 300})
    _history(tmp_path, "r3", {"t.py::a": 200})
    _history(tmp_path, "r4", {"t.py::b": 9_999}, rerun=True)
    _history(tmp_path, "current", {"t.py::b": 9_999})
    durations = durations_from_history(tmp_path, exclude_run="current")
    assert durations == {"t.py::a": 200.0, "t.py::b": 10.0}


def test_longest_first_keeps_groups_together_and_equals_in_order():
    items = ["a", "b", "g1", "c", "g2"]
    durations = {"a": 10, "b": 50, "c": 50, "g1": 30, "g2": 30}
    groups = {"g1": "grp", "g2": "grp"}
    ordered = longest_first(items, durations, nodeid=str, group=groups.get)
    assert ordered == ["g1", "g2", "b", "c", "a"]
    assert longest_first(items, {}, nodeid=str) == items


SUITE = """
import time

import pytest


def test_a_quick(testence_settings):
    time.sleep(0.05)


def test_b_quick(testence_settings):
    time.sleep(0.05)


def test_c_quick(testence_settings):
    time.sleep(0.05)


def test_d_slow(testence_settings):
    time.sleep(0.3)


@pytest.mark.xdist_group("pair")
def test_e_pair(testence_settings):
    time.sleep(0.05)


@pytest.mark.xdist_group("pair")
def test_f_pair(testence_settings):
    time.sleep(0.05)
"""


def _run(project: Path, *args: str) -> tuple[Any, list[dict[str, Any]]]:
    env = os.environ.copy()
    env.pop(RUN_ID_ENV, None)
    env.update(PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTHONPATH=str(ROOT / "src"))
    result = run_pytest(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "testence.pytest_plugin",
            "-p",
            "xdist.plugin",
            "--rootdir",
            str(project),
            "-p",
            "no:cacheprovider",
            "-p",
            "no:randomly",
            "-q",
            *args,
        ],
        cwd=project,
        env=env,
        timeout=300,
    )
    events: list[dict[str, Any]] = []
    newest = max((project / "runs").iterdir(), key=lambda path: path.stat().st_mtime)
    for ledger in newest.glob("run*.jsonl"):
        events += [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    return result, events


def _first_started(events: list[dict[str, Any]]) -> dict[str, str]:
    """The first test each worker started."""
    first: dict[str, tuple[int, str]] = {}
    for event in events:
        if event["kind"] == "test.start":
            worker = event["worker"]
            if worker not in first or event["seq"] < first[worker][0]:
                first[worker] = (event["seq"], event["test"].rsplit("::", 1)[-1])
    return {worker: name for worker, (_seq, name) in first.items()}


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "suite"
    project.mkdir()
    (project / "test_sched.py").write_text(SUITE.lstrip(), encoding="utf-8")
    return project


def test_longest_first_starts_the_slowest_test_first(tmp_path):
    project = _project(tmp_path)
    _history(
        project / "runs",
        "earlier",
        {
            "test_sched.py::test_a_quick": 50,
            "test_sched.py::test_b_quick": 50,
            "test_sched.py::test_c_quick": 50,
            "test_sched.py::test_d_slow": 3_000,
            "test_sched.py::test_e_pair": 50,
            "test_sched.py::test_f_pair": 50,
        },
    )
    result, events = _run(project, "-n", "2", "--testence-schedule", "longest-first")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "test_d_slow" in _first_started(events).values()


def test_longest_first_keeps_an_xdist_group_on_one_worker(tmp_path):
    project = _project(tmp_path)
    _history(
        project / "runs",
        "earlier",
        {
            "test_sched.py::test_a_quick": 50,
            "test_sched.py::test_d_slow": 300,
            "test_sched.py::test_e_pair": 2_000,
            "test_sched.py::test_f_pair": 2_000,
        },
    )
    result, events = _run(
        project,
        "-n",
        "2",
        "--dist",
        "loadgroup",
        "--testence-schedule",
        "longest-first",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    workers = {
        event["test"].rsplit("::", 1)[-1]: event["worker"]
        for event in events
        if event["kind"] == "test.start"
    }
    assert workers["test_e_pair"] == workers["test_f_pair"]
    assert "test_e_pair" in _first_started(events).values()


def test_another_dist_mode_is_refused(tmp_path):
    project = _project(tmp_path)
    result = run_pytest(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "testence.pytest_plugin",
            "-p",
            "xdist.plugin",
            "--rootdir",
            str(project),
            "-q",
            "-n",
            "2",
            "--dist",
            "loadfile",
            "--testence-schedule",
            "longest-first",
        ],
        cwd=project,
        env={
            **os.environ,
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "PYTHONPATH": str(ROOT / "src"),
        },
        timeout=120,
    )
    assert result.returncode != 0
    assert "works with --dist load or loadgroup" in result.stdout + result.stderr
