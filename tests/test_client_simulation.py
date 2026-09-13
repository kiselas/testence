import importlib.util
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "fault", [None, "wrong-reason", "missing", "skipped", "unverified", "integrity"]
)
def test_simulation_cannot_grade_unproven_failures_as_detection(tmp_path, fault):
    path = Path(__file__).parents[1] / "bench/client_simulation/run.py"
    spec = importlib.util.spec_from_file_location("client_simulation", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    message = (
        "navigation timed out" if fault == "wrong-reason" else "visual mismatch: 12 pixels changed"
    )
    case = f'<testcase><failure message="{message}"/></testcase>'
    cases = case if fault == "missing" else case * 2
    if fault == "skipped":
        cases = cases.replace("<failure", "<skipped")
    junit = tmp_path / "result.xml"
    junit.write_text(f"<testsuites><testsuite>{cases}</testsuite></testsuites>")
    inspection = {"assurance": {"violated": 2}, "integrity_errors": []}
    if fault == "unverified":
        inspection["assurance"] = {"unverified": 2}
    if fault == "integrity":
        inspection["integrity_errors"] = ["wrong binding"]
    assert module.grade(junit, inspection, 1, True) is (fault is None)
