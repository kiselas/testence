"""JUnit XML exporter — the format every CI and test-management tool reads (ADR-0030).

``pytest --junitxml`` already writes JUnit, and it stays the right choice when a
job only needs pass/fail. This exporter exists for what that file cannot carry:
the Testence identity of each result, test-management case ids, the intent steps
and the evidence pack. Everything goes where the consumers look for it:

- ``<properties>`` per test case: ``testence.*`` identity and assurance, the Allure
  ID, and case ids under the names TestRail's ``trcli`` (``test_id``,
  ``testrail_result_step``, ``testrail_attachment``) and Xray (``test_key``,
  ``requirements``) document; any other system as ``tms.<system>``;
- ``<failure>`` for a product disagreement (an assertion or oracle), ``<error>`` for
  a broken or aborted test, ``<skipped>`` for skipped and not-run tests — the same
  split Allure makes between failed and broken;
- ``<system-out>``: the step intents as an indented tree, then one
  ``[[ATTACHMENT|path]]`` line per evidence file (Jenkins and GitLab render these);
- the evidence files themselves under ``attachments/``, copied with the export-time
  redaction and attachment policy (``copy_attachments``).

The dialect is the one ``pytest --junitxml`` writes by default (``junit_family=xunit1``):
Jenkins' strict ``junit-4.xsd`` in every respect but two, ``<properties>`` and ``file``
on a ``<testcase>``, which is precisely where ``trcli`` and Xray read case ids.

Stdlib only (ADR-0007), a pure function of the ledger like every exporter.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from ._model import ExportedFile, LoadedRun, Step, Test, copy_attachments

name = "junit"

#: Characters XML 1.0 cannot carry at all; a browser console can emit them.
_XML_INVALID = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")
#: ``trcli`` step statuses.
_TESTRAIL_STEP = {True: "failed", False: "passed"}
#: ``error_kind`` values that make a failed test an ``<error>`` (Allure "broken").
_BROKEN_KINDS = frozenset({"infrastructure", "test_code"})
#: Consumers truncate long messages anyway; the full trace is in the element body.
_MESSAGE_LIMIT = 1_000


def export(run: LoadedRun, out_dir: Path) -> list[Path]:
    written: list[Path] = []
    root = ET.Element("testsuites", {"name": "testence"})
    suites: dict[str, list[Test]] = {}
    for test in run.tests:
        suites.setdefault(_suite_name(test), []).append(test)
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite_name, tests in suites.items():
        suite = ET.SubElement(root, "testsuite", {"name": _text(suite_name)})
        counts = {"tests": len(tests), "failures": 0, "errors": 0, "skipped": 0}
        _properties(
            suite,
            [
                ("testence.run_id", run.run_id),
                ("testence.project_id", run.project_id),
                ("testence.version", run.testence_version),
                ("testence.run_status", run.run_status),
            ],
        )
        for test in tests:
            files = copy_attachments(run, test, out_dir)
            written.extend(out_dir / item.path for item in files)
            outcome = _testcase(suite, test, files)
            if outcome:
                counts[outcome] += 1
        suite_time = sum(test.duration_ms for test in tests) / 1000
        suite.set("time", f"{suite_time:.3f}")
        for key, value in counts.items():
            suite.set(key, str(value))
            totals[key] += value
        if tests and tests[0].start is not None:
            suite.set("timestamp", tests[0].start.replace(microsecond=0).isoformat())
    # junit-4.xsd allows no skipped count or timestamp on the root; the suites carry both.
    for key in ("tests", "failures", "errors"):
        root.set(key, str(totals[key]))
    root.set("time", f"{run.duration_ms / 1000:.3f}")
    ET.indent(root, space="  ")
    target = out_dir / "junit.xml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True) + b"\n")
    return [target, *written]


def _testcase(suite: ET.Element, test: Test, files: list[ExportedFile]) -> str:
    """Write one ``<testcase>``; return the counter it adds to (or ``""``)."""
    classname, case_name = _names(test)
    attributes = {
        "name": _text(case_name),
        "classname": _text(classname),
        "time": f"{test.duration_ms / 1000:.3f}",
    }
    if test.file:
        attributes["file"] = _text(test.file)
    case = ET.SubElement(suite, "testcase", attributes)
    _properties(case, _case_properties(test, files))
    outcome = ""
    message = _message(test)
    if test.status == "skipped":
        ET.SubElement(case, "skipped", {"message": message or "skipped"})
        outcome = "skipped"
    elif test.status == "not_run":
        ET.SubElement(case, "skipped", {"message": "not run"})
        outcome = "skipped"
    elif test.failed:
        # Allure's rule: a failure unless the environment or the test code broke, so a
        # ledger older than error_kind still reports its assertion as a failure.
        product = test.status in ("failed", "fail") and test.error_kind not in _BROKEN_KINDS
        element = ET.SubElement(
            case,
            "failure" if product else "error",
            {"message": message or test.status, "type": test.error_kind or test.status},
        )
        element.text = _text(test.error_trace or test.error or "")
        outcome = "failures" if product else "errors"
    out = _system_out(test, files)
    if out:
        ET.SubElement(case, "system-out").text = _text(out)
    return outcome


def _case_properties(test: Test, files: list[ExportedFile]) -> list[tuple[str, str]]:
    properties = [
        ("testence.case_id", test.case_id),
        ("testence.variant_id", test.variant_id),
        ("testence.proof_id", test.proof_id),
        ("testence.assurance", test.assurance),
        ("testence.nodeid", test.nodeid),
        ("allure_id", test.allure_id or str(test.allure.get("allure_id") or "")),
    ]
    for system, ids in sorted(test.tms.items()):
        if system == "testrail":
            properties.append(("test_id", ", ".join(ids)))
        elif system == "xray":
            properties.append(("test_key", ids[0]))
            requirements = [item["id"] for item in test.requirements if item.get("id")]
            if requirements:
                properties.append(("requirements", ",".join(requirements)))
        else:
            properties.append((f"tms.{system}", ", ".join(ids)))
    if "testrail" in test.tms:
        properties.extend(
            ("testrail_result_step", f"{_TESTRAIL_STEP[step.failed]}:{step.intent or step.step}")
            for step in _leaves(test.steps)
        )
        properties.extend(("testrail_attachment", item.path) for item in files)
    return [(key, value) for key, value in properties if value]


def _system_out(test: Test, files: list[ExportedFile]) -> str:
    lines: list[str] = []

    def walk(items: list[Step], depth: int) -> None:
        for step in items:
            mark = " [FAILED]" if step.failed else ""
            lines.append(f"{'  ' * depth}{step.intent or step.step}{mark}")
            walk(step.substeps, depth + 1)

    walk(test.steps, 0)
    if test.pack_dir:
        lines.append(f"evidence pack: {test.pack_dir}")
    lines.extend(f"[[ATTACHMENT|{item.path}]]" for item in files)
    return "\n".join(lines)


def _names(test: Test) -> tuple[str, str]:
    """``classname`` as allure-pytest's full name before ``#``; the test's display name."""
    full_name = str(test.allure.get("full_name") or "")
    if "#" in full_name:
        classname = full_name.split("#", 1)[0]
    else:
        path = test.nodeid.split("::", 1)[0]
        classname = path[:-3].replace("/", ".") if path.endswith(".py") else path
        middle = test.nodeid.split("::")[1:-1]
        if middle:
            classname = ".".join([classname, *middle])
    return classname or "testence", test.name or test.nodeid


def _suite_name(test: Test) -> str:
    return test.file or test.nodeid.split("::", 1)[0] or "testence"


def _message(test: Test) -> str:
    text = (test.error or "").strip().splitlines()
    return _text(text[0][:_MESSAGE_LIMIT]) if text else ""


def _leaves(steps: list[Step]) -> list[Step]:
    leaves: list[Step] = []
    for step in steps:
        leaves.extend(_leaves(step.substeps) if step.substeps else [step])
    return leaves


def _properties(parent: ET.Element, pairs: list[tuple[str, Any]]) -> None:
    kept = [(key, str(value)) for key, value in pairs if value not in (None, "")]
    if not kept:
        return
    element = ET.SubElement(parent, "properties")
    for key, value in kept:
        ET.SubElement(element, "property", {"name": key, "value": _text(value)})


def _text(value: str) -> str:
    return _XML_INVALID.sub("�", value)
