"""Installing Testence must not change a suite that does not use it.

The plugin is registered through the pytest11 entry point, so it loads into every
pytest session of an environment that has the package. A session that no test opts
into writes nothing, and a broken ``testence.json`` does not stop it; a session with
one Testence test records as before, including under xdist.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from testence.evidence import RUN_ID_ENV
from testence.metrics import load_run

ROOT = Path(__file__).parents[1]

UNRELATED = """
def test_arithmetic():
    assert 1 + 1 == 2
"""

USES_TESTENCE = """
def test_arithmetic():
    assert 1 + 1 == 2

def test_records(testence_writer):
    testence_writer.emit("note", text="used Testence")
"""


def _pytest(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env.pop(RUN_ID_ENV, None)
    env.pop("PYTEST_XDIST_WORKER", None)
    # The environment overrides testence.json, and these tests need the file's value.
    env.pop("TESTENCE_DEBUG_PORT", None)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "src"), value] if (value := env.get("PYTHONPATH")) else [str(ROOT / "src")]
    )
    return subprocess.run(
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
            "-q",
            *args,
        ],
        cwd=project,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _project(tmp_path: Path, source: str, settings: dict | None = None) -> Path:
    project = tmp_path / "consumer"
    project.mkdir()
    (project / "test_suite.py").write_text(source.lstrip(), encoding="utf-8")
    if settings is not None:
        (project / "testence.json").write_text(json.dumps(settings), encoding="utf-8")
    return project


def test_a_suite_that_does_not_use_testence_writes_no_run(tmp_path: Path) -> None:
    project = _project(tmp_path, UNRELATED)

    result = _pytest(project)

    assert result.returncode == 0, result.stdout + result.stderr
    assert not (project / "runs").exists()


def test_a_suite_that_does_not_use_testence_writes_no_run_under_xdist(tmp_path: Path) -> None:
    project = _project(tmp_path, UNRELATED)

    result = _pytest(project, "-p", "xdist.plugin", "-n", "2")

    assert result.returncode == 0, result.stdout + result.stderr
    assert not (project / "runs").exists()


def test_one_testence_test_records_the_whole_session(tmp_path: Path) -> None:
    project = _project(tmp_path, USES_TESTENCE)

    result = _pytest(project)

    assert result.returncode == 0, result.stdout + result.stderr
    (run_dir,) = (project / "runs").iterdir()
    events = load_run(run_dir)
    ends = sorted(event["display_name"] for event in events if event["kind"] == "test.end")
    assert ends == ["test_arithmetic", "test_records"]
    assert [event["kind"] for event in events][:2] == ["run.start", "collection.start"]
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "complete"
    assert manifest["selected_count"] == 2


def test_one_testence_test_records_the_whole_session_under_xdist(tmp_path: Path) -> None:
    project = _project(tmp_path, USES_TESTENCE)

    result = _pytest(project, "-p", "xdist.plugin", "-n", "2")

    assert result.returncode == 0, result.stdout + result.stderr
    (run_dir,) = (project / "runs").iterdir()
    assert (run_dir / "run.jsonl").is_file()
    events = load_run(run_dir)
    assert {event["kind"] for event in events} >= {"run.start", "run.end", "test.end"}
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "complete"


def test_a_testence_option_records_a_suite_without_testence_tests(tmp_path: Path) -> None:
    project = _project(tmp_path, UNRELATED)

    result = _pytest(project, "--testence-headless")

    assert result.returncode == 0, result.stdout + result.stderr
    (run_dir,) = (project / "runs").iterdir()
    ends = [event for event in load_run(run_dir) if event["kind"] == "test.end"]
    assert [event["status"] for event in ends] == ["passed"]


def test_the_written_run_end_counts_the_cases_an_early_stop_never_ran(tmp_path: Path) -> None:
    """``run.end`` adds up as written, before any reader reconciles it."""
    project = _project(
        tmp_path,
        """
def test_a(testence_writer):
    assert False

def test_b():
    pass

def test_c():
    pass
""",
    )

    result = _pytest(project, "-x")

    assert result.returncode == 1, result.stdout + result.stderr
    (ledger,) = (project / "runs").glob("*/run.jsonl")
    written = json.loads(ledger.read_text(encoding="utf-8").splitlines()[-1])
    assert written["kind"] == "run.end"
    assert (written["passed"], written["failed"], written["not_run"]) == (0, 1, 2)


def test_broken_settings_do_not_stop_a_suite_that_does_not_use_testence(tmp_path: Path) -> None:
    project = _project(tmp_path, UNRELATED, {"debug_port": 99999})

    result = _pytest(project)

    assert result.returncode == 0, result.stdout + result.stderr
    assert not (project / "runs").exists()


def test_broken_settings_are_one_usage_error_for_a_testence_suite(tmp_path: Path) -> None:
    project = _project(tmp_path, USES_TESTENCE, {"debug_port": 99999})

    result = _pytest(project)
    output = result.stdout + result.stderr

    assert result.returncode == 4, output
    assert "INTERNALERROR" not in output
    assert "invalid Testence settings: debug_port must be" in output


def test_broken_settings_are_one_usage_error_when_asked_to_record(tmp_path: Path) -> None:
    project = _project(tmp_path, UNRELATED, {"debug_port": 99999})

    result = _pytest(project, "--testence-headless")
    output = result.stdout + result.stderr

    assert result.returncode == 4, output
    assert "INTERNALERROR" not in output
    assert "invalid Testence settings" in output


def test_a_second_session_in_one_process_is_judged_on_its_own(tmp_path: Path) -> None:
    """The first session's run id must not make the next one look CLI-started."""
    project = _project(tmp_path, UNRELATED)
    (project / "twice.py").write_text(
        """
import os, sys
import pytest

for attempt in (1, 2):
    code = pytest.main(["-p", "testence.pytest_plugin", "-q", "-p", "no:cacheprovider",
                        "--rootdir", ".", "test_suite.py"])
    assert code == 0, code
    print("run id left behind:", os.environ.get("TESTENCE_RUN_ID"))
""".lstrip(),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env.pop(RUN_ID_ENV, None)
    env["PYTHONPATH"] = str(ROOT / "src")

    result = subprocess.run(
        [sys.executable, "twice.py"], cwd=project, env=env, text=True, capture_output=True
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("run id left behind: None") == 2, result.stdout
    assert not (project / "runs").exists()


CRASHING_WORKERS = """
import os

def pytest_collection_modifyitems(config, items):
    if hasattr(config, "workerinput"):
        os._exit(70)
"""


def test_a_recording_run_whose_every_worker_crashed_keeps_the_controller_ledger(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path, USES_TESTENCE)
    (project / "conftest.py").write_text(CRASHING_WORKERS.lstrip(), encoding="utf-8")

    result = _pytest(project, "-p", "xdist.plugin", "-n", "2", "--testence-headless")

    assert result.returncode != 0, result.stdout + result.stderr
    (run_dir,) = (project / "runs").iterdir()
    kinds = [event["kind"] for event in load_run(run_dir)]
    assert "worker.crash" in kinds
    assert kinds[0] == "run.start"


def test_a_worker_crash_does_not_make_an_unrelated_suite_write_a_run(tmp_path: Path) -> None:
    project = _project(tmp_path, UNRELATED)
    (project / "conftest.py").write_text(CRASHING_WORKERS.lstrip(), encoding="utf-8")

    result = _pytest(project, "-p", "xdist.plugin", "-n", "2")

    assert result.returncode != 0, result.stdout + result.stderr
    assert not (project / "runs").exists()
