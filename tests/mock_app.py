"""A tiny app that authenticates every way we support — the auth test fixture.

It exists so the auth strategies are verified against real HTTP and a real browser
on every test run, with no external application, network or real credentials. Stdlib only.

Routes:
  GET  /login          login form (HTML)
  POST /login          form submit -> Set-Cookie: session_id, redirect /app
  GET  /app            protected page; shows the signed-in user or a 401 page
  POST /api/v1/auth/login   JSON {email,password} -> Set-Cookie: session_id
  POST /api/v1/auth/token   JSON {username,password} -> {"access_token": ...}
  GET  /api/v1/auth/me      accepts session cookie, bearer token, or basic
  GET  /api/v1/widgets/{id} demo entity for oracle tests
"""

from __future__ import annotations

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

USER = "demo@example.test"
PASSWORD = "demo-password"
SESSION_COOKIE = "session_id"
SESSION_VALUE = "sess-abc123"
TOKEN_VALUE = "token-xyz789"

#: Entities created through the form, so an oracle has something to re-read.
WIDGETS: dict[str, dict] = {}

_LOGIN_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>Sign in</title></head><body>
<h1>Sign in</h1>
<form method="POST" action="/login">
  <label for="email">Email</label>
  <input id="email" name="email" type="email" placeholder="email">
  <label for="password">Password</label>
  <input id="password" name="password" type="password" placeholder="password">
  <button type="submit">Sign in</button>
</form>
<div id="error">__ERROR__</div>
</body></html>"""

_APP_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>App</title></head><body>
<h1>Dashboard</h1>
<div id="whoami">signed in as __USER__</div>
<button id="reload">reload</button>
</body></html>"""

_DENIED_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>Denied</title></head><body><h1>401</h1>
<div id="whoami">not signed in</div></body></html>"""

#: A create form with client-side validation, so tests can exercise both the happy
#: path and the "front end refused to send" case. ``?drift=1`` makes the page show
#: a value the server never stored — how an oracle failure is reproduced on demand.
_WIDGET_FORM = """<!doctype html><html><head><meta charset="utf-8">
<title>New widget</title></head><body>
<h1>New widget</h1>
<form id="form" onsubmit="return submitWidget(event)">
  <label for="name">Name</label><input id="name" name="name">
  <label for="cidr">CIDR</label><input id="cidr" name="cidr">
  <div id="error"></div>
  <button type="submit" id="save-widget">Save</button>
</form>
<div id="saved"></div>
<script>
const drift = new URLSearchParams(location.search).has('drift');
function submitWidget(event) {
  event.preventDefault();
  const name = document.getElementById('name').value;
  const cidr = document.getElementById('cidr').value;
  // Deliberately naive client validation: a copy of the server rule, which is
  // exactly how the two drift apart in real applications.
  if (!/^\d+\.\d+\.\d+\.\d+\/\d+$/.test(cidr)) {
    document.getElementById('error').textContent = 'CIDR looks wrong';
    return false;
  }
  fetch('/api/v1/widgets', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({name: name, cidr: cidr}),
  }).then(r => r.json()).then(doc => {
    document.getElementById('saved').textContent =
      'saved ' + doc.id + ' as ' + (drift ? '10.9.9.9/32' : doc.cidr);
    document.getElementById('saved').dataset.id = doc.id;
    document.getElementById('saved').dataset.cidr = drift ? '10.9.9.9/32' : doc.cidr;
  });
  return false;
}
</script>
</body></html>"""


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args: Any) -> None:  # keep pytest output clean
        pass

    # -- helpers ---------------------------------------------------------
    def _send(self, status: int, body: str, content_type: str,
              extra: list[tuple[str, str]] | None = None) -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        for name, value in extra or []:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(payload)

    def _html(self, status: int, body: str, extra=None) -> None:
        self._send(status, body, "text/html; charset=utf-8", extra)

    def _json(self, status: int, doc: Any, extra=None) -> None:
        self._send(status, json.dumps(doc), "application/json", extra)

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def _authenticated(self) -> bool:
        cookie = self.headers.get("Cookie") or ""
        if f"{SESSION_COOKIE}={SESSION_VALUE}" in cookie:
            return True
        authorization = self.headers.get("Authorization") or ""
        if authorization == f"Bearer {TOKEN_VALUE}":
            return True
        if authorization.startswith("Basic "):
            raw = base64.b64decode(authorization[len("Basic "):]).decode()
            return raw == f"{USER}:{PASSWORD}"
        return False

    # -- routes ----------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/login":
            self._html(200, _LOGIN_PAGE.replace("__ERROR__", ""))
        elif path == "/app":
            if self._authenticated():
                self._html(200, _APP_PAGE.replace("__USER__", USER))
            else:
                self._html(401, _DENIED_PAGE)
        elif path == "/api/v1/auth/me":
            if self._authenticated():
                self._json(200, {"email": USER, "role": "admin"})
            else:
                self._json(401, {"detail": "not authenticated"})
        elif path == "/widgets/new":
            self._html(200, _WIDGET_FORM)
        elif path.startswith("/api/v1/widgets/"):
            if not self._authenticated():
                self._json(401, {"detail": "not authenticated"})
                return
            widget_id = path.rsplit("/", 1)[-1]
            stored = WIDGETS.get(widget_id)
            if stored is not None:
                self._json(200, stored)
            else:
                self._json(200, {"id": widget_id, "cidr": "10.0.0.0/24"})
        else:
            self._html(404, "<h1>404</h1>")

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        raw = self._read_body()
        if path == "/login":
            from urllib.parse import parse_qs

            form = {k: v[0] for k, v in parse_qs(raw.decode()).items()}
            if form.get("email") == USER and form.get("password") == PASSWORD:
                self.send_response(303)
                self.send_header("Location", "/app")
                self.send_header("Set-Cookie", f"{SESSION_COOKIE}={SESSION_VALUE}; Path=/")
                self.send_header("Content-Length", "0")
                self.end_headers()
            else:
                self._html(200, _LOGIN_PAGE.replace("__ERROR__", "Invalid credentials"))
            return
        try:
            document = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            document = {}
        if path == "/api/v1/auth/login":
            if document.get("email") == USER and document.get("password") == PASSWORD:
                self._json(200, {"user": {"email": USER}},
                           extra=[("Set-Cookie", f"{SESSION_COOKIE}={SESSION_VALUE}; Path=/")])
            else:
                self._json(401, {"detail": "invalid credentials"})
        elif path == "/api/v1/widgets":
            if not self._authenticated():
                self._json(401, {"detail": "not authenticated"})
                return
            widget_id = f"w{len(WIDGETS) + 1}"
            stored = {"id": widget_id, "name": document.get("name"),
                      "cidr": document.get("cidr")}
            WIDGETS[widget_id] = stored
            self._json(201, stored)
        elif path == "/api/v1/auth/token":
            if document.get("username") == USER and document.get("password") == PASSWORD:
                self._json(200, {"access_token": TOKEN_VALUE, "token_type": "bearer"})
            else:
                self._json(401, {"detail": "invalid credentials"})
        else:
            self._json(404, {"detail": "not found"})


class MockApp:
    """Context manager yielding ``base_url`` of a live server on a free port."""

    def __init__(self) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self.server.server_address[:2]
        return f"http://{host}:{port}"

    def __enter__(self) -> "MockApp":
        self.thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.server.shutdown()
        self.server.server_close()
