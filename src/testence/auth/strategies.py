"""Login strategies. All produce the same :class:`AuthContext`, so everything
downstream (API oracles, seeding, evidence) is scheme-agnostic.

Which to pick:

- :class:`FormLoginAuth` — **the default.** Drives the real login form in the
  browser, then captures cookies for API reuse. Slowest by a second or two, and
  worth it: it exercises the login screen every run (a broken login form is a
  product bug that a token-injecting shortcut hides), and it works no matter how
  the app stores its session, because the app stores it.
- :class:`ApiSessionAuth` — POST to the login endpoint, inject the session cookie
  into the browser. Use when login-form coverage lives in its own test and every
  other case should skip the round-trip.
- :class:`BearerTokenAuth` — token endpoint → ``Authorization: Bearer`` header,
  optionally mirrored into ``localStorage``/``sessionStorage`` for SPAs that read
  it from there. Covers JWT (from a client's view a JWT *is* a bearer token).
- :class:`BasicAuth` — HTTP Basic, for APIs that accept it (Swagger-style access).
- :class:`AttachedSessionAuth` — no credentials at all: reuse the session of a
  Chrome the developer already logged into (pairs with attach mode, ADR-0008).
"""

from __future__ import annotations

import base64
import json
from typing import Any, Callable

from testence.engine import Engine, Target

from .base import AuthContext, Credentials

_DEFAULT_SUCCESS_TIMEOUT_MS = 15_000

#: Scheme names accepted in configuration (aliases included).
_KNOWN_SCHEMES = frozenset(
    {"", "none", "form", "api-session", "session", "bearer", "jwt", "token",
     "basic", "attached"}
)


class FormLoginAuth:
    """Log in through the UI, then capture the session for API clients."""

    scheme = "form"

    def __init__(
        self,
        credentials: Credentials,
        *,
        login_path: str = "/login",
        username_target: Target | None = None,
        password_target: Target | None = None,
        submit_target: Target | None = None,
        success_url_contains: str | None = None,
        success_target: Target | None = None,
        timeout_ms: int = _DEFAULT_SUCCESS_TIMEOUT_MS,
    ) -> None:
        self.credentials = credentials
        self.login_path = login_path
        # Defaults follow the accessibility of a conventional login form; projects
        # override with their own addressing when the app is less conventional.
        self.username_target = username_target or Target("css", "input[type=email], input[name=email], input[name=username]")
        self.password_target = password_target or Target("css", "input[type=password]")
        self.submit_target = submit_target or Target("css", "button[type=submit], input[type=submit]")
        self.success_url_contains = success_url_contains
        self.success_target = success_target
        self.timeout_ms = timeout_ms

    def authenticate(self, engine: Engine) -> AuthContext:
        engine.goto(self.login_path)
        engine.fill(self.username_target, self.credentials.username)
        engine.fill(self.password_target, self.credentials.password)
        engine.click(self.submit_target)

        if self.success_target is not None:
            engine.expect_visible(self.success_target, timeout_ms=self.timeout_ms)
        elif self.success_url_contains:
            engine.wait_for_url_contains(self.success_url_contains, timeout_ms=self.timeout_ms)
        else:
            # No explicit success signal: settle for the login form going away, so a
            # failed login surfaces here instead of as a confusing failure later.
            engine.wait_while_visible(self.password_target, timeout_ms=self.timeout_ms)

        return AuthContext(
            cookies=engine.cookies(),
            storage=engine.storage_snapshot(),
            scheme=self.scheme,
        )


class ApiSessionAuth:
    """POST credentials to the API, put the resulting cookie in the browser."""

    scheme = "api-session"

    def __init__(
        self,
        credentials: Credentials,
        *,
        login_url: str,
        payload: Callable[[Credentials], dict[str, Any]] | None = None,
        cookie_domain: str | None = None,
        verify_tls: bool = True,
        ca_bundle: str = "",
    ) -> None:
        self.credentials = credentials
        self.login_url = login_url
        self.payload = payload or (lambda c: {"email": c.username, "password": c.password})
        self.cookie_domain = cookie_domain
        self.verify_tls = verify_tls
        self.ca_bundle = ca_bundle

    def authenticate(self, engine: Engine) -> AuthContext:
        from testence.api import http_json

        response = http_json("POST", self.login_url, body=self.payload(self.credentials),
                             verify_tls=self.verify_tls, ca_bundle=self.ca_bundle)
        cookies = [
            {
                "name": name,
                "value": value,
                "domain": self.cookie_domain or _host_of(self.login_url),
                "path": "/",
            }
            for name, value in response.cookies.items()
        ]
        if not cookies:
            raise RuntimeError(
                f"login at {self.login_url} returned {response.status} and set no cookie; "
                "if this API returns a token instead, use BearerTokenAuth"
            )
        engine.add_cookies(cookies)
        return AuthContext(
            cookies=cookies,
            user=response.json if isinstance(response.json, dict) else None,
            scheme=self.scheme,
        )


class BearerTokenAuth:
    """Token endpoint → Authorization header (+ optional storage mirror). JWT-ready."""

    scheme = "bearer"

    def __init__(
        self,
        credentials: Credentials,
        *,
        token_url: str,
        payload: Callable[[Credentials], dict[str, Any]] | None = None,
        token_field: str = "access_token",
        header_name: str = "Authorization",
        header_format: str = "Bearer {token}",
        storage_key: str | None = None,
        verify_tls: bool = True,
        ca_bundle: str = "",
    ) -> None:
        self.credentials = credentials
        self.token_url = token_url
        self.payload = payload or (lambda c: {"username": c.username, "password": c.password})
        self.token_field = token_field
        self.header_name = header_name
        self.header_format = header_format
        self.storage_key = storage_key
        self.verify_tls = verify_tls
        self.ca_bundle = ca_bundle

    def authenticate(self, engine: Engine) -> AuthContext:
        from testence.api import http_json

        response = http_json("POST", self.token_url, body=self.payload(self.credentials),
                             verify_tls=self.verify_tls, ca_bundle=self.ca_bundle)
        document = response.json if isinstance(response.json, dict) else {}
        token = document.get(self.token_field)
        if not token:
            raise RuntimeError(
                f"token endpoint {self.token_url} returned {response.status} without "
                f"field {self.token_field!r}; available: {sorted(document)}"
            )
        headers = {self.header_name: self.header_format.format(token=token)}
        engine.set_extra_http_headers(headers)
        storage: dict[str, str] = {}
        if self.storage_key:
            engine.set_storage_item(self.storage_key, str(token))
            storage[self.storage_key] = str(token)
        return AuthContext(headers=headers, storage=storage, scheme=self.scheme)


class BasicAuth:
    """HTTP Basic — for APIs that accept it alongside session auth."""

    scheme = "basic"

    def __init__(self, credentials: Credentials) -> None:
        self.credentials = credentials

    def authenticate(self, engine: Engine) -> AuthContext:
        raw = f"{self.credentials.username}:{self.credentials.password}".encode()
        headers = {"Authorization": "Basic " + base64.b64encode(raw).decode()}
        engine.set_extra_http_headers(headers)
        return AuthContext(headers=headers, scheme=self.scheme)


class AttachedSessionAuth:
    """Reuse whatever session the attached browser already has. No credentials.

    If the attached browser's session expired,
    tests fail at the first protected page. ``require_cookie`` turns that into an
    explicit, readable error instead of a mystery timeout.
    """

    scheme = "attached"

    def __init__(self, require_cookie: str | None = None) -> None:
        self.require_cookie = require_cookie

    def authenticate(self, engine: Engine) -> AuthContext:
        cookies = engine.cookies()
        if self.require_cookie and not any(c["name"] == self.require_cookie for c in cookies):
            raise RuntimeError(
                f"attached browser has no {self.require_cookie!r} cookie — "
                "log in in that browser window, or switch to another auth scheme"
            )
        return AuthContext(cookies=cookies, storage=engine.storage_snapshot(),
                           scheme=self.scheme)


class CachedSessionAuth:
    """Skip the login when the previous run's session is still valid.

    Wraps a credential strategy and reuses its cookies when they are still valid.
    Cached cookies are validated
    against a cheap probe endpoint (one HTTP GET, no browser involved); on a miss
    the wrapped strategy logs in for real and the fresh cookies are saved.

    The cache file holds a session cookie — the same secret the browser profile
    holds — so it lives under ``runs/`` (git-ignored) and is keyed by host.
    Delete it to force a fresh login. Enabled by configuring
    ``session_probe_path`` in the profile: no probe, no way to validate, no cache.
    """

    def __init__(
        self,
        inner: Any,
        *,
        base_url: str,
        probe_path: str,
        cache_file: Any,
        verify_tls: bool = True,
        ca_bundle: str = "",
    ) -> None:
        self.inner = inner
        self.base_url = base_url.rstrip("/")
        self.probe_path = probe_path
        self.cache_file = cache_file
        self.verify_tls = verify_tls
        self.ca_bundle = ca_bundle

    @property
    def scheme(self) -> str:
        return self.inner.scheme

    def authenticate(self, engine: Engine) -> AuthContext:
        cookies = self._load()
        if cookies and self._still_valid(cookies):
            engine.add_cookies(cookies)
            return AuthContext(cookies=cookies, scheme=f"{self.inner.scheme}+cached")
        context = self.inner.authenticate(engine)
        self._save(context.cookies)
        return context

    def _still_valid(self, cookies: list[dict[str, Any]]) -> bool:
        from testence.api import http_json

        header = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
        try:
            response = http_json(
                "GET", self.base_url + self.probe_path,
                headers={"Cookie": header},
                verify_tls=self.verify_tls, ca_bundle=self.ca_bundle,
            )
        except Exception:
            return False
        return 200 <= response.status < 300

    def _load(self) -> list[dict[str, Any]]:
        try:
            return json.loads(self.cache_file.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save(self, cookies: list[dict[str, Any]]) -> None:
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            self.cache_file.write_text(json.dumps(cookies), encoding="utf-8")
        except Exception:
            pass  # a cache that cannot be written is a slow run, not a failure


class NoAuth:
    scheme = "none"

    def authenticate(self, engine: Engine) -> AuthContext:  # noqa: ARG002
        return AuthContext(scheme=self.scheme)


def _host_of(url: str) -> str:
    from urllib.parse import urlparse

    return urlparse(url).hostname or "localhost"


def from_settings(settings: Any, engine_base_url: str = "") -> Any:
    """Build the adapter named by ``settings.auth``.

    Keeps projects declarative: switching an environment from form login to attach mode is
    a config edit, not a code edit.
    """
    scheme = (settings.auth or "none").lower()
    base = (engine_base_url or settings.base_url).rstrip("/")
    if scheme not in _KNOWN_SCHEMES:
        # Validate before asking for credentials, so a typo in config reports the
        # typo rather than a misleading "no credentials" error.
        raise ValueError(
            f"unknown auth scheme {scheme!r}; known: {', '.join(sorted(_KNOWN_SCHEMES))}"
        )
    if scheme in ("none", ""):
        return NoAuth()
    if scheme == "attached":
        return AttachedSessionAuth(require_cookie=settings.extra.get("session_cookie"))

    credentials = settings.credentials()
    tls = {"verify_tls": getattr(settings, "verify_tls", True),
           "ca_bundle": getattr(settings, "ca_bundle", "")}
    adapter: Any
    if scheme == "form":
        adapter = FormLoginAuth(
            credentials,
            login_path=settings.login_path,
            success_url_contains=settings.extra.get("success_url_contains"),
            timeout_ms=settings.timeout_ms,
        )
    elif scheme in ("api-session", "session"):
        adapter = ApiSessionAuth(
            credentials,
            login_url=base + (settings.api_login_path or "/api/v1/auth/login"),
            **tls,
        )
    elif scheme in ("bearer", "jwt", "token"):
        adapter = BearerTokenAuth(
            credentials,
            token_url=base + (settings.api_login_path or "/api/v1/auth/token"),
            token_field=settings.extra.get("token_field", "access_token"),
            storage_key=settings.extra.get("token_storage_key"),
            **tls,
        )
    else:
        adapter = BasicAuth(credentials)

    probe_path = settings.extra.get("session_probe_path")
    if probe_path and scheme in ("form", "api-session", "session"):
        from pathlib import Path
        from urllib.parse import urlparse

        host = urlparse(base).hostname or "default"
        adapter = CachedSessionAuth(
            adapter,
            base_url=base,
            probe_path=probe_path,
            cache_file=Path(settings.runs_root) / f".session-{host}.json",
            **tls,
        )
    return adapter


def parse_set_cookie(headers: list[tuple[str, str]]) -> dict[str, str]:
    """Extract cookie name/value pairs from Set-Cookie headers."""
    cookies: dict[str, str] = {}
    for name, value in headers:
        if name.lower() != "set-cookie":
            continue
        pair = value.split(";", 1)[0]
        if "=" in pair:
            key, _, val = pair.partition("=")
            cookies[key.strip()] = val.strip()
    return cookies


__all__ = [
    "FormLoginAuth",
    "ApiSessionAuth",
    "BearerTokenAuth",
    "BasicAuth",
    "AttachedSessionAuth",
    "CachedSessionAuth",
    "NoAuth",
    "from_settings",
    "parse_set_cookie",
    "json",
]
