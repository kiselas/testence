"""The render probe after ``goto`` waits for the first step without a target.

The probe asks "has the application painted anything", which a step with a target
answers better by waiting for its own element. It used to run after every goto
(178 ms on average on a React application); now a step with a target skips it, a
step without one (a URL check, a screenshot, an oracle) runs it first, and a probe
still due at the end of the test runs then.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler
from typing import Any

import pytest

from testence.dsl import Actions
from testence.engine import Target
from testence.engine.playwright_cdp import PlaywrightCdpEngine
from testence.evidence import EvidenceWriter
from testence.loopback import LoopbackHTTPServer

#: A minimal client-side router: it renders the path, follows popstate and counts
#: document loads in sessionStorage, so a reload is visible.
ROUTER = """<!doctype html><html><body><div id="root"></div>
<script>
window.__loads = Number(sessionStorage.getItem('loads') || 0) + 1;
sessionStorage.setItem('loads', String(window.__loads));
const render = () => {
  const root = document.getElementById('root');
  root.textContent = 'route ' + location.pathname;
  root.dataset.loads = String(window.__loads);
};
window.addEventListener('popstate', render);
render();
</script></body></html>"""

BLANK = "<!doctype html><html><body><div id='root'></div></body></html>"
ROOT = Target("css", "#root")


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args: Any) -> None:
        pass

    def do_GET(self) -> None:  # noqa: N802
        body = (BLANK if self.path.startswith("/blank") else ROUTER).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(scope="module")
def server() -> Iterator[str]:
    httpd = LoopbackHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()


@pytest.fixture(scope="module")
def browser(server) -> Iterator[PlaywrightCdpEngine]:
    engine = PlaywrightCdpEngine(base_url=server, headed=False)
    try:
        engine.start()
        yield engine
    finally:
        engine.stop()


@pytest.fixture
def ex(browser, tmp_path) -> Iterator[Actions]:
    browser.goto("about:blank")
    browser.reset_taps()
    writer = EvidenceWriter(tmp_path)
    try:
        yield Actions(browser, writer, "test_open.py::case")
    finally:
        browser.defer_render_probe = False
        writer.close()


def _ops(browser: PlaywrightCdpEngine) -> list[str]:
    return [entry["op"] for entry in browser.wait_ledger()]


def test_a_step_with_a_target_skips_the_render_probe(ex, browser):
    ex.goto("/r/a")
    ex.expect_text(ROOT, "route /r/a")
    ops = _ops(browser)
    assert "wait_until_rendered" not in ops
    assert "wait_until_rendered(skipped)" in ops


def test_a_step_without_a_target_gets_the_probe(ex, browser):
    ex.goto("/r/a")
    ex.expect_url(contains="/r/a")
    assert "wait_until_rendered" in _ops(browser)


def test_the_probe_still_due_at_the_end_of_the_test_runs(ex, browser):
    ex.goto("/r/a")
    ex.finish()
    assert "wait_until_rendered" in _ops(browser)


def test_a_direct_engine_call_after_goto_gets_the_probe(ex, browser):
    """A test may mix DSL steps with direct engine calls; those keep the old rule."""
    ex.goto("/r/a")
    browser.wait_while_visible(Target("css", "#absent"), timeout_ms=1_000)
    assert "wait_until_rendered" in _ops(browser)
