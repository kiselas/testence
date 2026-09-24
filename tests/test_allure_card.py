"""What a person sees on the Allure/TestOps card of a Testence result (L08)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from testence.evidence import RUN_ID_ENV
from testence.export import export_run

ROOT = Path(__file__).parents[1]

_SUITE = """
import pytest
from testence.dsl.steps import StepFailed
from testence.oracle import OracleFailed, OracleInconclusive


def test_assertion():
    assert 1 == 2, "the total is wrong"


def test_type_error():
    None.upper()


def test_step_timeout():
    raise StepFailed("click Save", TimeoutError("locator did not appear"))


def test_step_assertion():
    raise StepFailed("expect total", AssertionError("expected 10, saw 9"))


def test_oracle():
    raise OracleFailed("order saved", [{"field": "state", "ui": "paid", "api": "new"}])


def test_inconclusive():
    raise OracleInconclusive("api unreachable")


@pytest.mark.parametrize(("user", "password"), [("alice", "hunter2-secret")])
def test_login(user, password):
    assert user and password


@pytest.mark.smoke
@pytest.mark.usefixtures("tmp_path")
@pytest.mark.filterwarnings("ignore")
def test_tagged():
    assert True
"""


def _run(tmp_path: Path, suite: str = _SUITE, settings: dict[str, Any] | None = None) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    (project / "test_card.py").write_text(suite, encoding="utf-8")
    (project / "pytest.ini").write_text("[pytest]\nmarkers =\n    smoke: tag\n", encoding="utf-8")
    if settings is not None:
        (project / "testence.json").write_text(json.dumps(settings), encoding="utf-8")
    runs = tmp_path / "runs"
    env = os.environ.copy()
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env.pop(RUN_ID_ENV, None)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "src"), value] if (value := env.get("PYTHONPATH")) else [str(ROOT / "src")]
    )
    subprocess.run(
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
            "--testence-headless",
            "-p",
            "no:cacheprovider",
            "-q",
        ],
        cwd=project,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    (run_dir,) = [path for path in runs.iterdir() if path.is_dir()]
    return run_dir


def _cards(run_dir: Path, out: Path) -> dict[str, dict[str, Any]]:
    export_run(run_dir, "allure", out)
    documents = [json.loads(path.read_text(encoding="utf-8")) for path in out.glob("*-result.json")]
    return {doc["fullName"].rsplit("#", 1)[1]: doc for doc in documents}


def test_status_separates_product_disagreement_from_an_undecided_test(tmp_path):
    cards = _cards(_run(tmp_path), tmp_path / "allure")
    assert {name: card["status"] for name, card in cards.items()} == {
        "test_assertion": "failed",
        "test_type_error": "broken",
        "test_step_timeout": "broken",
        "test_step_assertion": "failed",
        "test_oracle": "failed",
        "test_inconclusive": "broken",
        "test_login": "passed",
        "test_tagged": "passed",
    }
    # The trace is the pytest failure, not a repeat of the one-line message.
    details = cards["test_type_error"]["statusDetails"]
    assert "NoneType" in details["message"]
    assert "None.upper()" in details["trace"]
    assert details["trace"] != details["message"]
    categories = json.loads((tmp_path / "allure" / "categories.json").read_text(encoding="utf-8"))
    assert {category["name"] for category in categories} >= {
        "Assertion failed",
        "Environment or browser (infrastructure)",
    }


def test_parameters_are_readable_and_a_secret_named_one_is_masked(tmp_path):
    cards = _cards(_run(tmp_path), tmp_path / "allure")
    parameters = {item["name"]: item for item in cards["test_login"]["parameters"]}
    assert parameters["user"]["value"] == "'alice'"
    assert "hunter2-secret" not in json.dumps(cards["test_login"]["parameters"])
    assert parameters["password"]["mode"] == "masked"
    assert "variant_id" not in parameters
    assert any(label["name"] == "variant_id" for label in cards["test_login"]["labels"])


def test_only_user_markers_become_tags(tmp_path):
    cards = _cards(_run(tmp_path), tmp_path / "allure")
    tags = [label["value"] for label in cards["test_tagged"]["labels"] if label["name"] == "tag"]
    assert tags == ["smoke"]
    for card in cards.values():
        assert "parametrize" not in {
            label["value"] for label in card["labels"] if label["name"] == "tag"
        }


def test_digest_parameters_keep_the_previous_shape(tmp_path):
    run_dir = _run(tmp_path, settings={"export": {"allure": {"parameters": "digest"}}})
    cards = _cards(run_dir, tmp_path / "allure")
    values = {item["name"]: item["value"] for item in cards["test_login"]["parameters"]}
    assert values["variant_id"].startswith("variant-")
    assert values["user"].startswith("sha256:")


def test_plan_scenario_names_and_describes_the_card(tmp_path):
    from testence.export._model import LoadedRun, Test
    from testence.export.allure import _description, _name

    scenario = {
        "title": "A paid order is persisted",
        "claims": [{"id": "orders.persisted", "statement": "The saved order is stored"}],
        "plan": "specs/orders.md",
    }
    test = Test(name="test_pay", allure={"plan_scenario": scenario, "docstring": "Docstring."})
    assert _name(test) == "A paid order is persisted"
    description = _description(test) or ""
    assert "**orders.persisted**: The saved order is stored" in description
    assert "specs/orders.md" in description
    explicit = Test(name="t", allure={"plan_scenario": scenario, "description": "Explicit"})
    assert _description(explicit) == "Explicit"
    assert _name(Test(name="t", allure={"plan_scenario": scenario, "title": "Mine"})) == "Mine"
    assert _description(Test(name="t", allure={"docstring": "Doc."})) == "Doc."
    assert LoadedRun().allure_parameters == "values"


def test_failure_screenshot_is_also_on_the_failed_step():
    from testence.export.allure import _attach_to_failed_step

    shot = {"name": "screenshot.png", "source": "x-attachment.png", "type": "image/png"}
    steps = [
        {"name": "open", "status": "passed"},
        {
            "name": "checkout",
            "status": "failed",
            "steps": [{"name": "fill", "status": "passed"}, {"name": "pay", "status": "failed"}],
        },
    ]
    assert _attach_to_failed_step(steps, shot)
    assert steps[1]["steps"][1]["attachments"] == [shot]
    assert "attachments" not in steps[1]


_BROWSER_SUITE = """
def test_green(ex):
    ex.goto("data:text/html,<h1>Paid</h1>")
"""


def test_screenshots_always_attaches_the_passing_page(tmp_path):
    settings = {
        "evidence": {"screenshots": "always"},
        "extra": {"capture_policy": {"screenshots": True}},
        "debug_port": 0,
    }
    run_dir = _run(tmp_path, _BROWSER_SUITE, settings)
    cards = _cards(run_dir, tmp_path / "allure")
    card = cards["test_green"]
    assert card["status"] == "passed"
    (shot,) = [item for item in card.get("attachments", []) if item["name"] == "screenshot.png"]
    assert (tmp_path / "allure" / shot["source"]).read_bytes().startswith(b"\x89PNG")

    export_run(run_dir, "allure", tmp_path / "minimal-policy", attachments="minimal")
    documents = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (tmp_path / "minimal-policy").glob("*-result.json")
    ]
    assert not any(doc.get("attachments") for doc in documents)


def test_secret_parameter_in_a_pytest_id_is_warned_about(tmp_path):
    """pytest puts parameter values into test ids; redacting ids would break identity,
    so the author is told to name the variant with ``ids=`` instead."""
    project = tmp_path / "warn"
    project.mkdir()
    (project / "test_w.py").write_text(
        "import pytest\n\n"
        "@pytest.mark.parametrize('api_token', ['tok-123456'])\n"
        "def test_w(api_token): assert api_token\n\n"
        "@pytest.mark.parametrize('api_token', ['tok-123456'], ids=['staging'])\n"
        "def test_ok(api_token): assert api_token\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env.pop(RUN_ID_ENV, None)
    env["PYTHONPATH"] = str(ROOT / "src")
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
            str(tmp_path / "runs"),
            "-p",
            "no:cacheprovider",
            "-q",
        ],
        cwd=project,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "test_w.py::test_w[tok-123456]: parameter 'api_token'" in result.stdout
    assert "test_ok[staging]: parameter" not in result.stdout
