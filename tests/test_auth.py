"""Every auth strategy, verified against a real browser and real HTTP.

These run on every commit: auth is the thing that breaks adoption, so it is the
thing that must not be verified by inspection.
"""

from __future__ import annotations

import pytest

from testence.api import ApiClient, http_json
from testence.auth import (
    ApiSessionAuth,
    AttachedSessionAuth,
    BasicAuth,
    BearerTokenAuth,
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
    auth = ApiSessionAuth(CREDS, login_url=f"{app.base_url}/api/v1/auth/token",
                          payload=lambda c: {"username": c.username, "password": c.password})
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
    auth = BearerTokenAuth(CREDS, token_url=f"{app.base_url}/api/v1/auth/token",
                           token_field="id_token")
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
    context = FormLoginAuth(CREDS, login_path="/login",
                            success_target=Target("css", "#whoami")).authenticate(engine)
    client = ApiClient(app.base_url, context)

    me = client.get("/api/v1/auth/me").raise_for_status().json
    assert me["email"] == USER


def test_api_client_without_session_gets_401(app):
    assert ApiClient(app.base_url).get("/api/v1/auth/me").status == 401


def test_api_client_bearer_session(engine, app):
    context = BearerTokenAuth(CREDS, token_url=f"{app.base_url}/api/v1/auth/token").authenticate(engine)
    assert ApiClient(app.base_url, context).get("/api/v1/auth/me").ok


def test_http_json_treats_4xx_as_data(app):
    response = http_json("POST", f"{app.base_url}/api/v1/auth/login",
                         body={"email": USER, "password": "nope"})
    assert response.status == 401 and not response.ok
    assert response.json["detail"] == "invalid credentials"


def test_assert_absent_checks_for_404(engine, app):
    context = BasicAuth(CREDS).authenticate(engine)
    client = ApiClient(app.base_url, context)
    client.assert_absent("/api/v1/nothing-here")
    with pytest.raises(AssertionError, match="404"):
        client.assert_absent("/api/v1/widgets/42")


def test_auth_context_describe_hides_values(engine, app):
    context = BearerTokenAuth(CREDS, token_url=f"{app.base_url}/api/v1/auth/token").authenticate(engine)
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
