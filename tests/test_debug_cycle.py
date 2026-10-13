"""Exact-case debug and byte-preserving response adaptation, synthetic targets only."""

from __future__ import annotations

import hashlib
import json
import threading
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import pytest

from testence.debug import debug, phase_timings, project_status
from testence.dsl import Actions
from testence.dsl.steps import StepFailed
from testence.engine import Target
from testence.engine.playwright_cdp import PlaywrightCdpEngine
from testence.evidence import EvidenceWriter
from testence.loopback import LoopbackHTTPServer

PAGE = b"""<!doctype html><meta charset=utf-8>
<input id=file type=file><button id=send>Send</button>
<p id=reply></p><div id=late hidden>Too large</div>
<button id=xhr>Send XHR</button>
<button id=latebutton onclick="window.sends=(window.sends||0)+1;setTimeout(()=>late.hidden=false,150)">Delayed result</button>
<script>send.onclick=async()=>{
 const form=new FormData();form.append('file',file.files[0]);
 const response=await fetch('/api/upload',{method:'POST',body:form});
 reply.textContent=JSON.stringify(await response.json());
};
xhr.onclick=()=>{const form=new FormData();form.append('file',file.files[0]);
 const request=new XMLHttpRequest();request.open('POST','/api/upload');
 request.onload=()=>reply.textContent=request.responseText;request.send(form);
};</script>"""


@pytest.fixture
def receiver():
    uploads = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", str(len(PAGE)))
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(PAGE)

        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            mime = BytesParser(policy=default).parsebytes(
                ("Content-Type: " + self.headers["Content-Type"] + "\r\n\r\n").encode() + body
            )
            part = next(mime.iter_parts())
            uploads.append(
                {
                    "bytes": part.get_payload(decode=True),
                    "filename": part.get_filename(),
                    "content_type": part.get_content_type(),
                    "authorization": self.headers.get("Authorization"),
                }
            )
            payload = json.dumps(
                {"backend": "received", "sha256": hashlib.sha256(uploads[-1]["bytes"]).hexdigest()}
            ).encode()
            self.send_response(201)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = LoopbackHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", uploads
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


@pytest.fixture
def ex(tmp_path, receiver):
    engine = PlaywrightCdpEngine(headed=False, base_url=receiver[0])
    writer = EvidenceWriter(tmp_path / "evidence")
    try:
        engine.start()
        engine.goto("/")
        # A cold browser's first navigation gets the default budget; the checks after it
        # keep a short one so the expected failures stay quick.
        engine.timeout_ms = 2000
        yield Actions(engine, writer, "debug-cycle")
    finally:
        engine.stop()
        writer.close()


def test_upload_rewrite_preserves_exact_file_once_and_marks_provenance(ex, receiver, tmp_path):
    raw = bytes(range(256)) * 64 + b"\x00multipart\r\nend"
    # An extension no OS maps to a type: macOS sends .bin as application/macbinary,
    # so the browser-chosen type would differ by host rather than by adapter.
    path = tmp_path / "synthetic.tstbin"
    path.write_bytes(raw)
    ex.rewrite_response(
        "*/api/upload", lambda original: {"adapted": original["sha256"]}, method="POST"
    )
    ex.upload(Target("css", "#file"), [str(path)])
    with ex.expect_request("/api/upload", method="POST") as sent:
        ex.click(Target("css", "#send"))
    ex.expect_text(
        Target("css", "#reply"),
        json.dumps({"adapted": hashlib.sha256(raw).hexdigest()}, separators=(",", ":")),
    )
    assert receiver[1] == [
        {
            "bytes": raw,
            "filename": "synthetic.tstbin",
            "content_type": "application/octet-stream",
            "authorization": None,
        }
    ]
    assert sent.response.status == 201 and sent.response.mocked
    ex.writer.close()
    assert "response-rewrite" in ex.writer.path.read_text(encoding="utf-8")


def test_rewrite_failure_does_not_send_a_second_upload(ex, receiver, tmp_path):
    def broken(_body):
        raise ValueError("synthetic adapter error")

    ex.rewrite_response("*/api/upload", broken)
    path = tmp_path / "synthetic.tstbin"
    path.write_bytes(b"original file")
    ex.upload(Target("css", "#file"), [str(path)])
    with pytest.raises(StepFailed, match="response adapter failed"):
        with ex.expect_request("/api/upload", method="POST"):
            ex.click(Target("css", "#send"))
    assert len(receiver[1]) == 1 and receiver[1][0]["bytes"] == b"original file"


def test_delayed_outcome_waits_without_repeating_action(ex):
    with ex.expect_outcome(
        {"rejected": Target("css", "#late")}, expected="rejected", timeout_ms=5000
    ) as observed:
        ex.click(Target("css", "#latebutton"))
    assert observed.name == "rejected"
    assert ex.engine.eval_js("() => window.sends") == 1
    with pytest.raises(StepFailed, match="already visible"):
        with ex.expect_outcome({"rejected": Target("css", "#late")}):
            pytest.fail("stale result allowed another action")


def test_absent_outcome_is_unobserved_not_silent_rejection(ex):
    with pytest.raises(StepFailed, match="outcome unobserved"):
        with ex.expect_outcome({"rejected": Target("css", "#late")}, timeout_ms=80):
            pass


@pytest.fixture
def project(tmp_path):
    (tmp_path / "testence.json").write_text(
        json.dumps(
            {
                "auth": "none",
                "extra": {
                    "parallel": {
                        "enabled": True,
                        "accounts": "non-revoking",
                        "cleanup": "asserted-absence",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "test_cases.py").write_text(
        """import pytest
from pathlib import Path
from testence.engine import Target
def test_one(): Path('executed').write_text('one')
def test_two(): Path('executed').write_text('two')
def test_ui_failure(ex):
 ex.goto('data:text/html,<h1>Actual heading</h1>')
 ex.engine.timeout_ms=100
 ex.expect_text(Target('role','heading',name='Actual heading'),'wrong heading')
@pytest.mark.testence_parallel
@pytest.mark.parametrize('number',range(4))
def test_isolated(number,testence_namespace):
 marker=testence_namespace.marker
 Path(marker).write_text(str(number))
 assert Path(marker).read_text()==str(number)
 Path(marker).unlink()
 assert not Path(marker).exists()
""",
        encoding="utf-8",
    )
    return tmp_path


def test_debug_refuses_unintended_suite_before_test_bodies(project):
    result = debug(project, "test_cases.py")
    assert not result["executed"] and len(result["selected"]) == 7
    assert not (project / "executed").exists()
    assert "choose one exact node" in result["error"]


def test_debug_executes_exactly_one_selected_case(project):
    result = debug(project, "test_cases.py::test_one")
    assert result["executed"] and result["exit_code"] == 0
    assert (project / "executed").read_text() == "one"
    assert result["summary"]["execution"] == {"passed": 1}
    assert result["phases"]["test_phase_ms"]["call"] >= 0


def test_debug_returns_aria_and_lifecycle_on_ui_failure(project):
    result = debug(project, "test_cases.py::test_ui_failure")
    assert result["exit_code"] == 1
    assert any("Actual heading" in pack["aria"] for pack in result["failure_packs"])
    assert {"browser.start", "auth", "recording", "browser.close"} <= result["phases"][
        "lifecycle_ms"
    ].keys()


def test_parallel_debug_requires_opt_in_and_namespace(project):
    blocked = debug(project, "test_cases.py::test_one", workers=4)
    assert not blocked["executed"] and "testence_parallel" in blocked["error"]
    result = debug(project, "test_cases.py::test_isolated", workers=4, allow_multiple=True)
    assert result["exit_code"] == 0
    assert result["summary"]["execution"] == {"passed": 4}


def test_status_locates_current_package_and_legacy_name(project):
    status = project_status(project)
    assert status["previous_name"] == "Exhibit"
    assert Path(status["package_path"]).name == "testence"
    assert status["settings"]["auth"] == "none"


def test_phase_timings_never_add_nested_totals():
    result = phase_timings(
        [
            {"kind": "test.phase", "phase": "setup", "duration_ms": 100},
            {"kind": "note", "lifecycle_phase": "auth", "duration_ms": 40},
        ]
    )
    assert result["test_phase_ms"] == {"setup": 100}
    assert result["lifecycle_ms"] == {"auth": 40}


def test_xhr_upload_and_context_reset_leave_no_adapter(ex, receiver, tmp_path):
    path = tmp_path / "synthetic.tstbin"
    path.write_bytes(b"xhr bytes")
    ex.rewrite_response("*/api/upload", lambda _body: {"via": "xhr"})
    ex.upload(Target("css", "#file"), [str(path)])
    ex.click(Target("css", "#xhr"))
    ex.expect_text(Target("css", "#reply"), json.dumps({"via": "xhr"}))
    assert receiver[1][0]["bytes"] == b"xhr bytes"
    ex.engine.reset_session()
    ex.goto("/")
    ex.upload(Target("css", "#file"), [str(path)])
    ex.click(Target("css", "#send"))
    ex.expect_text(Target("css", "#reply"), '"backend":"received"', exact=False)
    assert len(receiver[1]) == 2
    assert not ex.engine.network_log()[-1].mocked


def test_conflicting_results_fail_explicitly(ex):
    with pytest.raises(StepFailed, match="conflicting outcomes"):
        with ex.expect_outcome(
            {"rejected": Target("css", "#late"), "report": Target("css", "#reply")}
        ):
            ex.engine.eval_js("() => {late.hidden=false;reply.textContent='report'}")


def test_debug_timeout_keeps_incomplete_evidence(project):
    (project / "test_hang.py").write_text(
        "import time\ndef test_hang():\n print('entered',flush=True)\n time.sleep(60)\n",
        encoding="utf-8",
    )
    result = debug(project, "test_hang.py::test_hang", timeout_s=4)
    assert result["executed"] and result["timed_out"] and result["exit_code"] == 124
    assert result["summary"]["run_status"] == "incomplete"


def test_debug_selection_drift_blocks_execution(project, tmp_path):
    from testence.debug_worker import Selection

    class Item:
        nodeid = "test_cases.py::test_one"
        path = project / "test_cases.py"
        fixturenames = []

        def get_closest_marker(self, _name):
            return None

    class Session:
        items = [Item()]

    saved = tmp_path / "selection.json"
    Selection(saved, False).pytest_collection_finish(Session())
    (project / "test_cases.py").write_text("changed source", encoding="utf-8")
    with pytest.raises(pytest.UsageError, match="collection changed"):
        Selection(saved, True).pytest_collection_finish(Session())


def test_status_invalid_privacy_does_not_echo_configuration(project, capsys):
    from testence.cli import main

    (project / "testence.json").write_text(
        json.dumps({"evidence": {"redact": {"pii": ["synthetic-private-invalid-kind"]}}}),
        encoding="utf-8",
    )
    assert main(["status", "--project", str(project), "--json"]) == 2
    assert "synthetic-private-invalid-kind" not in capsys.readouterr().err


def test_parallel_waits_do_not_become_serial_wall_percent():
    result = phase_timings(
        [
            {"kind": "test.waits", "by_op": {"goto": {"ms": 86400}}},
            {"kind": "run.end", "worker": "controller", "duration_ms": 344000},
        ]
    )
    assert result["navigation"]["percent_of_recorded_waits"] == 100
    assert result["navigation"]["percent_of_serial_run_wall"] == 25.1
    result = phase_timings(
        [
            {"kind": "run.end", "worker": "gw0"},
            {"kind": "run.end", "worker": "gw1"},
            {"kind": "run.end", "worker": "controller", "duration_ms": 100},
        ]
    )
    assert result["navigation"]["percent_of_serial_run_wall"] is None


def test_response_adapter_coexists_with_authorization_headers(ex, receiver, tmp_path):
    ex.engine.set_extra_http_headers({"Authorization": "Bearer synthetic-header"})
    ex.rewrite_response("*/api/upload", lambda body: {"adapted": body["backend"]})
    path = tmp_path / "synthetic.tstbin"
    path.write_bytes(b"authorized original file")
    ex.upload(Target("css", "#file"), [str(path)])
    ex.click(Target("css", "#send"))
    ex.expect_text(Target("css", "#reply"), '{"adapted":"received"}')
    assert len(receiver[1]) == 1
    assert receiver[1][0]["authorization"] == "Bearer synthetic-header"
    assert receiver[1][0]["bytes"] == b"authorized original file"
    assert ex.engine.network_log()[-1].mocked


def test_mcp_debug_and_status_use_guarded_cycle(project):
    from testence.mcp import McpServer
    from tests.test_mcp import _call, _payload

    server = McpServer(project)
    status = _payload(_call(server, "testence_status"))
    assert status["previous_name"] == "Exhibit"
    blocked = _payload(_call(server, "testence_debug", {"node": "test_cases.py"}))
    assert not blocked["executed"] and len(blocked["selected"]) == 7
    result = _payload(_call(server, "testence_debug", {"node": "test_cases.py::test_one"}))
    assert result["exit_code"] == 0 and result["summary"]["execution"] == {"passed": 1}
    invalid = _call(server, "testence_debug", {"node": "test_cases.py", "allow_multiple": "yes"})
    assert invalid["isError"]
