import importlib.util
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import pytest

from testence.loopback import LoopbackHTTPServer


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


def _load_run():
    path = Path(__file__).parents[1] / "bench/client_simulation/run.py"
    spec = importlib.util.spec_from_file_location("client_simulation_warmup", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_warm_up_takes_screenshots_so_the_first_scenario_does_not_pay_for_them():
    """Every failed visual job was a screenshot of a freshly launched browser (timeout or
    two unlike captures); the warm-up has to exercise that path, not only launch and goto."""
    code = _load_run().WARMUP_CODE
    assert code.count("engine.screenshot(") == 1 and "for number in (1, 2)" in code
    assert (
        code.index("engine.goto(") < code.index("engine.screenshot(") < code.index("engine.stop(")
    )


def test_the_warm_up_runs_against_a_real_page_and_takes_both_screenshots():
    panel = (Path(__file__).parents[1] / "bench/client_simulation/panel.html").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(panel)))
            self.end_headers()
            self.wfile.write(panel)

    server = LoopbackHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    process = subprocess.Popen(
        [sys.executable, "-c", _load_run().WARMUP_CODE, f"http://127.0.0.1:{server.server_port}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    line: list[str] = []
    reader = threading.Thread(
        target=lambda: line.append(process.stdout.readline()),  # type: ignore[union-attr]
        daemon=True,
    )
    reader.start()
    try:
        # What is under test is the screenshots, not how long this host takes to close
        # its browser afterwards: stop waiting once they are reported.
        reader.join(timeout=300)
    finally:
        process.kill()
        process.wait(timeout=30)
        server.shutdown()
        server.server_close()
    assert line and "warm-up screenshots: 2" in line[0]
