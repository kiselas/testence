from __future__ import annotations

import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from testence.evidence import RUN_ID_ENV
from testence.export import export_run
from testence.metrics import load_run

ROOT = Path(__file__).parents[1]


def _run_pytest(project: Path, runs: Path, *args: str) -> tuple[subprocess.CompletedProcess[str], list[dict]]:
    runs.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env.pop(RUN_ID_ENV, None)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "src"), value] if (value := env.get("PYTHONPATH")) else [str(ROOT / "src")]
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "testence.pytest_plugin",
            "--testence-runs-root",
            str(runs),
            "--basetemp",
            str(project / ".pytest-tmp"),
            "-q",
            *args,
        ],
        cwd=project,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    run_dirs = [path for path in runs.iterdir() if path.is_dir()]
    assert len(run_dirs) == 1, result.stdout + result.stderr
    events = load_run(run_dirs[0])
    return result, events


def test_lifecycle_records_every_pytest_outcome_without_ex(tmp_path: Path) -> None:
    project = tmp_path / "consumer"
    project.mkdir()
    (project / "test_outcomes.py").write_text(
        """
import pytest

@pytest.fixture
def setup_error():
    raise RuntimeError("setup exploded")

@pytest.fixture
def teardown_error():
    yield
    raise RuntimeError("teardown exploded")

def test_pass():
    assert True

def test_fail():
    assert False, "product mismatch"

def test_setup_error(setup_error):
    pass

def test_teardown_error(teardown_error):
    pass

@pytest.mark.skip(reason="not applicable")
def test_setup_skip():
    pass

def test_call_skip():
    pytest.skip("runtime condition")

@pytest.mark.xfail(reason="known defect")
def test_xfail():
    assert False

@pytest.mark.xfail(reason="fixed unexpectedly")
def test_xpass():
    assert True

@pytest.mark.xfail(reason="must still fail", strict=True)
def test_strict_xpass():
    assert True
""".lstrip(),
        encoding="utf-8",
    )

    runs = tmp_path / "runs"
    junit = project / "junit.xml"
    result, events = _run_pytest(project, runs, "--junitxml", str(junit))

    assert result.returncode == 1
    starts = [event for event in events if event["kind"] == "test.start"]
    ends = {event["test"]: event for event in events if event["kind"] == "test.end"}
    assert len(starts) == len(ends) == 9
    assert ends["test_pass"]["status"] == "passed"
    assert ends["test_fail"]["status"] == "failed"
    assert ends["test_fail"]["phase"] == "call"
    assert ends["test_setup_error"]["status"] == "broken"
    assert ends["test_setup_error"]["phase"] == "setup"
    assert ends["test_teardown_error"]["status"] == "broken"
    assert ends["test_teardown_error"]["phase"] == "teardown"
    assert ends["test_setup_skip"]["status"] == "skipped"
    assert ends["test_call_skip"]["status"] == "skipped"
    assert ends["test_xfail"]["status"] == "skipped"
    assert ends["test_xfail"]["xfail"] is True
    assert ends["test_xpass"]["status"] == "passed"
    assert ends["test_xpass"]["xpass"] is True
    assert ends["test_strict_xpass"]["status"] == "failed"
    phases = [event for event in events if event["kind"] == "test.phase"]
    assert {event["phase"] for event in phases} == {"setup", "call", "teardown"}

    run_end = next(event for event in events if event["kind"] == "run.end")
    assert run_end["run_status"] == "failed"
    assert run_end["passed"] == 2
    assert run_end["failed"] == 2
    assert run_end["broken"] == 2
    assert run_end["skipped"] == 3

    run_dir = next(runs.iterdir())
    allure_dir = tmp_path / "allure"
    export_run(run_dir, "allure", allure_dir)
    allure = {
        doc["name"]: doc
        for path in allure_dir.glob("*-result.json")
        if (doc := json.loads(path.read_text(encoding="utf-8")))
    }
    assert allure["test_pass"]["status"] == "passed"
    assert allure["test_fail"]["status"] == "failed"
    assert allure["test_setup_error"]["status"] == "broken"
    assert allure["test_teardown_error"]["status"] == "broken"
    assert allure["test_call_skip"]["status"] == "skipped"

    ctrf_dir = tmp_path / "ctrf"
    export_run(run_dir, "ctrf", ctrf_dir)
    ctrf = json.loads((ctrf_dir / "ctrf-report.json").read_text(encoding="utf-8"))["results"]
    assert ctrf["summary"] == {
        **{key: ctrf["summary"][key] for key in ("start", "stop")},
        "tests": 9,
        "passed": 2,
        "failed": 4,
        "pending": 0,
        "skipped": 3,
        "other": 0,
    }

    junit_root = ET.parse(junit).getroot()
    junit_suite = junit_root if junit_root.tag == "testsuite" else junit_root.find("testsuite")
    assert junit_suite is not None
    assert junit_suite.attrib["tests"] == "9"
    assert junit_suite.attrib["failures"] == "2"
    assert junit_suite.attrib["errors"] == "2"
    assert junit_suite.attrib["skipped"] == "3"


def test_collection_errors_skips_and_zero_collection_are_recorded(tmp_path: Path) -> None:
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "test_broken.py").write_text("def test_broken(:\n", encoding="utf-8")
    broken_result, broken_events = _run_pytest(broken, tmp_path / "broken-runs")
    assert broken_result.returncode != 0
    assert any(event["kind"] == "collection.error" for event in broken_events)
    assert next(event for event in broken_events if event["kind"] == "run.end")[
        "collection_errors"
    ] == 1

    skipped = tmp_path / "collection-skip"
    skipped.mkdir()
    (skipped / "test_skipped.py").write_text(
        'import pytest\npytest.importorskip("dependency_that_does_not_exist")\n',
        encoding="utf-8",
    )
    skipped_result, skipped_events = _run_pytest(skipped, tmp_path / "skipped-runs")
    assert skipped_result.returncode == 5
    assert any(event["kind"] == "collection.skip" for event in skipped_events)

    empty = tmp_path / "empty"
    empty.mkdir()
    empty_result, empty_events = _run_pytest(empty, tmp_path / "empty-runs")
    assert empty_result.returncode == 5
    collection_end = next(event for event in empty_events if event["kind"] == "collection.end")
    assert collection_end["selected"] == 0
    run_end = next(event for event in empty_events if event["kind"] == "run.end")
    assert run_end["run_status"] == "no_tests"
    assert sum(run_end[status] for status in ("passed", "failed", "broken", "skipped")) == 0


def test_xdist_workers_preserve_one_terminal_event_per_case(tmp_path: Path) -> None:
    project = tmp_path / "parallel-consumer"
    project.mkdir()
    (project / "test_parallel.py").write_text(
        """
import pytest

@pytest.mark.parametrize("value", range(8))
def test_parallel(value):
    assert value >= 0
""".lstrip(),
        encoding="utf-8",
    )

    result, events = _run_pytest(
        project,
        tmp_path / "parallel-runs",
        "-p",
        "xdist.plugin",
        "-n",
        "2",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    starts = [event for event in events if event["kind"] == "test.start"]
    ends = [event for event in events if event["kind"] == "test.end"]
    assert len(starts) == len(ends) == 8
    assert len({event["nodeid"] for event in starts}) == 8
    assert all(event["status"] == "passed" for event in ends)
