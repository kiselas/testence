"""``@allure.*`` and ``allure.dynamic.*`` with the allure package but not allure-pytest.

The decorators become pytest marks only through a helper allure-pytest registers;
without it they silently did nothing, so a suite that finished moving to Testence
and dropped allure-pytest lost every label, link, id and title (launch-hardening
audit K11-1). ``allure.dynamic.*`` never became marks at all (K11-3), and an Enum
severity was exported as ``Severity.CRITICAL`` (K11-5).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from testence.evidence import RUN_ID_ENV
from testence.export import export_run

pytest.importorskip("allure")

ROOT = Path(__file__).parents[1]

SUITE = """
import allure
import pytest


@allure.epic("Shop")
@allure.feature("Checkout")
@allure.story("Pay by card")
@allure.severity(allure.severity_level.CRITICAL)
@allure.id("1042")
@allure.tag("smoke")
@allure.link("https://docs.example.test/pay", name="spec")
@allure.issue("https://jira.example.test/PAY-7")
@allure.title("Paying with a saved card charges it once")
@allure.description("The card is charged exactly once.")
def test_static(testence_writer):
    pass


@allure.feature("Refunds")
def test_dynamic(testence_writer):
    allure.dynamic.title("Refund is issued")
    allure.dynamic.severity(allure.severity_level.MINOR)
    allure.dynamic.story("Full refund")
    allure.dynamic.link("https://jira.example.test/REF-1", name="REF-1")


@pytest.mark.parametrize("amount", [5, 10])
@allure.title("Refund of {amount}")
def test_titled_variants(testence_writer, amount):
    allure.dynamic.tag(f"amount-{amount}")
"""


def _run(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    (project / "test_shop.py").write_text(SUITE.lstrip(), encoding="utf-8")
    runs = tmp_path / "runs"
    env = os.environ.copy()
    # Autoload off: allure-pytest must not be what makes the decorators work.
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
            "-p",
            "no:cacheprovider",
            "--strict-markers",
            "-q",
        ],
        cwd=project,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    (run_dir,) = [path for path in runs.iterdir() if path.is_dir()]
    return run_dir


@pytest.fixture(scope="module")
def results(tmp_path_factory: pytest.TempPathFactory) -> dict[str, dict]:
    tmp_path = tmp_path_factory.mktemp("allure-hooks")
    out = tmp_path / "allure"
    export_run(_run(tmp_path), "allure", out)
    documents = [json.loads(path.read_text(encoding="utf-8")) for path in out.glob("*-result.json")]
    return {document["name"]: document for document in documents}


def _labels(document: dict) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for label in document["labels"]:
        found.setdefault(label["name"], []).append(label["value"])
    return found


def test_decorators_are_read_without_allure_pytest(results):
    document = results["Paying with a saved card charges it once"]
    labels = _labels(document)
    assert labels["epic"] == ["Shop"]
    assert labels["feature"] == ["Checkout"]
    assert labels["story"] == ["Pay by card"]
    assert labels["severity"] == ["critical"]
    assert labels["as_id"] == ["1042"]
    assert "smoke" in labels["tag"]
    assert document["description"] == "The card is charged exactly once."
    links = {(link["type"], link["url"]) for link in document["links"]}
    assert ("link", "https://docs.example.test/pay") in links
    assert ("issue", "https://jira.example.test/PAY-7") in links


def test_dynamic_values_of_the_test_reach_its_result(results):
    document = results["Refund is issued"]
    labels = _labels(document)
    assert labels["feature"] == ["Refunds"]
    assert labels["severity"] == ["minor"]
    assert labels["story"] == ["Full refund"]
    assert {"type": "link", "url": "https://jira.example.test/REF-1", "name": "REF-1"} in document[
        "links"
    ]


def test_dynamic_values_stay_with_their_own_variant(results):
    five, ten = results["Refund of 5"], results["Refund of 10"]
    assert "amount-5" in _labels(five)["tag"] and "amount-10" not in _labels(five)["tag"]
    assert "amount-10" in _labels(ten)["tag"]
