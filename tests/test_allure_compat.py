"""Testence's Allure export lands on the identities allure-pytest creates.

``tests/fixtures/allure-pytest-reference/expected.json`` was produced by real
allure-pytest (see ``regenerate.py``) from the same project this test runs through
Testence, without allure installed. A migrated suite keeps its TestOps cases only if
these fields match (L07 of the stage 4 plan).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from testence import allure_compat
from testence.evidence import RUN_ID_ENV
from testence.export import export_run

ROOT = Path(__file__).parents[1]
REFERENCE = ROOT / "tests" / "fixtures" / "allure-pytest-reference"
DECLARED_LABELS = {"as_id", "feature", "story", "severity", "layer"}
# The tree TestOps and Allure build: suites, package and tags (L08).
HIERARCHY_LABELS = {"package", "parentSuite", "suite", "subSuite", "tag"}


def _run_reference(tmp_path: Path, *extra_files: tuple[str, str]) -> tuple[Path, str]:
    project = tmp_path / "project"
    shutil.copytree(REFERENCE / "project", project)
    for name, content in extra_files:
        (project / name).write_text(content, encoding="utf-8")
    runs = tmp_path / "runs"
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
    (run_dir,) = [path for path in runs.iterdir() if path.is_dir()]
    return run_dir, result.stdout + result.stderr


def _exported(run_dir: Path, out: Path) -> dict[tuple[str, str], dict[str, Any]]:
    export_run(run_dir, "allure", out)
    documents = [json.loads(path.read_text(encoding="utf-8")) for path in out.glob("*-result.json")]
    return {(doc["fullName"], doc["historyId"]): doc for doc in documents}


def test_export_reproduces_allure_pytest_identity_and_declared_metadata(tmp_path):
    expected = json.loads((REFERENCE / "expected.json").read_text(encoding="utf-8"))["cases"]
    run_dir, _ = _run_reference(tmp_path)
    actual = _exported(run_dir, tmp_path / "allure")

    assert set(actual) == {(case["fullName"], case["historyId"]) for case in expected}
    for case in expected:
        document = actual[(case["fullName"], case["historyId"])]
        assert document["testCaseId"] == case["testCaseId"], case["fullName"]
        assert document["name"] == case["name"]
        assert document.get("description") == case["description"]
        declared = sorted(
            (label["name"], label["value"])
            for label in document["labels"]
            if label["name"] in DECLARED_LABELS
        )
        assert declared == sorted(
            (label["name"], label["value"])
            for label in case["labels"]
            if label["name"] in DECLARED_LABELS
        )
        assert sorted(
            (link["url"], link["name"], link["type"]) for link in document["links"]
        ) == sorted((link["url"], link["name"], link["type"]) for link in case["links"])
        for names in (DECLARED_LABELS, HIERARCHY_LABELS):
            assert sorted(
                (label["name"], label["value"])
                for label in document["labels"]
                if label["name"] in names
            ) == sorted(
                (label["name"], label["value"])
                for label in case["labels"]
                if label["name"] in names
            ), case["fullName"]
        assert document.get("titlePath", []) == case["titlePath"]
        assert sorted((item["name"], item["value"]) for item in document["parameters"]) == sorted(
            (item["name"], item["value"]) for item in case["parameters"]
        )


def test_nodeid_naming_keeps_the_previous_identity(tmp_path):
    settings = json.dumps({"export": {"allure": {"naming": "nodeid"}}})
    run_dir, _ = _run_reference(tmp_path, ("testence.json", settings))
    actual = _exported(run_dir, tmp_path / "allure")
    names = {full_name for full_name, _ in actual}
    assert "suites/checkout/test_reference.py::test_plain" in names
    assert not any("#" in name for name in names)


def test_invalid_allure_naming_stops_the_session(tmp_path):
    settings = json.dumps({"export": {"allure": {"naming": "fancy"}}})
    with pytest.raises(AssertionError, match="export.allure.naming"):
        _run_reference(tmp_path, ("testence.json", settings))


def test_plan_bound_case_keeps_its_rename_proof_identity(tmp_path):
    """An explicit PlanSpec case_id survives a rename; allure-pytest's hash would not."""
    from testence.export._model import LoadedRun, Test
    from testence.export.allure import _identity

    test = Test(
        name="test_renamed",
        project_id="shop",
        case_id="checkout.pay",
        plan_id="shop.checkout",
        allure={"full_name": "a#test_renamed", "test_case_id": "x", "history_id": "y"},
    )
    full_name, test_case_id, history_id = _identity(LoadedRun(project_id="shop"), test)
    assert full_name == "a#test_renamed"
    assert (test_case_id, history_id) != ("x", "y")
    renamed = Test(**{**test.__dict__, "allure": {**test.allure, "full_name": "b#other"}})
    assert _identity(LoadedRun(project_id="shop"), renamed)[1] == test_case_id


def test_metadata_marker_without_a_plan(tmp_path):
    test_file = (
        "import pytest\n\n"
        "@pytest.mark.testence(allure_id=77, title='Checkout pays', severity='blocker',\n"
        "    labels={'feature': 'Cart', 'story': ['Pay', 'Refund']},\n"
        "    links=['https://docs.example.test/pay',\n"
        "           {'url': 'https://tracker.example.test/PAY-9', 'type': 'issue'}])\n"
        "def test_meta():\n"
        "    assert True\n"
    )
    run_dir, _ = _run_reference(tmp_path, ("test_meta.py", test_file))
    actual = _exported(run_dir, tmp_path / "allure")
    (document,) = [doc for (name, _), doc in actual.items() if name == "test_meta#test_meta"]
    labels = {(label["name"], label["value"]) for label in document["labels"]}
    assert {("ALLURE_ID", "77"), ("severity", "blocker"), ("feature", "Cart")} <= labels
    assert {("story", "Pay"), ("story", "Refund")} <= labels
    assert document["name"] == "Checkout pays"
    assert {link["type"] for link in document["links"]} == {"link", "issue"}


@pytest.mark.parametrize(
    ("marker", "message"),
    [
        ("severity='urgent'", "severity must be one of"),
        ("labels=['feature']", "labels must be a mapping"),
        ("links=[{'url': 'https://x.test', 'type': 'wiki'}]", "link type must be"),
        ("claims=['a.b']", "requires plan"),
        ("title=''", "title must be a non-empty string"),
    ],
)
def test_invalid_metadata_marker_is_a_usage_error(tmp_path, marker, message):
    test_file = f"import pytest\n\n@pytest.mark.testence({marker})\ndef test_bad():\n    pass\n"
    with pytest.raises(AssertionError, match=message):
        _run_reference(tmp_path, ("test_bad.py", test_file))


def test_one_allure_id_on_two_tests_warns(tmp_path):
    test_file = (
        "import pytest\n\n"
        "@pytest.mark.testence(allure_id=5)\ndef test_one():\n    pass\n\n"
        "@pytest.mark.testence(allure_id=5)\ndef test_two():\n    pass\n"
    )
    _, output = _run_reference(tmp_path, ("test_dup.py", test_file))
    assert "Allure ID 5 is set on 2 different tests" in output


def test_parametrized_variants_of_one_test_share_an_allure_id_without_warning(tmp_path):
    test_file = (
        "import pytest\n\n"
        "@pytest.mark.testence(allure_id=6)\n"
        "@pytest.mark.parametrize('n', [1, 2])\ndef test_variants(n):\n    pass\n"
    )
    _, output = _run_reference(tmp_path, ("test_variants.py", test_file))
    assert "Allure ID 6" not in output


def test_compat_helpers_match_allure_commons_semantics():
    assert allure_compat.full_name("a/b/test_x.py::TestK::test_y[1]") == "a.b.test_x.TestK#test_y"
    assert allure_compat.full_name("test_x.py::test_y") == "test_x#test_y"
    assert allure_compat.represent("hi") == "'hi'"
    assert allure_compat.represent(3) == "3"
    assert allure_compat.represent(b"x") == "<class 'bytes'>"
    assert allure_compat.history_id("n", {"b": 2, "a": "x"}) == allure_compat.md5("n", "x", 2)
