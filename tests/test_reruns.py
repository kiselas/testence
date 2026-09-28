"""``--testence-reruns``: every attempt is its own recorded attempt.

A failed test is repeated inside one ``pytest_runtest_protocol``. Recorded as one
attempt, a pass after a repeat looked exactly like a clean pass, and the failure pack of
the first attempt was attached to the final passed result (launch-hardening audit
A1-05, stage 4 plan L12 item 8). Testence repeats tests itself so that the runner has
no dependency outside ADR-0007's licences.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from testence.evidence import RUN_ID_ENV
from testence.metrics import load_run

ROOT = Path(__file__).parents[1]

FLAKY = """
import urllib.parse
from pathlib import Path

from testence.engine import Target

PAGE = "data:text/html," + urllib.parse.quote("<p id=state>ready</p>")
COUNTER = Path(__file__).with_name("attempts.txt")


def test_flaky_once(ex):
    attempt = int(COUNTER.read_text()) + 1 if COUNTER.exists() else 1
    COUNTER.write_text(str(attempt))
    ex.goto(PAGE, intent="open the page")
    ex.expect_text(Target("css", "#state"), "ready" if attempt > 1 else "never")


def test_always_fails(ex):
    ex.goto(PAGE, intent="open the page")
    ex.expect_text(Target("css", "#state"), "never")


def test_clean(testence_writer):
    pass
"""


def _run(project: Path, *args: str) -> tuple[subprocess.CompletedProcess[str], list[dict]]:
    env = os.environ.copy()
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env.pop(RUN_ID_ENV, None)
    env.pop("PYTEST_XDIST_WORKER", None)
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
            "--basetemp",
            str(project / ".pytest-tmp"),
            "--testence-headless",
            "-q",
            *args,
        ],
        cwd=project,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    (run_dir,) = (project / "runs").iterdir()
    return result, load_run(run_dir)


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    project = tmp_path_factory.mktemp("rerun-consumer")
    (project / "test_flaky.py").write_text(FLAKY.lstrip(), encoding="utf-8")
    # A failed check waits out its timeout: 10 s by default would dominate the run, and
    # 1 s let a loaded host fail the passing attempt too.
    (project / "testence.json").write_text(json.dumps({"timeout_ms": 5_000}), encoding="utf-8")
    return project


@pytest.fixture(scope="module")
def outcome(project: Path):
    return _run(project, "--testence-reruns", "1")


def _ends(events: list[dict], name: str) -> list[dict]:
    return [e for e in events if e["kind"] == "test.end" and e["display_name"] == name]


def test_each_attempt_has_its_own_identity_and_outcome(outcome):
    result, events = outcome
    assert result.returncode == 1, result.stdout + result.stderr

    first, second = _ends(events, "test_flaky_once")
    assert first["attempt_id"] != second["attempt_id"]
    assert first["proof_id"] != second["proof_id"]
    assert (first["status"], first.get("rerun")) == ("failed", True)
    assert (second["status"], second.get("retries"), second.get("flaky")) == ("passed", 1, True)

    failed_twice = _ends(events, "test_always_fails")
    assert [e["status"] for e in failed_twice] == ["failed", "failed"]
    assert failed_twice[0].get("rerun") is True
    assert failed_twice[1].get("retries") == 1 and "flaky" not in failed_twice[1]

    (clean,) = _ends(events, "test_clean")
    assert not {"rerun", "retries", "flaky"} & set(clean)


def test_the_failure_pack_stays_with_the_attempt_that_failed(outcome):
    _, events = outcome
    first, second = _ends(events, "test_flaky_once")
    assert first.get("pack")
    assert "pack" not in second


def test_steps_of_a_repeat_belong_to_the_repeat(outcome):
    _, events = outcome
    first, second = _ends(events, "test_flaky_once")
    steps = [e for e in events if e["kind"] == "step.start" and e["intent"] == "open the page"]
    attempts = {e["attempt_id"] for e in steps if e["test"].endswith("test_flaky_once")}
    assert attempts == {first["attempt_id"], second["attempt_id"]}


def test_the_run_summary_counts_final_outcomes_and_reruns_apart(outcome, project):
    _, events = outcome
    run_end = next(e for e in events if e["kind"] == "run.end")
    assert (run_end["passed"], run_end["failed"], run_end["reruns"]) == (2, 1, 2)
    assert run_end["run_status"] == "failed"
    ledger = next((project / "runs").glob("*/run.jsonl"))
    written = json.loads(ledger.read_text(encoding="utf-8").splitlines()[-1])
    assert (written["passed"], written["failed"], written["reruns"]) == (2, 1, 2)


def _run_dir(project: Path) -> Path:
    (run_dir,) = (project / "runs").iterdir()
    return run_dir


def test_exporters_show_one_result_per_test_and_every_attempt(outcome, project, tmp_path):
    from jsonschema import Draft7Validator

    from testence.export import export_run

    run_dir = _run_dir(project)
    ctrf_dir, allure_dir, junit_dir = tmp_path / "ctrf", tmp_path / "allure", tmp_path / "junit"
    export_run(run_dir, "ctrf", ctrf_dir)
    export_run(run_dir, "allure", allure_dir)
    export_run(run_dir, "junit", junit_dir)

    ctrf = json.loads((ctrf_dir / "ctrf-report.json").read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "tests" / "schemas" / "ctrf.schema.json").read_text("utf-8"))
    assert not list(Draft7Validator(schema).iter_errors(ctrf))
    tests = {test["name"].rsplit("::", 1)[-1]: test for test in ctrf["results"]["tests"]}
    assert len(tests) == 3
    assert ctrf["results"]["summary"]["tests"] == 3
    flaky = tests["test_flaky_once"]
    assert (flaky["status"], flaky["retries"], flaky["flaky"]) == ("passed", 1, True)
    assert [attempt["status"] for attempt in flaky["retryAttempts"]] == ["failed"]
    assert tests["test_always_fails"]["flaky"] is False
    assert "retries" not in tests["test_clean"]

    results = [
        json.loads(path.read_text(encoding="utf-8")) for path in allure_dir.glob("*-result.json")
    ]
    flaky_results = [r for r in results if r["name"] == "test_flaky_once"]
    assert sorted(r["status"] for r in flaky_results) == ["failed", "passed"]
    assert len({r["historyId"] for r in flaky_results}) == 1
    assert len({r["uuid"] for r in flaky_results}) == 2

    junit = next(junit_dir.glob("*.xml")).read_text(encoding="utf-8")
    assert junit.count("<testcase ") == 3
    assert 'name="testence.flaky" value="true"' in junit


def test_inspect_and_ci_report_the_flaky_pass(outcome, project, tmp_path):
    from testence.application import inspect_run
    from testence.ci import evaluate_ci

    run_dir = _run_dir(project)
    inspected = inspect_run(run_dir)
    assert inspected["tests"] == 3
    assert inspected["reruns"] == 2
    assert inspected["flaky"] == ["test_flaky.py::test_flaky_once"]
    assert len(inspected["packs"]) == 3  # two failed attempts of one test, one of another

    kwargs = dict(run_dir=run_dir, run_id=run_dir.name, test_exit=0, quality_mode="execution")
    warned = evaluate_ci(**kwargs)
    assert warned["quality"]["flaky"] == ["test_flaky.py::test_flaky_once"]
    assert not any(error.startswith("flaky: ") for error in warned["quality"]["errors"])
    failed = evaluate_ci(**kwargs, flaky="fail")
    assert any(error.startswith("flaky: ") for error in failed["quality"]["errors"])


SETUP_AND_FIXTURES = """
from pathlib import Path

import pytest

MARK = Path(__file__).with_name("module-fixture.txt")


@pytest.fixture(scope="module")
def flaky_once_module():
    runs = int(MARK.read_text()) + 1 if MARK.exists() else 1
    MARK.write_text(str(runs))
    if runs == 1:
        raise RuntimeError("module fixture failed once")
    return runs


def test_module_fixture_is_set_up_again(flaky_once_module, testence_writer):
    assert flaky_once_module == 2


@pytest.mark.xfail(reason="known")
def test_expected_failure_is_not_repeated():
    assert False


def test_passes(testence_writer):
    pass


class TestState:
    attempts = []

    def test_a_repeat_gets_a_fresh_instance(self):
        TestState.attempts.append(hasattr(self, "seen"))
        self.seen = True
        assert len(TestState.attempts) > 1
        assert TestState.attempts == [False, False]
"""


FAILING_MODULE_SETUP = """
from pathlib import Path

MARK = Path(__file__).with_name("module-setup.txt")


def setup_module(module):
    runs = int(MARK.read_text()) + 1 if MARK.exists() else 1
    MARK.write_text(str(runs))
    if runs == 1:
        raise RuntimeError("module setup failed once")


def test_after_module_setup(testence_writer):
    pass
"""


def test_a_repeat_sets_up_again_what_failed_and_leaves_xfail_alone(tmp_path: Path):
    project = tmp_path / "setup-consumer"
    project.mkdir()
    (project / "test_setup.py").write_text(SETUP_AND_FIXTURES.lstrip(), encoding="utf-8")
    (project / "test_module_setup.py").write_text(FAILING_MODULE_SETUP.lstrip(), encoding="utf-8")

    result, events = _run(project, "--testence-reruns", "2", "-rR")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "3 rerun" in result.stdout, result.stdout
    module = _ends(events, "test_after_module_setup")
    assert [e["status"] for e in module] == ["broken", "passed"]
    fresh = _ends(events, "test_a_repeat_gets_a_fresh_instance")
    assert [e["status"] for e in fresh] == ["failed", "passed"]
    fixture = _ends(events, "test_module_fixture_is_set_up_again")
    assert [(e["status"], e.get("rerun")) for e in fixture] == [("broken", True), ("passed", None)]
    assert fixture[1]["flaky"] is True
    (xfail,) = _ends(events, "test_expected_failure_is_not_repeated")
    assert "rerun" not in xfail


UNRELATED_TEST = """
def test_x():
    pass
"""


@pytest.mark.parametrize("value", ["-1", "6", "many"])
def test_an_invalid_rerun_count_is_a_usage_error(tmp_path: Path, value):
    project = tmp_path / "invalid"
    project.mkdir()
    (project / "test_x.py").write_text(UNRELATED_TEST, encoding="utf-8")
    env = os.environ.copy()
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["PYTHONPATH"] = str(ROOT / "src")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "testence.pytest_plugin",
            "-q",
            "--rootdir",
            str(project),
            f"--testence-reruns={value}",
        ],
        cwd=project,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 4, result.stdout + result.stderr
    assert "--testence-reruns must be" in result.stdout + result.stderr


SCOPES_CONFTEST = """
from pathlib import Path

import pytest

HERE = Path(__file__).parent


def _count(name):
    mark = HERE / f"{name}.txt"
    runs = int(mark.read_text()) + 1 if mark.exists() else 1
    mark.write_text(str(runs))
    return runs


@pytest.fixture(scope="session")
def session_resource():
    return _count("session-setups")


@pytest.fixture(scope="module")
def module_resource(request):
    return _count(f"module-setups-{request.module.__name__}")
"""

LAST_IN_MODULE_FAILS_ONCE = """
from pathlib import Path

MARK = Path(__file__).with_name("call.txt")


def test_first(session_resource, module_resource, testence_writer):
    assert (session_resource, module_resource) == (1, 1)


def test_last_fails_once(session_resource, module_resource, testence_writer):
    runs = int(MARK.read_text()) + 1 if MARK.exists() else 1
    MARK.write_text(str(runs))
    assert runs > 1
    assert (session_resource, module_resource) == (1, 1)
"""

LATER_MODULE = """
import pytest


def test_session_fixture_is_the_first_one(session_resource, module_resource, testence_writer):
    assert (session_resource, module_resource) == (1, 1)


@pytest.mark.xfail(strict=True, reason="known")
def test_a_strict_xpass_is_not_repeated(testence_writer):
    pass
"""


def test_a_repeat_keeps_the_scopes_around_the_test(tmp_path: Path):
    """A repeat is the next test: the module and session fixtures around it stay up.

    Torn down as for the real next test, the last test of a module lost its module
    fixture, and the last test of the run the session ones, which the repeat then
    set up a second time (launch-hardening audit, cycle 4).
    """
    project = tmp_path / "scopes-consumer"
    project.mkdir()
    (project / "conftest.py").write_text(SCOPES_CONFTEST.lstrip(), encoding="utf-8")
    (project / "test_a.py").write_text(LAST_IN_MODULE_FAILS_ONCE.lstrip(), encoding="utf-8")
    (project / "test_b.py").write_text(LATER_MODULE.lstrip(), encoding="utf-8")

    result, events = _run(project, "--testence-reruns", "1")

    summary = result.stdout.strip().splitlines()[-1]
    assert all(part in summary for part in ("1 failed", "3 passed", "1 rerun")), result.stdout
    assert (project / "session-setups.txt").read_text() == "1"
    assert (project / "module-setups-test_a.txt").read_text() == "1"
    (xpass,) = _ends(events, "test_a_strict_xpass_is_not_repeated")
    assert xpass["status"] == "failed" and "rerun" not in xpass
