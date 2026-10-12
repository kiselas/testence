"""Fresh contexts and observable, owned shutdown under worker browser reuse."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler
from types import SimpleNamespace

import pytest

from testence.debug import debug
from testence.engine.playwright_cdp import PlaywrightCdpEngine
from testence.loopback import LoopbackHTTPServer


@pytest.fixture
def consumer(tmp_path):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            api = self.path.startswith("/api/")
            body = (
                json.dumps(
                    {"source": "server", "authorization": self.headers.get("Authorization")}
                ).encode()
                if api
                else b"<h1>Healthy page</h1>"
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json" if api else "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = LoopbackHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    settings = {
        "auth": "none",
        "base_url": f"http://127.0.0.1:{server.server_port}",
        "evidence": {"trace": "on"},
        "extra": {
            "parallel": {"enabled": True, "accounts": "isolated", "cleanup": "asserted-absence"}
        },
    }
    (tmp_path / "testence.json").write_text(json.dumps(settings), encoding="utf-8")
    (tmp_path / "test_contexts.py").write_text(
        """import json
from pathlib import Path
import pytest
from testence.engine import Target

def clean(ex):
 ex.goto('/')
 assert ex.engine.eval_js("() => [document.cookie, localStorage.getItem('leak'),sessionStorage.getItem('leak'),window.leak || null]") == ['',None,None,None]
 session=ex.engine._browser.new_browser_cdp_session()
 pid=next(p['id'] for p in session.send('SystemInfo.getProcessInfo')['processInfo'] if p['type']=='browser')
 session.detach()
 with Path('pids.jsonl').open('a') as stream: stream.write(json.dumps(pid)+'\\n')
 ex.expect_text(Target('role','heading',name='Healthy page'),'Healthy page')

def test_a_seed(ex):
 clean(ex)
 ex.engine.eval_js("() => {document.cookie='leak=yes';localStorage.setItem('leak','yes');sessionStorage.setItem('leak','yes');window.leak='yes'}")
 ex.engine.set_extra_http_headers({'Authorization':'Bearer synthetic-test'})
 ex.route('**/api/probe', body='{"source":"injected"}', content_type='application/json')
 assert ex.engine.eval_js("async () => (await (await fetch('/api/probe')).json()).source") == 'injected'
 assert ex.engine.network_log()[-1].mocked

def test_b_isolated(ex):
 clean(ex)
 assert ex.engine.eval_js("async () => await (await fetch('/api/probe')).json()") == {'source':'server','authorization':None}
 assert not ex.engine.network_log()[-1].mocked

def test_c_failed_case(ex):
 clean(ex)
 ex.engine.timeout_ms=100
 ex.expect_text(Target('role','heading',name='Healthy page'),'wrong heading')

def test_d_after_failure(ex):
 clean(ex)
 assert ex.engine.eval_js("async () => await (await fetch('/api/probe')).json()") == {'source':'server','authorization':None}

@pytest.mark.testence_parallel
@pytest.mark.parametrize('case',range(8))
def test_parallel(case,ex,testence_namespace):
 clean(ex)
 path=Path(testence_namespace.marker)
 path.write_text(str(case))
 assert path.read_text()==str(case)
 path.unlink()
 assert not path.exists()
""",
        encoding="utf-8",
    )
    try:
        yield tmp_path
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("video", ["off", "retain-on-failure"])
def test_reuse_preserves_context_isolation_and_failure_trace(consumer, video):
    settings = json.loads((consumer / "testence.json").read_text())
    settings["evidence"]["video"] = video
    (consumer / "testence.json").write_text(json.dumps(settings))
    result = debug(consumer, "test_contexts.py", browser_reuse=True, allow_multiple=True)
    assert result["exit_code"] == 1 and not result["timed_out"]
    assert result["summary"]["execution"] == {"passed": 11, "failed": 1}
    assert len(set(json.loads(s) for s in (consumer / "pids.jsonl").read_text().splitlines())) == 1
    assert any("Healthy page" in p["aria"] for p in result["failure_packs"])
    from pathlib import Path

    assert len(list(Path(result["run_dir"]).rglob("trace.zip"))) == 12
    assert len(list(Path(result["run_dir"]).rglob("*.webm"))) == (1 if video != "off" else 0)
    assert result["phases"]["lifecycle_ms"]["browser.worker_close"] >= 0
    assert result["phases"]["lifecycle_ms"]["driver.stop"] >= 0
    assert result["phases"]["lifecycle_ms"]["context.release"] >= 0


def test_parallel_reuse_has_one_browser_per_worker_and_exact_cleanup(consumer):
    result = debug(
        consumer,
        "test_contexts.py::test_parallel",
        workers=4,
        allow_multiple=True,
        browser_reuse=True,
    )
    assert result["exit_code"] == 0 and result["summary"]["execution"] == {"passed": 8}
    assert len(set(json.loads(s) for s in (consumer / "pids.jsonl").read_text().splitlines())) == 4
    assert not list(consumer.glob("testence-*"))
    from pathlib import Path

    events = [
        json.loads(s)
        for p in Path(result["run_dir"]).glob("run*.jsonl")
        for s in p.read_text().splitlines()
    ]
    assert all(
        e["fingerprint"]["browser_reuse"] is True for e in events if e.get("kind") == "run.start"
    )
    assert len([e for e in events if e.get("lifecycle_phase") == "browser.worker_start"]) == 4
    assert len([e for e in events if e.get("lifecycle_phase") == "browser.worker_close"]) == 4


@pytest.mark.parametrize(
    "setting",
    [
        {"cdp_url": "http://127.0.0.1:1"},
        {"execution_mode": "attached"},
        {"execution_mode": "warm"},
        {"extra": {"user_data_dir": "synthetic-unused-profile"}},
        {"extra": {"browser_reuse": "yes"}},
    ],
)
def test_reuse_refuses_incompatible_scope_before_browser_launch(consumer, setting):
    path = consumer / "testence.json"
    settings = json.loads(path.read_text())
    settings.update(setting)
    path.write_text(json.dumps(settings))
    result = debug(consumer, "test_contexts.py::test_b_isolated", browser_reuse=True)
    assert result["exit_code"] != 0
    assert not (consumer / "pids.jsonl").exists()
    assert (
        "browser reuse requires isolated" in result["output_tail"]
        or "browser_reuse must be a boolean" in result["output_tail"]
    )


def test_stop_is_idempotent_and_failed_cleanup_is_visible():
    calls = []

    def close():
        calls.append("context")
        raise RuntimeError("synthetic broken transport")

    engine = PlaywrightCdpEngine()
    engine._context = SimpleNamespace(close=close)
    engine._browser = SimpleNamespace(close=lambda: calls.append("browser"))
    engine._pw = SimpleNamespace(stop=lambda: calls.append("driver"))
    engine._owns_context = engine._launched_here = True
    engine.stop()
    first = engine.wait_ledger()
    engine.stop()
    assert calls == ["context", "browser", "driver"]
    assert engine.wait_ledger() == first
    assert first[0]["op"] == "context.close" and first[0]["ok"] is False
    assert engine._pw is engine._browser is engine._context is None


def test_failed_sibling_configuration_closes_only_the_new_context(monkeypatch):
    calls = []
    context = SimpleNamespace(close=lambda: calls.append("child context"))
    owner = PlaywrightCdpEngine()
    owner._browser = SimpleNamespace(
        new_context=lambda **kwargs: context, close=lambda: pytest.fail("owner browser was closed")
    )
    owner._pw = SimpleNamespace(stop=lambda: pytest.fail("owner driver was stopped"))
    owner._owns_context = owner._launched_here = True

    def fail(_self):
        raise RuntimeError("synthetic context configure failure")

    monkeypatch.setattr(PlaywrightCdpEngine, "_configure_context", fail)
    with pytest.raises(RuntimeError, match="configure failure"):
        owner.sibling()
    assert calls == ["child context"]
    assert owner._pw is not None and owner._browser is not None


def test_failed_authentication_has_timing_without_running_the_case(consumer):
    (consumer / "conftest.py").write_text(
        """import testence.pytest_plugin as plugin
class Adapter:
 def authenticate(self, engine): raise RuntimeError('synthetic auth rejection')
plugin.from_settings=lambda settings: Adapter()
""",
        encoding="utf-8",
    )
    path = consumer / "testence.json"
    settings = json.loads(path.read_text())
    settings["auth"] = "form"
    path.write_text(json.dumps(settings))
    result = debug(consumer, "test_contexts.py::test_b_isolated", browser_reuse=True)
    assert result["exit_code"] == 1
    assert not (consumer / "pids.jsonl").exists()
    from pathlib import Path

    events = [
        json.loads(s) for s in (Path(result["run_dir"]) / "run.jsonl").read_text().splitlines()
    ]
    timing = [e for e in events if e.get("lifecycle_phase") == "auth"]
    assert len(timing) == 1 and timing[0]["ok"] is False
    assert timing[0]["duration_ms"] >= 0
    assert any(e.get("lifecycle_phase") == "browser.worker_close" for e in events)


def test_config_opt_in_and_mcp_use_the_same_worker_lifecycle(consumer):
    from testence.mcp import McpServer
    from tests.test_mcp import _call, _payload

    path = consumer / "testence.json"
    settings = json.loads(path.read_text())
    settings["extra"]["browser_reuse"] = True
    path.write_text(json.dumps(settings))
    result = _payload(
        _call(McpServer(consumer), "testence_debug", {"node": "test_contexts.py::test_b_isolated"})
    )
    assert result["exit_code"] == 0 and result["summary"]["execution"] == {"passed": 1}
    assert result["phases"]["lifecycle_ms"]["browser.worker_close"] >= 0
    invalid = _call(
        McpServer(consumer),
        "testence_debug",
        {"node": "test_contexts.py::test_b_isolated", "browser_reuse": "yes"},
    )
    assert invalid["isError"]


def test_interrupted_engine_phase_is_not_recorded_as_success():
    engine = PlaywrightCdpEngine()
    with pytest.raises(KeyboardInterrupt), engine._measure("synthetic interrupted phase"):
        raise KeyboardInterrupt()
    assert engine.wait_ledger()[-1]["ok"] is False
