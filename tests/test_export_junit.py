"""JUnit and CTRF as the other platforms read them (stage 4, L10).

JUnit is what TestRail (``trcli``), Xray, Jenkins and GitLab ingest; CTRF is the
newer JSON report. Both must carry what ``pytest --junitxml`` cannot: the Testence
identity, test-management case ids, the intent steps and the evidence files, and
both must stay valid for the consumer's own schema.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

from testence.contracts._validation import ContractError
from testence.evidence import RUN_ID_ENV, EvidenceWriter
from testence.export import export_run
from testence.pytest_plugin import _resolve_tms

from .test_export import GOLDEN_DIR, build_ledger

ROOT = Path(__file__).parents[1]
CTRF_SCHEMA = json.loads(
    (Path(__file__).parent / "schemas" / "ctrf.schema.json").read_text("utf-8")
)

# Jenkins' junit-4.xsd, reduced to what a checker needs: the attributes each element
# may carry and the children it may contain, in order. Two deviations are deliberate
# and match pytest's default xunit1 dialect: <properties> and ``file`` on a
# <testcase>, where trcli and Xray read case ids. Checked against the XSD itself
# with lxml when the exporter was written; nothing else differs.
_ALLOWED = {
    "testsuites": ({"name", "time", "tests", "failures", "errors", "disabled"}, ["testsuite"]),
    "testsuite": (
        {
            "name",
            "tests",
            "failures",
            "errors",
            "skipped",
            "disabled",
            "time",
            "timestamp",
            "hostname",
            "id",
            "package",
            "file",
            "log",
            "url",
            "version",
        },
        ["properties", "testcase", "system-out", "system-err"],
    ),
    "testcase": (
        {"name", "classname", "time", "status", "assertions", "file", "line"},
        ["properties", "skipped", "error", "failure", "system-out", "system-err"],
    ),
}


def _check_junit_shape(element: ET.Element) -> None:
    attributes, children = _ALLOWED[element.tag]
    assert set(element.attrib) <= attributes, (element.tag, set(element.attrib) - attributes)
    order = [child.tag for child in element]
    assert all(tag in children for tag in order), (element.tag, order)
    positions = [children.index(tag) for tag in order]
    assert positions == sorted(positions), (element.tag, order)
    for child in element:
        if child.tag in _ALLOWED:
            _check_junit_shape(child)
        elif child.tag == "properties":
            assert all(item.tag == "property" for item in child)
            assert all(set(item.attrib) == {"name", "value"} for item in child)


def _tms_ledger(tmp_path: Path) -> Path:
    writer = EvidenceWriter(tmp_path, run_id="r-tms", worker="")
    writer.emit("run.start", testence="0.1.0.dev0", fingerprint={"browser_channel": "chromium"})
    for test, status, kind, extra in (
        ("test_pay", "pass", "", {"tms": {"testrail": ["C123", "C124"], "xray": ["PAY-7"]}}),
        ("test_env", "failed", "infrastructure", {"tms": {"qase": ["12"]}}),
        ("test_skip", "skipped", "", {}),
    ):
        writer.emit(
            "test.start",
            test=test,
            file="tests/test_pay.py",
            nodeid=f"tests/test_pay.py::{test}",
            requirements=[{"id": "PAY-1", "url": "https://jira.example/PAY-1"}],
            **extra,
        )
        writer.emit("step.start", test=test, step="s1", intent=f"{test} step", depth=0)
        writer.emit(
            "step.end",
            test=test,
            step="s1",
            status="ok" if status == "pass" else "fail",
            duration_ms=5.0,
            depth=0,
            children=0,
        )
        writer.emit(
            "test.end",
            test=test,
            status=status,
            duration_ms=20.0,
            error="ConnectionError: gateway \x1b[31mdown\x00" if kind else None,
            error_kind=kind or None,
        )
    writer.emit("run.end", duration_ms=70.0, passed=1, failed=1)
    writer.close()
    return writer.run_dir


def _cases(xml_path: Path) -> dict[str, ET.Element]:
    root = ET.parse(xml_path).getroot()
    return {case.get("name", ""): case for case in root.iter("testcase")}


def _properties(case: ET.Element) -> list[tuple[str, str]]:
    return [
        (item.get("name", ""), item.get("value", ""))
        for properties in case.findall("properties")
        for item in properties
    ]


def test_junit_is_valid_for_jenkins_and_counts_outcomes(tmp_path):
    files = export_run(build_ledger(tmp_path), "junit", tmp_path / "junit")
    report = files[0]
    assert report.name == "junit.xml"
    root = ET.parse(report).getroot()
    _check_junit_shape(root)
    assert (root.get("tests"), root.get("failures"), root.get("errors")) == ("2", "1", "0")
    red = _cases(report)["test_hosts"]
    failure = red.find("failure")
    assert failure is not None and "boom" in (failure.get("message") or "")
    out = red.findtext("system-out") or ""
    attachments = [
        line.split("|", 1)[1].rstrip("]") for line in out.splitlines() if "ATTACHMENT" in line
    ]
    assert attachments and all((report.parent / path).is_file() for path in attachments)


def test_case_ids_land_under_the_names_each_platform_reads(tmp_path):
    report = export_run(_tms_ledger(tmp_path), "junit", tmp_path / "out")[0]
    cases = _cases(report)
    pay = dict(_properties(cases["test_pay"]))
    # TestRail trcli --case-matcher property; Xray test_key and requirements.
    assert pay["test_id"] == "C123, C124"
    assert pay["test_key"] == "PAY-7"
    assert pay["requirements"] == "PAY-1"
    steps = [
        value for name, value in _properties(cases["test_pay"]) if name == "testrail_result_step"
    ]
    assert steps == ["passed:test_pay step"]
    # A system without a documented property keeps a namespaced one.
    assert dict(_properties(cases["test_env"]))["tms.qase"] == "12"


def test_broken_and_skipped_results_use_error_and_skipped(tmp_path):
    report = export_run(_tms_ledger(tmp_path), "junit", tmp_path / "out")[0]
    cases = _cases(report)
    env = cases["test_env"]
    assert env.find("error") is not None and env.find("failure") is None
    # Control characters a console emits are replaced, so the file still parses.
    assert "\x1b" not in (env.find("error").get("message") or "")
    assert cases["test_skip"].find("skipped") is not None
    root = ET.parse(report).getroot()
    assert root.get("errors") == "1"
    assert sum(int(suite.get("skipped", "0")) for suite in root.iter("testsuite")) == 1


def test_tms_marker_values_are_checked_and_normalised():
    assert _resolve_tms({"testrail": [123, "C124"], "xray": "PAY-7", "qase": 12}) == (
        ("qase", ("12",)),
        ("testrail", ("C123", "C124")),
        ("xray", ("PAY-7",)),
    )
    for bad in (
        {"testrail": "T12"},
        {"xray": "pay-7"},
        {"xray": ["PAY-7", "PAY-8"]},
        {"TestRail": "C1"},
        {"qase": []},
        {"qase": True},
        ["testrail"],
    ):
        with pytest.raises(ContractError):
            _resolve_tms(bad)


def test_the_marker_reaches_the_junit_report_through_a_real_run(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "test_marked.py").write_text(
        "import pytest\n\n"
        "@pytest.mark.testence(tms={'testrail': 42, 'xray': 'SHOP-3'})\n"
        "def test_checkout():\n    assert True\n",
        encoding="utf-8",
    )
    env = {
        k: v for k, v in os.environ.items() if k != RUN_ID_ENV and not k.startswith("PYTEST_XDIST")
    }
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["PYTHONPATH"] = str(ROOT / "src")
    runs = tmp_path / "runs"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "testence.pytest_plugin",
            "-q",
            "-p",
            "no:cacheprovider",
            "--rootdir",
            str(project),
            "--testence-runs-root",
            str(runs),
        ],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    run_dir = next(runs.iterdir())
    report = export_run(run_dir, "junit", tmp_path / "junit")[0]
    properties = dict(_properties(_cases(report)["test_checkout"]))
    assert (properties["test_id"], properties["test_key"]) == ("C42", "SHOP-3")
    labels = json.loads((export_run(run_dir, "ctrf", tmp_path / "ctrf")[0]).read_text("utf-8"))
    assert labels["results"]["tests"][0]["labels"]["tms.testrail"] == "C42"


@pytest.mark.parametrize("ledger", ["golden", "fresh", "tms"])
def test_ctrf_report_is_valid_for_the_published_schema(tmp_path, ledger):
    if ledger == "golden":
        report = GOLDEN_DIR / "ctrf" / "ctrf-report.json"
    else:
        run_dir = build_ledger(tmp_path) if ledger == "fresh" else _tms_ledger(tmp_path)
        report = export_run(run_dir, "ctrf", tmp_path / "ctrf")[0]
    document = json.loads(report.read_text(encoding="utf-8"))
    errors = sorted(Draft7Validator(CTRF_SCHEMA).iter_errors(document), key=str)
    assert not errors, [f"{list(error.absolute_path)}: {error.message}" for error in errors[:5]]
