from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from testence.evidence import RUN_ID_ENV
from testence.export import export_run
from testence.metrics import load_run
from testence.testplan import (
    SelectionCandidate,
    load_testplan,
    resolve,
    select_candidates,
)
from testence.testplan import TestPlan as Plan
from testence.testplan import TestPlanEntry as PlanEntry
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
            "no Allure test plan entry resolved",
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


def test_namespaced_selector_and_allure_id_select_every_matching_candidate(tmp_path):
    plan = _write_plan(
        tmp_path / "testplan.json",
        [{"selector": "testence://shop/create/default"}, {"id": 42}],
    )
    candidates = [
        SelectionCandidate("tests/test_a.py::test_a", "shop", "create", "default"),
        SelectionCandidate("tests/test_b.py::test_b", "shop", "delete", "default", "42"),
    ]

    assert select_candidates(load_testplan(plan), candidates) == {0, 1}

    # One TestOps case over several variants selects all of them: that is what
    # rerunning a parametrized case from TestOps means.
    shared = [*candidates, SelectionCandidate("test_c", "shop", "edit", "default", "42")]
    assert select_candidates(load_testplan(_write_plan(plan, [{"id": "42"}])), shared) == {1, 2}


def _stale_project(tmp_path: Path) -> Path:
    project = tmp_path / "stale"
    project.mkdir()
    (project / "test_shop.py").write_text(
        "import pytest\n\n"
        "def test_cart(): assert True\n\n"
        "def test_other(): assert True\n\n"
        "@pytest.mark.testence(allure_id=123)\n"
        "@pytest.mark.parametrize('role', ['admin', 'viewer'])\n"
        "def test_login(role): assert role\n\n"
        "@pytest.mark.parametrize('size', [1, 2, 3])\n"
        "def test_sizes(size): assert size\n",
        encoding="utf-8",
    )
    return project


def _ended(events: list[dict]) -> list[str]:
    return sorted(event["nodeid"] for event in events if event["kind"] == "test.end")


def test_a_stale_entry_is_reported_while_the_rest_of_the_plan_runs(tmp_path):
    project = _stale_project(tmp_path)
    plan = _write_plan(
        project / "testplan.json",
        [
            {"selector": "test_shop.py::test_cart"},
            {"id": "999", "selector": "test_shop.py::test_renamed_last_week"},
        ],
    )
    result, events = _run(project, tmp_path / "runs", plan)

    assert result.returncode == 0, result.stdout + result.stderr
    assert _ended(events) == ["test_shop.py::test_cart"]
    assert "1 Allure test plan entry matched no collected test" in result.stdout
    (unresolved,) = [event for event in events if event["kind"] == "testplan.unresolved"]
    assert unresolved["count"] == 1
    assert unresolved["entries"] == [
        {"id": "999", "selector": "test_shop.py::test_renamed_last_week"}
    ]

    run_dir = next((tmp_path / "runs").iterdir())
    export_run(run_dir, "allure", tmp_path / "allure")
    properties = (tmp_path / "allure" / "environment.properties").read_text(encoding="utf-8")
    assert "testence.testplan_unresolved=1" in properties
    export_run(run_dir, "ctrf", tmp_path / "ctrf")
    ctrf = json.loads((tmp_path / "ctrf" / "ctrf-report.json").read_text(encoding="utf-8"))
    assert ctrf["results"]["summary"]["extra"]["testence"]["testplan_unresolved"] == [
        {"id": "999", "selector": "test_shop.py::test_renamed_last_week"}
    ]


def test_strict_policy_refuses_a_stale_entry_before_execution(tmp_path):
    project = _stale_project(tmp_path)
    plan = _write_plan(
        project / "testplan.json",
        [{"selector": "test_shop.py::test_cart"}, {"selector": "test_shop.py::test_gone"}],
    )
    result, events = _run(project, tmp_path / "runs", plan, "--testence-testplan-unresolved=fail")
    assert result.returncode == 4
    assert "did not resolve" in result.stderr
    assert not any(event["kind"] == "test.start" for event in events)


def test_rerunning_a_parametrized_case_by_allure_id_runs_every_variant(tmp_path):
    project = _stale_project(tmp_path)
    plan = _write_plan(project / "testplan.json", [{"id": 123}])
    result, events = _run(project, tmp_path / "runs", plan)
    assert result.returncode == 0, result.stdout + result.stderr
    assert _ended(events) == [
        "test_shop.py::test_login[admin]",
        "test_shop.py::test_login[viewer]",
    ]


def test_an_allure_pytest_full_name_selects_every_variant(tmp_path):
    project = _stale_project(tmp_path)
    plan = _write_plan(project / "testplan.json", [{"selector": "test_shop#test_sizes"}])
    result, events = _run(project, tmp_path / "runs", plan)
    assert result.returncode == 0, result.stdout + result.stderr
    assert _ended(events) == [f"test_shop.py::test_sizes[{size}]" for size in (1, 2, 3)]


def test_overlapping_and_repeated_entries_select_each_test_once(tmp_path):
    project = _stale_project(tmp_path)
    plan = _write_plan(
        project / "testplan.json",
        [
            {"selector": "test_shop#test_sizes"},
            {"selector": "test_shop.py::test_sizes[2]"},
            {"selector": "test_shop.py::test_sizes[2]"},
        ],
    )
    result, events = _run(project, tmp_path / "runs", plan)
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(_ended(events)) == 3


def test_unknown_plan_fields_are_ignored_with_a_warning(tmp_path):
    project = _stale_project(tmp_path)
    plan = project / "testplan.json"
    plan.write_text(
        json.dumps(
            {
                "version": "1.0",
                "tests": [{"selector": "test_shop.py::test_cart", "priority": "high"}],
                "generatedBy": "testops",
            }
        ),
        encoding="utf-8",
    )
    result, events = _run(project, tmp_path / "runs", plan)
    assert result.returncode == 0, result.stdout + result.stderr
    assert _ended(events) == ["test_shop.py::test_cart"]
    assert "ignored unknown Allure test plan field(s): generatedBy" in result.stdout
    assert "ignored unknown Allure test plan entry field(s): priority" in result.stdout


def test_resolve_reports_unresolved_entries_and_refuses_a_plan_that_selects_nothing():
    candidates = [SelectionCandidate("t.py::a", "p", "a", "default", full_name="t#a")]
    plan = Plan("1.0", (PlanEntry(selector="t#a"), PlanEntry(id="7")))
    selection = resolve(plan, candidates)
    assert selection.selected == frozenset({0})
    assert selection.unresolved == (PlanEntry(id="7"),)
    with pytest.raises(PlanError, match="did not resolve"):
        resolve(plan, candidates, unresolved="fail")
    with pytest.raises(PlanError, match="no Allure test plan entry resolved"):
        resolve(Plan("1.0", (PlanEntry(id="7"),)), candidates)
