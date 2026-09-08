from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from testence.evidence import RUN_ID_ENV
from testence.metrics import load_run
from testence.testplan import (
    SelectionCandidate,
    load_testplan,
    select_candidates,
)
from testence.testplan import TestPlanError as PlanError

ROOT = Path(__file__).parents[1]


def _run(project: Path, runs: Path, plan: Path, *args: str):
    runs.mkdir(parents=True)
    env = os.environ.copy()
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env.pop(RUN_ID_ENV, None)
    env["ALLURE_TESTPLAN_PATH"] = str(plan)
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
    return result, load_run(run_dirs[0])


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "consumer"
    project.mkdir()
    (project / "test_cases.py").write_text(
        "\n".join(f"def test_{number}(): assert True" for number in range(8)) + "\n",
        encoding="utf-8",
    )
    return project


def _write_plan(path: Path, tests: list[dict], version: str = "1.0") -> Path:
    path.write_text(json.dumps({"version": version, "tests": tests}), encoding="utf-8")
    return path


def test_allure_plan_selects_exactly_one_of_eight(tmp_path):
    project = _project(tmp_path)
    plan = _write_plan(project / "testplan.json", [{"selector": "test_cases.py::test_3"}])

    result, events = _run(project, tmp_path / "runs", plan)

    assert result.returncode == 0, result.stdout + result.stderr
    ends = [event for event in events if event["kind"] == "test.end"]
    assert [event["nodeid"] for event in ends] == ["test_cases.py::test_3"]
    collection = next(event for event in events if event["kind"] == "collection.end")
    assert collection["selected"] == 1


def test_selector_targets_one_parameter_variant(tmp_path):
    project = tmp_path / "variants"
    project.mkdir()
    (project / "test_variants.py").write_text(
        "import pytest\n\n"
        "@pytest.mark.parametrize('browser', ['chromium', 'firefox'])\n"
        "def test_checkout(browser): assert browser\n",
        encoding="utf-8",
    )
    plan = _write_plan(
        project / "testplan.json",
        [{"selector": "test_variants.py::test_checkout[chromium]"}],
    )

    result, events = _run(project, tmp_path / "variant-runs", plan)

    assert result.returncode == 0, result.stdout + result.stderr
    ends = [event for event in events if event["kind"] == "test.end"]
    assert [event["nodeid"] for event in ends] == ["test_variants.py::test_checkout[chromium]"]


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        ("not-json", "invalid Allure test plan JSON"),
        (json.dumps({"version": "2.0", "tests": []}), "version must be '1.0'"),
        (json.dumps({"version": "1.0", "tests": [{}]}), "requires id or selector"),
        (
            json.dumps({"version": "1.0", "tests": [{"selector": "missing::test"}]}),
            "did not resolve",
        ),
    ],
)
def test_invalid_or_unresolved_plan_fails_before_execution(tmp_path, contents, message):
    project = _project(tmp_path)
    plan = project / "testplan.json"
    plan.write_text(contents, encoding="utf-8")

    result, events = _run(project, tmp_path / "runs", plan)

    assert result.returncode == 4
    assert message in result.stderr
    assert not any(event["kind"] == "test.start" for event in events)
    assert {event["status"] for event in events if event["kind"] == "test.end"} <= {"not_run"}
    assert next(event for event in events if event["kind"] == "run.end")["run_status"] == (
        "usage_error"
    )


def test_empty_plan_fails_unless_explicit_noop_policy(tmp_path):
    project = _project(tmp_path)
    plan = _write_plan(project / "testplan.json", [])

    failed, _events = _run(project, tmp_path / "failed-runs", plan)
    noop, events = _run(
        project,
        tmp_path / "noop-runs",
        plan,
        "--testence-empty-testplan=noop",
    )

    assert failed.returncode == 4
    assert "selected zero tests" in failed.stderr
    assert noop.returncode == 0, noop.stdout + noop.stderr
    assert not any(event["kind"] == "test.end" for event in events)
    assert next(event for event in events if event["kind"] == "run.end")["run_status"] == "passed"


def test_namespaced_selector_and_allure_id_are_exact_and_unambiguous(tmp_path):
    plan = _write_plan(
        tmp_path / "testplan.json",
        [{"selector": "testence://shop/create/default"}, {"id": 42}],
    )
    candidates = [
        SelectionCandidate("tests/test_a.py::test_a", "shop", "create", "default"),
        SelectionCandidate("tests/test_b.py::test_b", "shop", "delete", "default", "42"),
    ]

    assert select_candidates(load_testplan(plan), candidates) == {0, 1}

    with pytest.raises(PlanError, match="ambiguous"):
        select_candidates(
            load_testplan(_write_plan(plan, [{"id": "42"}])),
            [*candidates, SelectionCandidate("test_c", "shop", "edit", "default", "42")],
        )
