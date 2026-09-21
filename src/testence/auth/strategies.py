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
import hashlib
import json
import math
import os
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from testence.engine import Engine, Target

from .base import AuthContext, Credentials

_DEFAULT_SUCCESS_TIMEOUT_MS = 15_000

#: Scheme names accepted in configuration (aliases included).
_KNOWN_SCHEMES = frozenset(
    {"", "none", "form", "api-session", "session", "bearer", "jwt", "token", "basic", "attached"}
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
        self.username_target = username_target or Target(
            "css", "input[type=email], input[name=email], input[name=username]"
        )
        self.password_target = password_target or Target("css", "input[type=password]")
        # `form button:not([type])` because a button inside a form submits it by
        # default: the HTML spec says so, component libraries rely on it, and without
        # this the first run against an ordinary `<button>Log in</button>` failed with
        # a bare element-not-found timeout.
        self.submit_target = submit_target or Target(
            "css", "button[type=submit], input[type=submit], form button:not([type])"
        )
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

        response = http_json(
            "POST",
            self.login_url,
            body=self.payload(self.credentials),
            verify_tls=self.verify_tls,
            ca_bundle=self.ca_bundle,
        )
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

        response = http_json(
            "POST",
            self.token_url,
            body=self.payload(self.credentials),
            verify_tls=self.verify_tls,
            ca_bundle=self.ca_bundle,
        )
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
        return AuthContext(cookies=cookies, storage=engine.storage_snapshot(), scheme=self.scheme)


class CachedSessionAuth:
    """Skip the login when the previous run's session is still valid.

    Wraps a credential strategy and reuses its cookies when they are still valid.
    Cached cookies are validated against a cheap identity endpoint (one HTTP GET,
    no browser involved); on a miss the wrapped strategy logs in for real. Cache
    records expire, carry their project/origin/account/role scope and are written
    with owner-only permissions where the operating system supports that mode.

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
        cache_ttl_s: int = 3600,
        scope: dict[str, str] | None = None,
        identity_field: str = "email",
        role_field: str = "role",
        expected_identity: str = "",
        expected_role: str = "",
        verify_tls: bool = True,
        ca_bundle: str = "",
    ) -> None:
        if cache_ttl_s <= 0:
            raise ValueError("session cache TTL must be greater than zero")
        self.inner = inner
        self.base_url = base_url.rstrip("/")
        self.probe_path = probe_path
        self.cache_file = Path(cache_file)
        self.cache_ttl_s = cache_ttl_s
        self.scope = dict(scope or {})
        self.identity_field = identity_field
        self.role_field = role_field
        self.expected_identity_digest = _identity_digest(expected_identity)
        self.expected_role = expected_role
        self.verify_tls = verify_tls
        self.ca_bundle = ca_bundle

    @property
    def scheme(self) -> str:
        return self.inner.scheme

    def authenticate(self, engine: Engine) -> AuthContext:
        cached = self._load()
        if cached and self._still_valid(cached):
            cookies = cached["cookies"]
            engine.add_cookies(cookies)
            return AuthContext(
                cookies=cookies,
                user={"identity_verified": True, "role": cached["identity"]["role"]},
                scheme=f"{self.inner.scheme}+cached",
            )
        context = self.inner.authenticate(engine)
        identity = self._probe_identity(context.cookies)
        if identity is not None:
            self._save(context.cookies, identity)
        return context

    def _still_valid(self, cached: dict[str, Any]) -> bool:
        try:
            identity = self._probe_identity(cached["cookies"])
        except RuntimeError:
            return False
        return identity is not None and identity == cached["identity"]

    def _probe_identity(self, cookies: list[dict[str, Any]]) -> dict[str, str] | None:
        from testence.api import http_json

        url = self.base_url + self.probe_path
        header = AuthContext(cookies=cookies).cookie_header(url)
        try:
            response = http_json(
                "GET",
                url,
                headers={"Cookie": header},
                verify_tls=self.verify_tls,
                ca_bundle=self.ca_bundle,
            )
        except Exception:
            return None
        if not response.ok or not isinstance(response.json, dict):
            return None
        account = _json_field(response.json, self.identity_field)
        role = _json_field(response.json, self.role_field)
        if account is None or role is None:
            return None
        account_digest = _identity_digest(str(account))
        if self.expected_identity_digest and account_digest != self.expected_identity_digest:
            raise RuntimeError(
                f"session identity probe returned another {self.identity_field}; refusing reuse"
            )
        if self.expected_role and str(role) != self.expected_role:
            raise RuntimeError(
                f"session identity probe returned role {role!r}, expected {self.expected_role!r}"
            )
        return {"account": account_digest, "role": str(role)}

    def _load(self) -> dict[str, Any] | None:
        try:
            document = json.loads(self.cache_file.read_text(encoding="utf-8"))
            if not isinstance(document, dict) or document.get("v") != 1:
                return None
            created_at = float(document["created_at"])
            if not math.isfinite(created_at):
                return None
            age = time.time() - created_at
            if age < -60 or age > self.cache_ttl_s:
                return None
            if document.get("scope") != self.scope:
                return None
            cookies = document.get("cookies")
            if not isinstance(cookies, list) or not all(
                isinstance(cookie, dict)
                and isinstance(cookie.get("name"), str)
                and isinstance(cookie.get("value"), str)
                for cookie in cookies
            ):
                return None
            identity = document.get("identity")
            if not isinstance(identity, dict) or not {"account", "role"} <= identity.keys():
                return None
            return document
        except Exception:
            return None

    def _save(self, cookies: list[dict[str, Any]], identity: dict[str, str]) -> None:
        temporary = self.cache_file.with_suffix(f"{self.cache_file.suffix}.tmp-{os.getpid()}")
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            document = {
                "v": 1,
                "created_at": time.time(),
                "scope": self.scope,
                "identity": identity,
                "cookies": cookies,
            }
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(document, stream, separators=(",", ":"))
            os.replace(temporary, self.cache_file)
            try:
                self.cache_file.chmod(0o600)
            except OSError:
                pass
        except Exception:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            pass  # a cache that cannot be written is a slow run, not a failure


class NoAuth:
    scheme = "none"

    def authenticate(self, engine: Engine) -> AuthContext:  # noqa: ARG002
        return AuthContext(scheme=self.scheme)


def _host_of(url: str) -> str:
    from urllib.parse import urlparse

    return urlparse(url).hostname or "localhost"


def _identity_digest(value: str) -> str:
    return hashlib.sha256(value.strip().casefold().encode("utf-8")).hexdigest() if value else ""


def _json_field(document: dict[str, Any], pointer: str) -> Any:
    current: Any = document
    for part in pointer.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


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
    verify_tls = bool(getattr(settings, "verify_tls", True))
    ca_bundle = str(getattr(settings, "ca_bundle", ""))
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
            verify_tls=verify_tls,
            ca_bundle=ca_bundle,
        )
    elif scheme in ("bearer", "jwt", "token"):
        adapter = BearerTokenAuth(
            credentials,
            token_url=base + (settings.api_login_path or "/api/v1/auth/token"),
            token_field=settings.extra.get("token_field", "access_token"),
            storage_key=settings.extra.get("token_storage_key"),
            verify_tls=verify_tls,
            ca_bundle=ca_bundle,
        )
    else:
        adapter = BasicAuth(credentials)

    probe_path = settings.extra.get("session_probe_path")
    if probe_path and scheme in ("form", "api-session", "session"):
        probe_path = str(probe_path)
        parsed_probe = urlsplit(probe_path)
        if not probe_path.startswith("/") or parsed_probe.scheme or parsed_probe.netloc:
            raise ValueError("session_probe_path must be a root-relative path on base_url")
        expected_role = str(settings.extra.get("session_expected_role") or "")
        scope = {
            "project": str(Path(settings.runs_root).resolve().parent),
            "origin": base,
            "account": _identity_digest(credentials.username),
            "role": expected_role,
            "strategy": scheme,
            "environment": settings.profile or "(default)",
        }
        cache_key = hashlib.sha256(
            json.dumps(scope, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]
        adapter = CachedSessionAuth(
            adapter,
            base_url=base,
            probe_path=probe_path,
            cache_file=Path(settings.runs_root) / f".session-{cache_key}.json",
            cache_ttl_s=int(settings.extra.get("session_cache_ttl_s", 3600)),
            scope=scope,
            identity_field=str(settings.extra.get("session_identity_field") or "email"),
            role_field=str(settings.extra.get("session_role_field") or "role"),
            expected_identity=credentials.username,
            expected_role=expected_role,
            verify_tls=verify_tls,
            ca_bundle=ca_bundle,
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
