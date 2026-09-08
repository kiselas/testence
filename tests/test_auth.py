"""Every auth strategy, verified against a real browser and real HTTP.

These run on every commit: auth is the thing that breaks adoption, so it is the
thing that must not be verified by inspection.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from testence.api import ApiClient, Response, UnsafeRequestTarget, http_json
from testence.auth import (
    ApiSessionAuth,
    AttachedSessionAuth,
    AuthContext,
    BasicAuth,
    BearerTokenAuth,
    CachedSessionAuth,
    Credentials,
    FormLoginAuth,
    MissingCredentials,
    NoAuth,
)
from testence.engine import Target, worker_port_offset
from testence.engine.playwright_cdp import PlaywrightCdpEngine

from .mock_app import PASSWORD, SESSION_COOKIE, USER, MockApp

CREDS = Credentials(USER, PASSWORD, source="test-fixture")


@pytest.fixture(scope="module")
def app():
    with MockApp() as mock:
        yield mock


@pytest.fixture
def engine(app):
    eng = PlaywrightCdpEngine(
        base_url=app.base_url,
        headed=False,
        api_prefix="/api/",
        debug_port=9222 + worker_port_offset(),
    )
    eng.start()
    yield eng
    eng.stop()


# -- credential handling ---------------------------------------------------


def test_credentials_never_leak_in_repr():
    creds = Credentials("user@example.test", "s3cret")
    assert "s3cret" not in repr(creds)
    assert "s3cret" not in str(creds.redacted())


def test_missing_credentials_names_the_variables(monkeypatch):
    monkeypatch.delenv("TESTENCE_USER", raising=False)
    monkeypatch.delenv("TESTENCE_PASSWORD", raising=False)
    with pytest.raises(MissingCredentials, match="TESTENCE_USER"):
        Credentials.from_env()


def test_credentials_from_env(monkeypatch):
    monkeypatch.setenv("TESTENCE_USER", "u@example.test")
    monkeypatch.setenv("TESTENCE_PASSWORD", "p")
    creds = Credentials.from_env()
    assert creds.username == "u@example.test"
    assert creds.source == "env:TESTENCE_USER"


# -- strategies ------------------------------------------------------------


def test_form_login_authenticates_browser_and_captures_cookie(engine):
    """The default strategy: real form, real submit, session captured for APIs."""
    auth = FormLoginAuth(
        CREDS,
        login_path="/login",
        success_target=Target("css", "#whoami"),
    )
    context = auth.authenticate(engine)

    assert context.scheme == "form"
    assert any(c["name"] == SESSION_COOKIE for c in context.cookies)
    engine.goto("/app")
    assert USER in engine.read_text(Target("css", "#whoami"))


def test_form_login_wrong_password_fails_fast(engine):
    auth = FormLoginAuth(
        Credentials(USER, "wrong-password"),
        login_path="/login",
        success_target=Target("css", "#whoami"),
        timeout_ms=2_000,
    )
    with pytest.raises(Exception):
        auth.authenticate(engine)


def test_api_session_auth_injects_cookie_into_browser(engine, app):
    auth = ApiSessionAuth(CREDS, login_url=f"{app.base_url}/api/v1/auth/login")
    context = auth.authenticate(engine)

    assert context.scheme == "api-session"
    engine.goto("/app")  # browser is authenticated without ever seeing the form
    assert USER in engine.read_text(Target("css", "#whoami"))


def test_api_session_auth_explains_token_only_apis(engine, app):
    """A login endpoint that returns a token instead of a cookie must say so."""
    auth = ApiSessionAuth(
        CREDS,
        login_url=f"{app.base_url}/api/v1/auth/token",
        payload=lambda c: {"username": c.username, "password": c.password},
    )
    with pytest.raises(RuntimeError, match="BearerTokenAuth"):
        auth.authenticate(engine)


def test_bearer_token_auth_sets_header_and_storage(engine, app):
    auth = BearerTokenAuth(
        CREDS,
        token_url=f"{app.base_url}/api/v1/auth/token",
        storage_key="access_token",
    )
    context = auth.authenticate(engine)

    assert context.scheme == "bearer"
    assert context.headers["Authorization"].startswith("Bearer ")
    engine.goto("/app")
    assert USER in engine.read_text(Target("css", "#whoami"))
    assert engine.storage_snapshot().get("access_token")


def test_bearer_token_auth_reports_missing_field(engine, app):
    auth = BearerTokenAuth(
        CREDS, token_url=f"{app.base_url}/api/v1/auth/token", token_field="id_token"
    )
    with pytest.raises(RuntimeError, match="id_token"):
        auth.authenticate(engine)


def test_basic_auth_reaches_protected_page(engine):
    context = BasicAuth(CREDS).authenticate(engine)
    assert context.headers["Authorization"].startswith("Basic ")
    engine.goto("/app")
    assert USER in engine.read_text(Target("css", "#whoami"))


def test_attached_session_requires_existing_cookie(engine):
    auth = AttachedSessionAuth(require_cookie=SESSION_COOKIE)
    with pytest.raises(RuntimeError, match=SESSION_COOKIE):
        auth.authenticate(engine)  # fresh context has no session yet

    ApiSessionAuth(CREDS, login_url=f"{engine.base_url}/api/v1/auth/login").authenticate(engine)
    assert auth.authenticate(engine).scheme == "attached"


def test_no_auth_is_inert(engine):
    context = NoAuth().authenticate(engine)
    assert context.scheme == "none" and not context.cookies


# -- session sharing with API clients --------------------------------------


def test_api_client_inherits_browser_session(engine, app):
    """The oracle must read the API as the same user the UI is logged in as."""
    context = FormLoginAuth(
        CREDS, login_path="/login", success_target=Target("css", "#whoami")
    ).authenticate(engine)
    client = ApiClient(app.base_url, context)

    me = client.get("/api/v1/auth/me").raise_for_status().json
    assert me["email"] == USER


def test_api_client_without_session_gets_401(app):
    assert ApiClient(app.base_url).get("/api/v1/auth/me").status == 401


def test_api_client_bearer_session(engine, app):
    context = BearerTokenAuth(CREDS, token_url=f"{app.base_url}/api/v1/auth/token").authenticate(
        engine
    )
    assert ApiClient(app.base_url, context).get("/api/v1/auth/me").ok


@pytest.mark.parametrize(
    "target",
    [
        "https://other.example.test/api",
        "//other.example.test/api",
        "http://app.example.test/api",
    ],
)
def test_api_client_rejects_cross_origin_and_https_downgrade_before_network(target, monkeypatch):
    called = False

    def fake_http_json(*_args, **_kwargs):
        nonlocal called
        called = True
        return Response(200, [], "{}")

    monkeypatch.setattr("testence.api.http_json", fake_http_json)
    client = ApiClient(
        "https://app.example.test",
        AuthContext(
            headers={"Authorization": "Bearer secret"},
            cookies=[{"name": "session", "value": "secret", "domain": "app.example.test"}],
        ),
    )

    with pytest.raises(UnsafeRequestTarget):
        client.get(target)
    assert not called


def test_api_client_accepts_equivalent_same_origin(monkeypatch):
    captured = {}

    def fake_http_json(method, url, **kwargs):
        captured.update(method=method, url=url, **kwargs)
        return Response(200, [], "{}")

    monkeypatch.setattr("testence.api.http_json", fake_http_json)
    client = ApiClient(
        "http://example.test",
        AuthContext(headers={"Authorization": "Bearer secret"}),
    )

    client.get("HTTP://EXAMPLE.TEST:80/api")
    assert captured["url"] == "HTTP://EXAMPLE.TEST:80/api"
    assert captured["headers"]["Authorization"] == "Bearer secret"


def test_api_client_sends_auth_to_an_explicitly_allowed_api_origin(monkeypatch):
    captured = {}

    def fake_http_json(method, url, **kwargs):
        captured.update(method=method, url=url, **kwargs)
        return Response(200, [], "{}")

    monkeypatch.setattr("testence.api.http_json", fake_http_json)
    client = ApiClient(
        "https://app.example.test",
        AuthContext(headers={"Authorization": "Bearer secret"}),
        allowed_origins=["https://api.example.test"],
    )

    client.get("https://api.example.test/v1/items")
    assert captured["headers"]["Authorization"] == "Bearer secret"


def test_api_client_filters_browser_cookies_for_the_request_url(monkeypatch):
    captured = {}

    def fake_http_json(method, url, **kwargs):
        captured.update(method=method, url=url, **kwargs)
        return Response(200, [], "{}")

    monkeypatch.setattr("testence.api.http_json", fake_http_json)
    context = AuthContext(
        cookies=[
            {"name": "host", "value": "1", "domain": "api.example.test", "path": "/"},
            {"name": "parent", "value": "2", "domain": ".example.test", "path": "/api"},
            {"name": "wrong_path", "value": "3", "domain": ".example.test", "path": "/admin"},
            {"name": "wrong_host", "value": "4", "domain": "other.example", "path": "/"},
            {
                "name": "secure",
                "value": "5",
                "domain": "api.example.test",
                "path": "/",
                "secure": True,
            },
            {
                "name": "expired",
                "value": "6",
                "domain": "api.example.test",
                "path": "/",
                "expires": 1,
            },
        ]
    )

    ApiClient("http://api.example.test", context).get("/api/items")
    assert captured["headers"]["Cookie"] == "parent=2; host=1"


def test_http_json_refuses_cross_origin_redirect_before_forwarding_credentials():
    received: list[dict[str, str]] = []

    class Sink(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):  # noqa: N802
            received.append(dict(self.headers.items()))
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

    sink = ThreadingHTTPServer(("127.0.0.1", 0), Sink)
    sink_thread = threading.Thread(target=sink.serve_forever, daemon=True)
    sink_thread.start()
    sink_url = f"http://127.0.0.1:{sink.server_address[1]}/collect"

    class Source(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):  # noqa: N802
            self.send_response(302)
            self.send_header("Location", sink_url)
            self.send_header("Content-Length", "0")
            self.end_headers()

    source = ThreadingHTTPServer(("127.0.0.1", 0), Source)
    source_thread = threading.Thread(target=source.serve_forever, daemon=True)
    source_thread.start()
    source_url = f"http://127.0.0.1:{source.server_address[1]}/redirect"

    try:
        with pytest.raises(UnsafeRequestTarget, match="cross-origin redirect"):
            http_json(
                "GET",
                source_url,
                headers={"Authorization": "Bearer canary", "Cookie": "session=canary"},
            )
        assert received == []
    finally:
        source.shutdown()
        source.server_close()
        sink.shutdown()
        sink.server_close()


class _CookieEngine:
    def __init__(self):
        self.added = []

    def add_cookies(self, cookies):
        self.added.extend(cookies)


class _CountingSessionAuth:
    scheme = "api-session"

    def __init__(self):
        self.calls = 0

    def authenticate(self, engine):
        self.calls += 1
        cookies = [
            {
                "name": "session",
                "value": "cache-canary",
                "domain": "app.example.test",
                "path": "/",
                "secure": True,
            }
        ]
        engine.add_cookies(cookies)
        return AuthContext(cookies=cookies, scheme=self.scheme)


def _identity_response(role="admin", status=200):
    body = f'{{"email":"{USER}","role":"{role}"}}' if status == 200 else "{}"
    return Response(status, [], body)


def _cached_auth(tmp_path, inner, **kwargs):
    return CachedSessionAuth(
        inner,
        base_url="https://app.example.test",
        probe_path="/api/v1/auth/me",
        cache_file=tmp_path / "session.json",
        cache_ttl_s=60,
        scope={
            "project": "testence",
            "origin": "https://app.example.test",
            "account": "hashed-account",
            "role": "admin",
            "strategy": "api-session",
            "environment": "test",
        },
        expected_identity=USER,
        expected_role="admin",
        **kwargs,
    )


def test_session_cache_requires_fresh_matching_identity_and_hides_account(tmp_path, monkeypatch):
    monkeypatch.setattr("testence.api.http_json", lambda *_args, **_kwargs: _identity_response())
    inner = _CountingSessionAuth()
    auth = _cached_auth(tmp_path, inner)

    auth.authenticate(_CookieEngine())
    cached = auth.authenticate(_CookieEngine())

    assert inner.calls == 1
    assert cached.scheme == "api-session+cached"
    cache_text = (tmp_path / "session.json").read_text(encoding="utf-8")
    assert USER not in cache_text and PASSWORD not in cache_text


def test_expired_or_logged_out_session_cache_reauthenticates(tmp_path, monkeypatch):
    responses = iter([_identity_response(), _identity_response(status=401), _identity_response()])
    monkeypatch.setattr("testence.api.http_json", lambda *_args, **_kwargs: next(responses))
    inner = _CountingSessionAuth()
    auth = _cached_auth(tmp_path, inner)

    auth.authenticate(_CookieEngine())
    auth.authenticate(_CookieEngine())
    assert inner.calls == 2

    document = json.loads((tmp_path / "session.json").read_text(encoding="utf-8"))
    document["created_at"] = 1
    (tmp_path / "session.json").write_text(json.dumps(document), encoding="utf-8")
    monkeypatch.setattr("testence.api.http_json", lambda *_args, **_kwargs: _identity_response())
    auth.authenticate(_CookieEngine())
    assert inner.calls == 3


def test_session_cache_never_reuses_or_accepts_another_role(tmp_path, monkeypatch):
    responses = iter(
        [_identity_response(), _identity_response("viewer"), _identity_response("viewer")]
    )
    monkeypatch.setattr("testence.api.http_json", lambda *_args, **_kwargs: next(responses))
    inner = _CountingSessionAuth()
    auth = _cached_auth(tmp_path, inner)

    auth.authenticate(_CookieEngine())
    with pytest.raises(RuntimeError, match="role 'viewer', expected 'admin'"):
        auth.authenticate(_CookieEngine())
    assert inner.calls == 2


def test_legacy_or_malformed_session_cache_is_a_miss(tmp_path, monkeypatch):
    (tmp_path / "session.json").write_text('[{"name":"old"}]', encoding="utf-8")
    monkeypatch.setattr("testence.api.http_json", lambda *_args, **_kwargs: _identity_response())
    inner = _CountingSessionAuth()

    _cached_auth(tmp_path, inner).authenticate(_CookieEngine())
    assert inner.calls == 1


def test_http_json_treats_4xx_as_data(app):
    response = http_json(
        "POST", f"{app.base_url}/api/v1/auth/login", body={"email": USER, "password": "nope"}
    )
    assert response.status == 401 and not response.ok
    assert response.json["detail"] == "invalid credentials"


def test_assert_absent_checks_for_404(engine, app):
    context = BasicAuth(CREDS).authenticate(engine)
    client = ApiClient(app.base_url, context)
    client.assert_absent("/api/v1/nothing-here")
    with pytest.raises(AssertionError, match="404"):
        client.assert_absent("/api/v1/widgets/42")


def test_auth_context_describe_hides_values(engine, app):
    context = BearerTokenAuth(CREDS, token_url=f"{app.base_url}/api/v1/auth/token").authenticate(
        engine
    )
    described = context.describe()
    assert described["headers"] == ["Authorization"]
    assert "Bearer" not in str(described)


def test_get_list_rejects_a_non_collection(engine, app):
    """A 404 body is an object, so len() on it looks like one item — the exact
    mistake this helper exists to prevent."""
    context = BasicAuth(CREDS).authenticate(engine)
    client = ApiClient(app.base_url, context)
    with pytest.raises(AssertionError, match="expected a collection"):
        client.get_list("/api/v1/nothing-here")
