"""More than one user in a test: ``testence_actor("viewer")``.

Permissions, sharing and "another user sees my change" cannot be tested with one
session. Each role declared under ``users`` in ``testence.json`` gets its own session:
its own credentials, its own ``AuthContext`` and ``ApiClient`` and, on demand, its own
browser, isolated from the test's main one.

    {"auth": "form", "users": {"admin": {"user_var": "ADMIN_USER", "password_var":
     "ADMIN_PASSWORD"}, "viewer": {"user_var": "VIEWER_USER", "password_var": "VIEWER_PASSWORD"}}}

Schemes that need no page (``api-session``, ``bearer``, ``basic``) log an actor in
without a browser; ``.ex`` starts one and hands it the session when it is first used.
A form login needs the page, so its actor has a browser from the start. The second
session is a context of the test's browser: Playwright's sync API allows one driver per
thread, and separate contexts share nothing (cookies, storage, network).
"""

from __future__ import annotations

import dataclasses
import re
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from testence.auth import AuthContext, from_settings
from testence.auth.strategies import api_headers_from_storage

if TYPE_CHECKING:
    from testence.api import ApiClient
    from testence.config import Settings
    from testence.dsl import Actions
    from testence.engine import Engine

_ROLE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}")
_SPEC_KEYS = frozenset({"user_var", "password_var"})
#: Schemes whose login is an HTTP exchange; the session can be built without a page.
_PAGELESS = frozenset({"api-session", "session", "bearer", "jwt", "token", "basic"})


class ActorError(RuntimeError):
    """A role that is not declared, or cannot be logged in as."""


def actor_specs(settings: Settings) -> dict[str, dict[str, str]]:
    """The validated ``users`` table: role -> {user_var, password_var}."""
    raw = settings.extra.get("users") or {}
    if not isinstance(raw, dict):
        raise ValueError("users must be an object of role -> credentials")
    specs: dict[str, dict[str, str]] = {}
    for role, spec in raw.items():
        if not isinstance(role, str) or not _ROLE.fullmatch(role):
            raise ValueError(f"user role {role!r} must be a short name of letters, digits, _ or -")
        if not isinstance(spec, dict):
            raise ValueError(f"users.{role} must be an object with user_var and password_var")
        unknown = sorted(set(spec) - _SPEC_KEYS)
        if unknown:
            raise ValueError(f"users.{role}: unknown field(s) {', '.join(unknown)}")
        missing = sorted(key for key in _SPEC_KEYS if not str(spec.get(key) or "").strip())
        if missing:
            raise ValueError(f"users.{role}: set {' and '.join(missing)}")
        specs[role] = {key: str(spec[key]) for key in _SPEC_KEYS}
    return specs


class _Sink:
    """Stands in for the browser while a page-less scheme logs in.

    The strategies hand cookies, headers and storage to the engine they are given;
    this keeps them, so the same values can be replayed into a real browser later.
    """

    def __init__(self, scheme: str) -> None:
        self._scheme = scheme
        self._cookies: list[dict[str, Any]] = []
        self.headers: dict[str, str] = {}
        self.storage: dict[str, str] = {}

    def add_cookies(self, cookies: list[dict[str, Any]]) -> None:
        self._cookies.extend(cookies)

    def cookies(self) -> list[dict[str, Any]]:
        return list(self._cookies)

    def set_extra_http_headers(self, headers: dict[str, str]) -> None:
        self.headers.update(headers)

    def set_storage_item(self, key: str, value: str) -> None:
        self.storage[key] = value

    def storage_snapshot(self) -> dict[str, str]:
        return dict(self.storage)

    def __getattr__(self, name: str) -> Any:
        raise ActorError(
            f"auth {self._scheme!r} needs a browser page ({name}); it is not available "
            "for a page-less actor session"
        )


class Actor:
    """One role's session: ``auth``, ``api`` and, on demand, ``engine`` and ``ex``."""

    def __init__(
        self,
        role: str,
        settings: Settings,
        auth: AuthContext,
        engine: Engine | None,
        *,
        open_browser: Callable[[], Engine],
        make_actions: Callable[[Engine], Actions],
    ) -> None:
        from testence.api import ApiClient

        self.role = role
        self.settings = settings
        self.auth = auth
        self.api: ApiClient = ApiClient.from_settings(settings, auth)
        self._engine = engine
        self._actions: Actions | None = None
        self._open_browser = open_browser
        self._make_actions = make_actions

    @property
    def engine(self) -> Engine:
        """This role's own browser, started on first use and logged in as the role."""
        if self._engine is None:
            engine = self._open_browser()
            if self.auth.cookies:
                engine.add_cookies(self.auth.cookies)
            if self.auth.headers:
                engine.set_extra_http_headers(self.auth.headers)
            for key, value in self.auth.storage.items():
                engine.set_storage_item(key, value)
            self._engine = engine
        return self._engine

    @property
    def ex(self) -> Actions:
        """The DSL on this role's browser; its steps are recorded in the running test."""
        if self._actions is None:
            self._actions = self._make_actions(self.engine)
        return self._actions

    def close(self) -> None:
        engine, self._engine = self._engine, None
        if engine is not None:
            engine.stop()


class Actors:
    """The ``testence_actor`` fixture: ``actors("viewer")``, one session per role and test."""

    def __init__(
        self,
        settings: Settings,
        *,
        spawn_browser: Callable[[], Engine],
        make_actions: Callable[[Engine], Actions],
        remember: Callable[[str], None],
        note: Callable[..., None],
    ) -> None:
        self._settings = settings
        self._specs = actor_specs(settings)
        self._spawn_browser = spawn_browser
        self._make_actions = make_actions
        self._remember = remember
        self._note = note
        self._open: dict[str, Actor] = {}

    @property
    def roles(self) -> list[str]:
        return sorted(self._specs)

    def __call__(self, role: str) -> Actor:
        if role in self._open:
            return self._open[role]
        if role not in self._specs:
            declared = ", ".join(self.roles) or "none"
            raise ActorError(
                f"no user {role!r} in testence.json (declared: {declared}); add "
                f'"users": {{"{role}": {{"user_var": "...", "password_var": "..."}}}}'
            )
        actor = self._login(role)
        self._open[role] = actor
        return actor

    def _login(self, role: str) -> Actor:
        spec = self._specs[role]
        settings = dataclasses.replace(
            self._settings, user_var=spec["user_var"], password_var=spec["password_var"]
        )
        scheme = (settings.auth or "none").lower()
        if scheme in ("none", "", "attached"):
            raise ActorError(
                f"auth is {scheme!r}: there is no login to repeat as {role!r}; "
                "set auth to form, api-session, bearer or basic"
            )
        adapter = from_settings(settings)
        started = time.perf_counter()
        engine: Engine | None = None
        sink: _Sink | None = None
        if scheme in _PAGELESS:
            sink = _Sink(scheme)
            context = adapter.authenticate(sink)  # type: ignore[arg-type]
        else:
            engine = self._start_browser()
            try:
                context = adapter.authenticate(engine)
                spec_bridge = settings.extra.get("api_auth_from_storage")
                if spec_bridge:
                    context.headers.update(
                        api_headers_from_storage(
                            spec_bridge, engine, timeout_ms=min(settings.timeout_ms, 10_000)
                        )
                    )
            except BaseException:
                engine.stop()
                raise
        for value in context.headers.values():
            self._remember(value)
            self._remember(value.rsplit(" ", 1)[-1])
        self._note(
            text="authenticated",
            actor=role,
            auth=context.describe(),
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
        )
        return Actor(
            role,
            settings,
            context,
            engine,
            open_browser=self._start_browser,
            make_actions=self._make_actions,
        )

    def _start_browser(self) -> Engine:
        return self._spawn_browser()

    def close(self) -> None:
        for actor in self._open.values():
            actor.close()
        self._open.clear()
