"""A deadline per test (stage 7, T03).

A test that hangs fails with where it hung, and the worker goes on: the next test of
the same process runs and passes. A hang in Python code takes the exception at the
deadline; a call stuck inside the browser driver gets it only once the processes
Testence started are killed, after a grace period.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from testence.deadline import DeadlineExceeded, Watchdog, parse_timeout
from testence.evidence import RUN_ID_ENV
from testence.metrics import load_run
from tests.owned_pytest import run_pytest

ROOT = Path(__file__).parents[1]

SUITE = """
import time
import urllib.parse

import pytest

PAGE = "data:text/html," + urllib.parse.quote("<h1>ready</h1>")


@pytest.mark.testence(timeout_s=1)
def test_a_python_loop_that_never_ends():
    while True:
        time.sleep(0.05)


def test_b_after_the_loop_runs():
    assert True


@pytest.mark.testence(timeout_s=10, anonymous=True)
def test_c_stuck_in_the_driver(testence_engine):
    testence_engine.goto(PAGE)
    testence_engine.eval_js("new Promise(() => {})")


@pytest.mark.testence(anonymous=True)
def test_d_a_browser_after_the_kill(ex):
    ex.goto(PAGE)
    assert ex.text(__import__("testence.engine").engine.Target("css", "h1")) == "ready"


@pytest.mark.testence(timeout_s=30)
def test_e_in_time():
    time.sleep(0.1)
"""


def _run(project: Path, *args: str) -> tuple[subprocess.CompletedProcess[str], list[dict]]:
    env = os.environ.copy()
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["TESTENCE_DEADLINE_GRACE_S"] = "2"
    env.pop(RUN_ID_ENV, None)
    env.pop("PYTEST_XDIST_WORKER", None)
    env.pop("TESTENCE_TEST_TIMEOUT", None)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "src"), value] if (value := env.get("PYTHONPATH")) else [str(ROOT / "src")]
    )
    result = run_pytest(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "testence.pytest_plugin",
            "--rootdir",
            str(project),
            "--basetemp",
            str(project / ".pytest-tmp"),
            "--testence-headless",
            "-q",
            *args,
        ],
        cwd=project,
        env=env,
        timeout=240,
    )
    (run_dir,) = (project / "runs").iterdir()
    return result, load_run(run_dir)


@pytest.fixture(scope="module", params=["fresh", "reuse"])
def outcome(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory):
    project = tmp_path_factory.mktemp(f"deadline-{request.param}")
    (project / "test_hangs.py").write_text(SUITE.lstrip(), encoding="utf-8")
    (project / "testence.json").write_text(json.dumps({"timeout_ms": 5_000}), encoding="utf-8")
    extra = ["--testence-browser-reuse"] if request.param == "reuse" else []
    started = time.monotonic()
    result, events = _run(project, *extra)
    return result, events, time.monotonic() - started


def _end(events: list[dict], name: str) -> dict:
    return next(e for e in events if e["kind"] == "test.end" and e["display_name"] == name)


def test_a_hang_fails_with_where_it_hung_and_the_worker_goes_on(outcome) -> None:
    result, events, _ = outcome
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert _end(events, "test_a_python_loop_that_never_ends")["status"] in ("failed", "broken")
    assert "ran past its 1 s deadline in call" in output
    assert "time.sleep(0.05)" in output
    for name in ("test_b_after_the_loop_runs", "test_d_a_browser_after_the_kill", "test_e_in_time"):
        assert _end(events, name)["status"] == "passed", output
    deadline = {e["test"].rsplit("::", 1)[-1]: e for e in events if e["kind"] == "test.deadline"}
    assert set(deadline) == {"test_a_python_loop_that_never_ends", "test_c_stuck_in_the_driver"}
    loop = deadline["test_a_python_loop_that_never_ends"]
    assert (loop["phase"], loop["killed"]) == ("call", 0)
    assert any("time.sleep(0.05)" in line for line in loop["stack"])


def test_a_call_stuck_in_the_driver_is_ended_by_the_kill(outcome) -> None:
    result, events, elapsed = outcome
    output = result.stdout + result.stderr
    assert _end(events, "test_c_stuck_in_the_driver")["status"] in ("failed", "broken"), output
    stuck = next(
        e
        for e in events
        if e["kind"] == "test.deadline" and e["test"].endswith("test_c_stuck_in_the_driver")
    )
    assert (stuck["phase"], stuck["killed"] >= 1) == ("call", True), stuck
    assert any("eval_js" in line for line in stuck["stack"]), stuck
    assert "browser process tree(s) Testence started were killed" in output
    # 1 s + 10 s deadlines and browser starts: far below the 240 s guard.
    assert elapsed < 120


def test_parse_timeout_accepts_seconds_and_refuses_nonsense() -> None:
    assert parse_timeout("2.5", "x") == 2.5
    assert parse_timeout(None, "x") is None
    assert parse_timeout(0, "x") is None
    for wrong in (True, "soon", -1, 10**6):
        with pytest.raises(ValueError):
            parse_timeout(wrong, "x")


def test_a_watch_stopped_in_time_raises_nothing() -> None:
    watch = Watchdog(0.2, "call", kill=lambda: 0)
    assert watch.stop() is None
    time.sleep(0.4)


def test_a_watch_past_its_deadline_interrupts_this_thread() -> None:
    watch = Watchdog(0.2, "call", kill=lambda: 0, grace=5)
    with pytest.raises(DeadlineExceeded):
        for _ in range(100):
            time.sleep(0.05)
    expiry = watch.stop()
    assert expiry is not None and expiry.phase == "call"
    assert any("time.sleep(0.05)" in line for line in expiry.stack)
