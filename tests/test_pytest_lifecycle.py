from __future__ import annotations

import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from testence.evidence import RUN_ID_ENV
from testence.export import export_run
from testence.metrics import load_run

ROOT = Path(__file__).parents[1]


def _run_pytest(
    project: Path, runs: Path, *args: str
) -> tuple[subprocess.CompletedProcess[str], list[dict]]:
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
            "--rootdir",
            str(project),
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
    ends = {event["display_name"]: event for event in events if event["kind"] == "test.end"}
    assert len(starts) == len(ends) == 9
    assert len({event["event_id"] for event in events}) == len(events)
    assert all(event["v"] == "testence/2" for event in events)
    assert all(
        event.get("project_id")
        and event.get("case_id")
        and event.get("variant_id")
        and event.get("attempt_id")
        and event.get("proof_id")
        for event in starts
    )
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
    assert ends["test_strict_xpass"]["xpass"] is True
    phases = [event for event in events if event["kind"] == "test.phase"]
    assert {event["phase"] for event in phases} == {"setup", "call", "teardown"}

    run_end = next(event for event in events if event["kind"] == "run.end")
    assert run_end["run_status"] == "failed"
    assert "integrity_errors" not in run_end
    assert run_end["passed"] == 2
    assert run_end["failed"] == 2
    assert run_end["broken"] == 2
    assert run_end["skipped"] == 3

    run_dir = next(runs.iterdir())
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == "testence/run-manifest/2"
    assert manifest["status"] == "complete"
    assert manifest["selected_count"] == 9
    assert {entry["path"] for entry in manifest["ledgers"]} == {"run.jsonl"}
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
    assert {
        key: ctrf["summary"][key]
        for key in ("tests", "passed", "failed", "pending", "skipped", "other")
    } == {"tests": 9, "passed": 2, "failed": 4, "pending": 0, "skipped": 3, "other": 0}
    assert ctrf["summary"]["extra"]["testence"]["run_status"] == "failed"

    junit_root = ET.parse(junit).getroot()
    junit_suite = junit_root if junit_root.tag == "testsuite" else junit_root.find("testsuite")
    assert junit_suite is not None
    # pytest 8 counts a call+teardown-error case twice in the suite-level ``tests``
    # attribute even though it emits one testcase element. Testence's ledger and both
    # exporters retain nine case identities; pytest 9 also reports nine at suite level.
    assert len(junit_suite.findall("testcase")) == 9
    assert junit_suite.attrib["tests"] == ("10" if pytest.version_tuple < (9, 0) else "9")
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
    assert (
        next(event for event in broken_events if event["kind"] == "run.end")["collection_errors"]
        == 1
    )

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


def test_duplicate_display_names_remain_distinct_exported_cases(tmp_path: Path) -> None:
    project = tmp_path / "duplicate-consumer"
    (project / "a").mkdir(parents=True)
    (project / "b").mkdir()
    (project / "a" / "test_a.py").write_text(
        "def test_save():\n    assert False, 'first case fails'\n", encoding="utf-8"
    )
    (project / "b" / "test_b.py").write_text(
        "def test_save():\n    assert True\n", encoding="utf-8"
    )

    result, events = _run_pytest(project, tmp_path / "duplicate-runs")

    assert result.returncode == 1
    ends = [event for event in events if event["kind"] == "test.end"]
    assert len(ends) == 2
    assert len({event["nodeid"] for event in ends}) == 2
    assert {event["status"] for event in ends} == {"failed", "passed"}

    run_dir = next((tmp_path / "duplicate-runs").iterdir())
    ctrf_dir = tmp_path / "duplicate-ctrf"
    export_run(run_dir, "ctrf", ctrf_dir)
    ctrf = json.loads((ctrf_dir / "ctrf-report.json").read_text(encoding="utf-8"))["results"]
    assert ctrf["summary"]["tests"] == 2
    assert ctrf["summary"]["passed"] == 1
    assert ctrf["summary"]["failed"] == 1
    assert len({test["name"] for test in ctrf["tests"]}) == 2


def test_early_stop_records_the_unstarted_selected_scope(tmp_path: Path) -> None:
    project = tmp_path / "maxfail-consumer"
    project.mkdir()
    (project / "test_cases.py").write_text(
        """
def test_a():
    assert False

def test_b():
    pass

def test_c():
    pass
""".lstrip(),
        encoding="utf-8",
    )

    result, events = _run_pytest(project, tmp_path / "maxfail-runs", "-x")

    assert result.returncode == 1
    ends = {event["display_name"]: event for event in events if event["kind"] == "test.end"}
    assert ends["test_a"]["status"] == "failed"
    assert ends["test_b"]["status"] == "not_run"
    assert ends["test_c"]["status"] == "not_run"
    run_end = next(event for event in events if event["kind"] == "run.end")
    assert run_end["failed"] == 1
    assert run_end["not_run"] == 2


def test_keyboard_interrupt_aborts_started_case_and_marks_remainder_not_run(
    tmp_path: Path,
) -> None:
    project = tmp_path / "interrupt-consumer"
    project.mkdir()
    (project / "test_cases.py").write_text(
        """
def test_a():
    raise KeyboardInterrupt()

def test_b():
    pass
""".lstrip(),
        encoding="utf-8",
    )

    result, events = _run_pytest(project, tmp_path / "interrupt-runs")

    assert result.returncode == 2
    ends = {event["display_name"]: event for event in events if event["kind"] == "test.end"}
    assert ends["test_a"]["status"] == "aborted"
    assert ends["test_b"]["status"] == "not_run"
    run_end = next(event for event in events if event["kind"] == "run.end")
    assert run_end["run_status"] == "interrupted"
    assert run_end["aborted"] == 1
    assert run_end["not_run"] == 1


def test_worker_crash_cannot_export_as_a_green_run(tmp_path: Path) -> None:
    project = tmp_path / "crash-consumer"
    project.mkdir()
    (project / "test_cases.py").write_text(
        """
import os

def test_a():
    os._exit(7)

def test_b():
    pass
""".lstrip(),
        encoding="utf-8",
    )

    result, events = _run_pytest(
        project,
        tmp_path / "crash-runs",
        "-p",
        "xdist.plugin",
        "-n",
        "2",
        "--max-worker-restart=0",
    )

    assert result.returncode != 0
    crash = next(event for event in events if event["kind"] == "worker.crash")
    assert crash["worker"] == "controller"
    assert crash["crashed_worker"].startswith("gw")
    ends = {event["display_name"]: event for event in events if event["kind"] == "test.end"}
    assert ends["test_a"]["status"] == "aborted"
    assert ends["test_b"]["status"] == "passed"
    run_end = next(event for event in events if event["kind"] == "run.end")
    assert run_end["run_status"] == "failed"
    assert run_end["aborted"] == 1

    run_dir = next((tmp_path / "crash-runs").iterdir())
    ctrf_dir = tmp_path / "crash-ctrf"
    export_run(run_dir, "ctrf", ctrf_dir)
    ctrf = json.loads((ctrf_dir / "ctrf-report.json").read_text(encoding="utf-8"))["results"]
    assert ctrf["summary"]["tests"] == 2
    assert ctrf["summary"]["passed"] == 1
    assert ctrf["summary"]["failed"] == 1
    assert ctrf["summary"]["other"] == 0


def test_xdist_restart_keeps_replacement_worker_shards_in_the_run(tmp_path: Path) -> None:
    project = tmp_path / "restart-consumer"
    project.mkdir()
    (project / "test_cases.py").write_text(
        """
import os
import time

def test_a_crashes():
    os._exit(7)

def test_b():
    time.sleep(0.2)

def test_c():
    time.sleep(0.2)

def test_d():
    time.sleep(0.2)
""".lstrip(),
        encoding="utf-8",
    )

    result, events = _run_pytest(
        project,
        tmp_path / "restart-runs",
        "-p",
        "xdist.plugin",
        "-n",
        "2",
        "--max-worker-restart=1",
    )

    assert result.returncode != 0
    ends = {event["display_name"]: event for event in events if event["kind"] == "test.end"}
    assert ends["test_a_crashes"]["status"] == "aborted"
    assert {ends[name]["status"] for name in ("test_b", "test_c", "test_d")} == {"passed"}
    assert any(event.get("worker") == "gw2" for event in events), result.stdout + result.stderr
    final = next(event for event in events if event["kind"] == "run.end")
    assert final["run_status"] == "failed"
    assert "integrity_errors" not in final


def test_required_assertion_controls_assurance_without_changing_pytest_status(
    tmp_path: Path,
) -> None:
    project = tmp_path / "assurance-consumer"
    project.mkdir()
    (project / "plan.md").write_text(
        """
# Persistence proof

```testence-planspec
{
  "schema": "testence/planspec/2",
  "project_id": "assurance-consumer",
  "id": "widgets.create",
  "title": "Create widget",
  "owner": "qa-platform",
  "requirements": [{"id": "REQ-42", "url": "https://tms.example/REQ-42"}],
  "issues": [{"id": "BUG-42", "url": "https://issues.example/BUG-42"}],
  "claims": [{
    "id": "widgets.create.persisted",
    "statement": "The API returns the created widget.",
    "oracles": ["api"],
    "required": true
  }],
  "assertions": [{
    "id": "assert.widget.persisted",
    "claim_id": "widgets.create.persisted",
    "oracle": "api",
    "required": true
  }],
  "scenarios": [{
    "id": "create-widget",
    "title": "Create one widget",
    "claims": ["widgets.create.persisted"],
    "risk": "critical"
  }]
}
```
""".lstrip(),
        encoding="utf-8",
    )
    (project / "test_assurance.py").write_text(
        """
import pytest

from testence.oracle import verify

MARK = pytest.mark.testence(
    plan="plan.md",
    case_id="create-widget",
    claims=["widgets.create.persisted"],
    allure_id="314",
)

@MARK
def test_pass_without_proof():
    pass

@MARK
def test_pass_with_proof(testence_writer, request):
    verify(
        testence_writer,
        request.node.nodeid,
        "persisted widget",
        {"id": 42},
        {"id": 42},
        assertion_id="assert.widget.persisted",
        claim_id="widgets.create.persisted",
    )
""".lstrip(),
        encoding="utf-8",
    )

    result, events = _run_pytest(project, tmp_path / "assurance-runs")

    assert result.returncode == 0, result.stdout + result.stderr
    ends = {event["display_name"]: event for event in events if event["kind"] == "test.end"}
    assert ends["test_pass_without_proof"]["status"] == "passed"
    assert ends["test_pass_without_proof"]["assurance"] == "unverified"
    assert ends["test_pass_with_proof"]["status"] == "passed"
    assert ends["test_pass_with_proof"]["assurance"] == "verified"
    start = next(
        event
        for event in events
        if event["kind"] == "test.start" and event["display_name"] == "test_pass_with_proof"
    )
    assert start["owner"] == "qa-platform"
    assert start["allure_id"] == "314"
    assert start["risk"] == "critical"
    assert start["requirements"] == [{"id": "REQ-42", "url": "https://tms.example/REQ-42"}]
    assert start["issues"] == [{"id": "BUG-42", "url": "https://issues.example/BUG-42"}]
    assertion = next(event for event in events if event["kind"] == "assertion")
    assert assertion["source"].startswith("test_assurance.py:")
    assert assertion["expected"] == assertion["actual"] == {"id": 42}
