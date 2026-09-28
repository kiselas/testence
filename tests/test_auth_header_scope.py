"""Auth headers reach the target's origins only (product review 2026-09-28, P0-1).

Bearer and Basic credentials were set on the whole browser context, so the token or
the password went with every request the page made: to a CDN, analytics, a font host.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler
from typing import Any

import pytest

from testence.engine.playwright_cdp import PlaywrightCdpEngine
from testence.loopback import LoopbackHTTPServer


class _Recorder(BaseHTTPRequestHandler):
    seen: list[tuple[str, str | None]]
    page = b""

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        type(self).seen.append((self.path, self.headers.get("Authorization")))
        body = type(self).page if self.path == "/" else b"ok"
        self.send_response(200)
        self.send_header("Content-Type", "text/html" if self.path == "/" else "text/plain")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass


def _serve(handler: type[_Recorder]) -> tuple[LoopbackHTTPServer, str]:
    server = LoopbackHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}"


@pytest.fixture
def origins() -> Iterator[tuple[type[_Recorder], str, type[_Recorder], str]]:
    target = type("Target", (_Recorder,), {"seen": []})
    third = type("Third", (_Recorder,), {"seen": []})
    third_server, third_url = _serve(third)
    target.page = (
        f"<img src='{third_url}/pixel.png'>"
        "<script>fetch('/api/me').then(() => document.title = 'loaded')</script>"
    ).encode()
    target_server, target_url = _serve(target)
    try:
        yield target, target_url, third, third_url
    finally:
        for server in (target_server, third_server):
            server.shutdown()
            server.server_close()


def _open(engine: PlaywrightCdpEngine, url: str) -> None:
    engine.start()
    engine.set_extra_http_headers({"Authorization": "Bearer secret-token"})
    engine.goto(url + "/")
    engine._require_page().wait_for_function("document.title === 'loaded'")


def _authorization(recorder: type[_Recorder], path: str) -> str | None:
    return next(header for seen, header in recorder.seen if seen == path)


def test_the_token_goes_to_the_target_and_not_to_a_third_party(origins):
    target, target_url, third, third_url = origins
    engine = PlaywrightCdpEngine(base_url=target_url, headed=False)
    try:
        _open(engine, target_url)
    finally:
        engine.stop()
    assert _authorization(target, "/") == "Bearer secret-token"
    assert _authorization(target, "/api/me") == "Bearer secret-token"
    assert _authorization(third, "/pixel.png") is None


def test_an_allowed_api_origin_receives_the_token_too(origins):
    target, target_url, third, third_url = origins
    engine = PlaywrightCdpEngine(base_url=target_url, headed=False, credential_origins=(third_url,))
    try:
        _open(engine, target_url)
    finally:
        engine.stop()
    assert _authorization(third, "/pixel.png") == "Bearer secret-token"


def test_headers_without_a_named_origin_are_refused():
    engine = PlaywrightCdpEngine(base_url="", headed=False)
    try:
        engine.start()
        with pytest.raises(RuntimeError, match="need base_url"):
            engine.set_extra_http_headers({"Authorization": "Bearer secret-token"})
    finally:
        engine.stop()
