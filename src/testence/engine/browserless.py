"""The session of a test that talks to the API only.

A test that asks for ``testence_api`` and not for ``ex`` used to start a browser
context and log in through it only to read the session back out. For the schemes that
log in over HTTP (``api-session``, ``bearer``, ``basic``) this stands in for the
engine: it keeps what a strategy would have put into a browser, records the test's API
calls as its wait ledger, and answers the few questions a failure pack asks of an
engine. Anything that needs a page fails with a message naming the fix.
"""

from __future__ import annotations

from typing import Any

#: Auth schemes that log in without a browser.
HTTP_SCHEMES = frozenset({"", "none", "api-session", "session", "bearer", "jwt", "token", "basic"})


class BrowserRequired(AttributeError):
    """A browser operation was asked of a test that has no browser.

    An ``AttributeError``, so ``getattr(session, name, default)`` keeps its meaning
    for evidence code that probes an engine for optional features.
    """


class BrowserlessSession:
    """Cookies, headers and storage a login produced, kept without a browser."""

    capture_screenshots = False
    capture_network_bodies = False

    def __init__(self) -> None:
        self._cookies: list[dict[str, Any]] = []
        self._headers: dict[str, str] = {}
        self._storage: dict[str, str] = {}
        self._session_storage: dict[str, str] = {}
        self._ledger: list[dict[str, Any]] = []
        self._testence_state: dict[str, Any] = {"any_failed": False, "mode": "browserless"}

    # -- lifecycle ------------------------------------------------------------
    def start(self) -> None:
        return None

    def stop(self, *, keep_browser: bool = False) -> None:  # noqa: ARG002
        return None

    def capabilities(self) -> frozenset[str]:
        return frozenset()

    def reset_taps(self) -> None:
        self._ledger.clear()

    # -- what a login leaves behind ---------------------------------------------
    def add_cookies(self, cookies: list[dict[str, Any]]) -> None:
        self._cookies.extend(dict(cookie) for cookie in cookies)

    def cookies(self) -> list[dict[str, Any]]:
        return [dict(cookie) for cookie in self._cookies]

    def set_extra_http_headers(self, headers: dict[str, str]) -> None:
        self._headers.update(headers)

    def extra_http_headers(self) -> dict[str, str]:
        return dict(self._headers)

    def set_storage_item(self, key: str, value: str, *, session: bool = False) -> None:
        (self._session_storage if session else self._storage)[key] = value

    def storage_snapshot(self) -> dict[str, str]:
        return dict(self._storage)

    def storage_item(self, key: str, *, session: bool = False) -> str | None:
        return (self._session_storage if session else self._storage).get(key)

    def storage_keys(self, *, session: bool = False) -> list[str]:
        return sorted(self._session_storage if session else self._storage)

    # -- evidence -----------------------------------------------------------------
    def record_wait(self, op: str, detail: str, ms: float, ok: bool) -> None:
        self._ledger.append({"op": op, "detail": detail, "ms": round(ms, 1), "ok": ok})

    def wait_ledger(self) -> list[dict[str, Any]]:
        return list(self._ledger)

    def settle(self, timeout_ms: int = 1_500) -> bool:  # noqa: ARG002
        return True

    def aria_snapshot(self) -> str:
        return "<no browser: this test used the API only>"

    def network_log(self) -> list[Any]:
        return []

    def console_log(self) -> list[dict[str, Any]]:
        return []

    def current_url(self) -> str:
        return ""

    def browser_manifest(self) -> dict[str, Any]:
        return {
            "mode": "browserless",
            "page_url": None,
            "note": "API-only test: no browser was started",
        }

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        raise BrowserRequired(
            f"{name}() needs a browser, and this test has none: it asked only for "
            "testence_api. Request `ex` (or `testence_engine`) in the test signature"
        )
