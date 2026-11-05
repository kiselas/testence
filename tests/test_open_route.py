"""``ex.open``: the app's router when it is mounted, a document load otherwise.

``ex.open(route)`` hands an in-app route to the application's own router when the
application is mounted on this origin and loads the document otherwise; the step
records which path it took.
"""

from __future__ import annotations

import json
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
        if self.path.startswith("/blank"):
            body = BLANK.encode()
        elif self.path.startswith("/s/"):
            # Rendered on the server, no router: popstate changes nothing on the page.
            body = f"<!doctype html><div id='root'>static {self.path}</div>".encode()
        else:
            body = ROUTER.encode()
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
        writer.close()


def _step_ends(ex: Actions) -> list[dict[str, Any]]:
    lines = ex.writer.path.read_text(encoding="utf-8").splitlines()
    return [doc for doc in map(json.loads, lines) if doc["kind"] == "step.end"]


def test_open_loads_first_then_routes_client_side(ex, browser):
    assert ex.open("/r/a") == "goto"
    ex.expect_text(ROOT, "route /r/a")
    assert ex.open("/r/b") == "navigate"
    ex.expect_text(ROOT, "route /r/b")
    # The router answered: the document was loaded once.
    assert browser.eval_js("document.getElementById('root').dataset.loads") == "1"
    assert [e.get("navigation") for e in _step_ends(ex) if "navigation" in e] == [
        "goto",
        "navigate",
    ]


def test_open_loads_a_page_whose_app_is_not_mounted(ex):
    ex.goto("/blank")
    assert ex.open("/r/c") == "goto"
    ex.expect_text(ROOT, "route /r/c")


def test_open_loads_a_route_outside_the_app(ex, server):
    ex.open("/r/a")
    other = server.replace("127.0.0.1", "localhost") + "/r/x"
    assert ex.open(other) == "goto"


def test_open_loads_when_the_page_ignores_popstate(ex, browser):
    """A page whose router does not listen to popstate shows nothing new after a
    pushed route; open() notices that the document did not change and loads it."""
    ex.goto("/s/a")
    assert ex.open("/s/b") == "goto"
    ex.expect_text(ROOT, "static /s/b")
