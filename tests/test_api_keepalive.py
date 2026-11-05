"""The API client keeps its connections alive (one per origin).

urllib opened a new connection, and on HTTPS a new TLS handshake, for every call; on
a remote test environment that was tens of seconds a run. The client now reuses one
connection per origin, retries once when the server closed an idle connection, and
closes its connections at the end of the test. The redirect policy, TLS settings and
evidence are unchanged.
"""

from __future__ import annotations

import json
import socket
import threading
import urllib.error
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler
from typing import Any

import pytest

from testence.api import ApiClient, ConnectionPool, UnsafeRequestTarget, http_json
from testence.auth.base import AuthContext
from testence.loopback import LoopbackHTTPServer


class _CountingServer(LoopbackHTTPServer):
    def __init__(self, handler: type[BaseHTTPRequestHandler]) -> None:
        super().__init__(("127.0.0.1", 0), handler)
        self.accepted = 0
        self.requests: list[tuple[str, str, bytes]] = []
        #: Close each connection after this many answers, as a keep-alive timeout would.
        self.answers_per_connection = 0

    def get_request(self):  # type: ignore[no-untyped-def]
        accepted = super().get_request()
        self.accepted += 1
        return accepted


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server: _CountingServer

    def log_message(self, *args: Any) -> None:
        pass

    def setup(self) -> None:
        super().setup()
        self.answered = 0

    def _answer(self, status: int, doc: Any, extra: list[tuple[str, str]] = ()) -> None:  # type: ignore[assignment]
        body = json.dumps(doc).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for name, value in extra:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()
        self.answered += 1
        limit = self.server.answers_per_connection
        if limit and self.answered >= limit:
            # Close without saying so, like a server whose keep-alive timer ran out.
            self.close_connection = True

    def _route(self, method: str) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        self.server.requests.append((method, self.path, body))
        if self.path == "/moved":
            self._answer(302, {}, [("Location", "/items/1")])
        elif self.path == "/away":
            self._answer(302, {}, [("Location", "http://127.0.0.2:9/stolen")])
        elif self.path == "/created":
            self._answer(303, {}, [("Location", "/items/2")])
        else:
            self._answer(200, {"path": self.path, "method": method})

    def do_GET(self) -> None:  # noqa: N802
        self._route("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._route("POST")


@pytest.fixture
def server() -> Iterator[_CountingServer]:
    httpd = _CountingServer(_Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd
    finally:
        httpd.shutdown()
        httpd.server_close()


def _base(server: _CountingServer) -> str:
    return f"http://127.0.0.1:{server.server_address[1]}"


def test_ten_calls_share_one_connection(server):
    recorded: list[dict[str, Any]] = []
    with ApiClient(_base(server), recorder=lambda **fields: recorded.append(fields)) as client:
        for index in range(10):
            response = client.get(f"/items/{index}")
            assert response.status == 200 and response.json["path"] == f"/items/{index}"
    assert server.accepted == 1
    assert client.pool.opened == 1
    assert [call["status"] for call in recorded] == [200] * 10


def test_an_idle_connection_the_server_closed_is_not_used(server):
    server.answers_per_connection = 1
    with ApiClient(_base(server)) as client:
        assert client.get("/items/1").status == 200
        assert client.post("/items", {"name": "a"}).status == 200
        assert client.get("/items/3").status == 200
    # Each call after the first found its idle connection closed and opened a new
    # one before sending: every request reached the server once.
    assert server.accepted == 3
    assert [method for method, _path, _body in server.requests] == ["GET", "POST", "GET"]


class _DropsSecondRequest(_Handler):
    """Answers the first request of a connection; reads the second and hangs up
    without an answer, as a server whose keep-alive timer fires mid-request."""

    def _route(self, method: str) -> None:
        if self.answered == 0:
            super()._route(method)
            return
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        self.server.requests.append((method, self.path, body))
        self.close_connection = True


def test_a_post_on_a_connection_that_drops_is_not_sent_twice(server):
    server.RequestHandlerClass = _DropsSecondRequest
    with ApiClient(_base(server)) as client:
        assert client.get("/items/1").status == 200
        with pytest.raises(urllib.error.URLError):
            client.post("/items", {"name": "seed"})
    # The server saw the POST once; the client did not repeat it behind the test.
    assert [method for method, _path, _body in server.requests] == ["GET", "POST"]
    assert server.accepted == 1


def test_an_idempotent_request_on_a_connection_that_drops_is_repeated_once(server):
    server.RequestHandlerClass = _DropsSecondRequest
    with ApiClient(_base(server)) as client:
        assert client.get("/items/1").status == 200
        assert client.get("/items/2").json["path"] == "/items/2"
    assert [path for _method, path, _body in server.requests] == [
        "/items/1",
        "/items/2",
        "/items/2",
    ]
    assert server.accepted == 2


def test_the_proxy_follows_the_environment_between_calls(monkeypatch):
    from testence.api import _proxy_for

    monkeypatch.setenv("HTTP_PROXY", "http://first.invalid:3128")
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    assert _proxy_for("http", "app.example.test") == "http://first.invalid:3128"
    monkeypatch.setenv("HTTP_PROXY", "http://second.invalid:3128")
    assert _proxy_for("http", "app.example.test") == "http://second.invalid:3128"
    monkeypatch.setenv("NO_PROXY", "app.example.test")
    assert _proxy_for("http", "app.example.test") == ""


def test_a_new_connection_that_fails_is_not_retried():
    accepted = []
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(4)

    def drop() -> None:
        connection, _ = listener.accept()
        accepted.append(1)
        connection.recv(65536)
        connection.close()  # no answer at all

    thread = threading.Thread(target=drop, daemon=True)
    thread.start()
    try:
        with pytest.raises(urllib.error.URLError):
            ApiClient(f"http://127.0.0.1:{listener.getsockname()[1]}").get("/items/1")
        thread.join(5)
        assert accepted == [1]
    finally:
        listener.close()


def test_close_releases_the_connection_and_a_later_call_reopens(server):
    client = ApiClient(_base(server))
    client.get("/items/1")
    client.close()
    client.get("/items/2")
    client.close()
    assert server.accepted == 2


def test_redirects_stay_on_the_origin_and_follow_like_urllib(server):
    pool = ConnectionPool()
    moved = http_json("GET", _base(server) + "/moved", pool=pool)
    assert moved.json == {"path": "/items/1", "method": "GET"}
    created = http_json("POST", _base(server) + "/created", body={"name": "a"}, pool=pool)
    assert created.json == {"path": "/items/2", "method": "GET"}
    post_after_303 = server.requests[-1]
    assert post_after_303 == ("GET", "/items/2", b"")
    with pytest.raises(UnsafeRequestTarget, match="cross-origin redirect"):
        http_json("GET", _base(server) + "/away", headers={"Authorization": "Bearer x"}, pool=pool)
    pool.close()
    assert pool.opened == 1 and server.accepted == 1


def test_a_post_answered_with_a_temporary_redirect_is_data(server):
    """urllib did not repeat a POST on 307/308; neither does the pool."""

    class _Temporary(_Handler):
        def do_POST(self) -> None:  # noqa: N802
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            self._answer(307, {"detail": "elsewhere"}, [("Location", "/items/9")])

    server.RequestHandlerClass = _Temporary
    response = http_json("POST", _base(server) + "/items", body={"a": 1}, pool=ConnectionPool())
    assert response.status == 307 and response.json == {"detail": "elsewhere"}


def test_cookies_and_headers_still_reach_the_server(server):
    seen: list[str] = []

    class _Echo(_Handler):
        def do_GET(self) -> None:  # noqa: N802
            seen.append(self.headers.get("Cookie", ""))
            self._answer(200, {})

    server.RequestHandlerClass = _Echo
    auth = AuthContext(cookies=[{"name": "sid", "value": "v1", "domain": "127.0.0.1", "path": "/"}])
    with ApiClient(_base(server), auth) as client:
        client.get("/a")
        client.get("/b")
    assert seen == ["sid=v1", "sid=v1"] and server.accepted == 1
