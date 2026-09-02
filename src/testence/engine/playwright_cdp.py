"""Playwright-backed Engine implementation.

Two attach modes (ADR-0008):
- ``cdp_url`` given → connect_over_cdp to an already-running headed Chrome
  (developer's profile, existing session cookies, shared triage substrate).
- otherwise → launch system Chrome (``channel="chrome"``), headed by default,
  with ``--remote-debugging-port`` so triage clients can attach later.

On failure the browser is deliberately left running (``keep_browser=True``):
the page at the failure state IS evidence.
"""

from __future__ import annotations

import re
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from typing import Any

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Locator,
    Page,
    Playwright,
    sync_playwright,
)
from playwright.sync_api import expect as pw_expect

from .protocol import Engine, NetRecord, Target

_DEFAULT_TIMEOUT_MS = 10_000
_RENDER_TIMEOUT_MS = 2_000
_BODY_CAP_BYTES = 64 * 1024
_WS_FRAME_CAP_BYTES = 8 * 1024
#: Poll interval for capture-buffer waits. Playwright events are dispatched while
#: ``wait_for_timeout`` yields to its message loop, so this is not a busy Python
#: poll. It is still a floor on how late an already completed mutation is observed:
#: 50 ms was visible on fast React APIs, while 10 ms stays cheap and responsive.
_POLL_MS = 10
#: Verbs that must never be accepted as a URL fragment: see wait_for_request.
_HTTP_VERBS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})

#: Injected into every document when ``reduce_motion`` is on. CSS transitions and
#: entry animations add 150–300 ms to every modal/panel open — pure wait for a
#: deterministic runner, and a common reason "catching the modal" needs padding.
_REDUCE_MOTION_JS = """(() => {
    const inject = () => {
        const style = document.createElement('style');
        style.textContent = '*, *::before, *::after {'
            + ' animation-duration: 0s !important;'
            + ' animation-delay: 0s !important;'
            + ' transition-duration: 0s !important;'
            + ' transition-delay: 0s !important;'
            + ' scroll-behavior: auto !important; }';
        document.documentElement.appendChild(style);
    };
    if (document.documentElement) inject();
    else document.addEventListener('DOMContentLoaded', inject);
})();"""


class PlaywrightCdpEngine(Engine):
    def __init__(
        self,
        base_url: str = "",
        *,
        cdp_url: str | None = None,
        headed: bool = True,
        debug_port: int = 9222,
        api_prefix: str = "/api/",
        timeout_ms: int = _DEFAULT_TIMEOUT_MS,
        browser_channel: str = "chromium",
        ignore_https_errors: bool = False,
        reduce_motion: bool = False,
        user_data_dir: str | None = None,
        test_id_attribute: str = "",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.cdp_url = cdp_url
        self.headed = headed
        self.debug_port = debug_port
        self.api_prefix = api_prefix
        self.timeout_ms = timeout_ms
        self.browser_channel = browser_channel
        self.ignore_https_errors = ignore_https_errors
        self.reduce_motion = reduce_motion
        self.user_data_dir = user_data_dir
        #: DOM attribute that ``Target("testid", ...)`` resolves against. Apps
        #: rarely ship `data-testid`; they do ship something stable (this project's
        #: tables carry `data-key` with the row's id). Pointing the test-id
        #: selector at it buys a measured 215 ms per row click against 261-332 ms
        #: for `:has()`/xpath addressing — not because resolution is slow (1.7-3.5
        #: ms either way) but because Playwright re-evaluates the selector on every
        #: actionability retry, and a flat attribute match is the cheapest one.
        self.test_id_attribute = test_id_attribute
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._net: list[NetRecord] = []
        self._pending: dict[Any, NetRecord] = {}
        self._console: list[dict[str, Any]] = []
        self._ws: list[dict[str, Any]] = []
        #: Wait ledger: every wait/action records {op, detail, ms, ok}. This is the
        #: run's honest time budget — the answer to "where did 39 seconds go" is
        #: here, not in a profiler. Cleared per test with the other taps.
        self._waits: list[dict[str, Any]] = []
        self._launched_here = False
        # A CDP client normally borrows the launcher's default context. Closing
        # that context from pytest can discard the logged-in session the launcher
        # exists to preserve. The exceptional no-context attach creates one and
        # therefore owns it; locally launched and persistent contexts are owned too.
        self._owns_context = False
        self._extra_headers: dict[str, str] = {}

    # -- lifecycle -------------------------------------------------------

    def start(self) -> None:
        # Keep ownership correct if an embedding application deliberately reuses
        # one engine object for more than one start/stop cycle.
        self._launched_here = False
        self._owns_context = False
        playwright = sync_playwright().start()
        self._pw = playwright
        if self.test_id_attribute:
            playwright.selectors.set_test_id_attribute(self.test_id_attribute)
        if self.cdp_url:
            self._browser = playwright.chromium.connect_over_cdp(self.cdp_url)
            # The context with pages in it is the one that is logged in. Taking
            # contexts[0] blindly can hand back a pristine default context whose
            # cookie jar is empty, which surfaces as "attached browser has no
            # session cookie" while the real session sits in the next context over.
            contexts = sorted(self._browser.contexts, key=lambda c: -len(c.pages))
            if contexts:
                self._context = contexts[0]
            else:
                self._context = self._browser.new_context()
                self._owns_context = True
        elif self.user_data_dir:
            # Persistent profile. Required for the long-lived dev browser: a
            # context created with new_context() is invisible to a later
            # connect_over_cdp (which only ever sees the *default* context), so a
            # session established in one would be unreachable by the runs meant to
            # reuse it. A profile on disk is the default context, and it also
            # survives restarts of the browser itself.
            self._context = playwright.chromium.launch_persistent_context(
                self.user_data_dir,
                channel=self.browser_channel,
                headless=not self.headed,
                args=[f"--remote-debugging-port={self.debug_port}"],
                ignore_https_errors=self.ignore_https_errors,
            )
            self._browser = self._context.browser
            self._launched_here = True
            self._owns_context = True
        else:
            self._browser = playwright.chromium.launch(
                channel=self.browser_channel,
                headless=not self.headed,
                args=[f"--remote-debugging-port={self.debug_port}"],
            )
            self._launched_here = True
            self._context = self._browser.new_context(ignore_https_errors=self.ignore_https_errors)
            self._owns_context = True
        self._context.set_default_timeout(self.timeout_ms)
        if self.reduce_motion:
            # Both hints, because apps honour either: the media feature for
            # prefers-reduced-motion-aware CSS, the init script for the rest.
            self._context.add_init_script(_REDUCE_MOTION_JS)
        # Attached: reuse the tab that is already open and logged in — opening a
        # fresh one throws away the app instance the long-lived browser exists to
        # keep warm (and leaves a blank tab behind on every run).
        self._page = (
            self._context.pages[0]
            if self.cdp_url and self._context.pages
            else self._context.new_page()
        )
        if self.reduce_motion:
            self._page.emulate_media(reduced_motion="reduce")
        self._attach_taps(self._page)

    def stop(self, *, keep_browser: bool = False) -> None:
        if keep_browser:
            # Leave the crime scene intact; only detach our client if we attached.
            if self._pw and not self._launched_here:
                with suppress(Exception):
                    self._pw.stop()
            return
        if self._context and self._owns_context:
            # Ctrl+C can reach Chromium's driver before Python enters cleanup. At
            # that point close() reports a dead transport, but the desired state
            # (the owned context is gone) already holds. Continue best-effort so a
            # dev-browser shutdown never ends in a misleading stack trace.
            with suppress(Exception):
                self._context.close()
        if self._browser and self._launched_here:
            with suppress(Exception):
                self._browser.close()
        if self._pw:
            with suppress(Exception):
                self._pw.stop()

    # -- taps --------------------------------------------------------------

    def _attach_taps(self, page: Page) -> None:
        def on_request(request: Any) -> None:
            if self.api_prefix not in request.url:
                return
            body = request.post_data or None
            rec = NetRecord(
                method=request.method,
                url=request.url,
                status=None,
                started_ms=time.monotonic() * 1000,
                duration_ms=None,
                request_body=body[:_BODY_CAP_BYTES] if body else None,
            )
            self._pending[request] = rec
            self._net.append(rec)

        def on_response(response: Any) -> None:
            rec = self._pending.pop(response.request, None)
            if rec is None:
                return
            rec.duration_ms = time.monotonic() * 1000 - rec.started_ms
            # Bodies are kept for every error AND every mutation: the response to
            # a POST/PATCH the UI just made carries the entity (with its id), which
            # is what wait_for_response callers synchronize on. GET bodies stay
            # uncaptured — list responses are large and an oracle can re-ask.
            if (response.status >= 400) or rec.method != "GET":
                try:
                    rec.response_body = response.text()[:_BODY_CAP_BYTES]
                except Exception:  # noqa: BLE001 - evidence capture is best-effort
                    rec.response_body = "<body unavailable>"
            # Status LAST, deliberately: wait_for_response keys on it, so setting it
            # before the body is captured hands the caller a record whose body is
            # still empty — a race that showed up as "the create response has no id".
            rec.status = response.status

        def on_request_failed(request: Any) -> None:
            """A request that never produced a response.

            Overwhelmingly this is the application aborting its own fetch when a
            component unmounts — a panel that closes on save cancels the very
            request that saved it. The server may already have applied the change,
            so this is not an error to raise: it is the outcome being unobservable
            from here, and the record has to say so. Before this handler existed
            such a record sat at ``status=None`` forever and every
            ``wait_for_response`` on it spent its whole budget learning nothing.
            """
            rec = self._pending.pop(request, None)
            if rec is None:
                return
            rec.duration_ms = time.monotonic() * 1000 - rec.started_ms
            rec.failure = str(getattr(request, "failure", None) or "aborted")

        def on_console(msg: Any) -> None:
            if msg.type in ("error", "warning"):
                self._console.append({"level": msg.type, "text": msg.text})

        def on_websocket(ws: Any) -> None:
            def on_frame(payload: Any) -> None:
                text = payload if isinstance(payload, str) else "<binary frame>"
                self._ws.append(
                    {
                        "url": ws.url,
                        "at_ms": time.monotonic() * 1000,
                        "payload": text[:_WS_FRAME_CAP_BYTES],
                    }
                )

            ws.on("framereceived", on_frame)

        page.on("request", on_request)
        page.on("response", on_response)
        page.on("requestfailed", on_request_failed)
        page.on("console", on_console)
        page.on("websocket", on_websocket)
        page.on(
            "pageerror",
            lambda err: self._console.append({"level": "pageerror", "text": str(err)}),
        )

    @contextmanager
    def _timed(self, op: str, detail: str = "") -> Iterator[None]:
        """Record how long an action or wait took, success or not."""
        started = time.monotonic()
        ok = True
        try:
            yield
        except Exception:
            ok = False
            raise
        finally:
            self._waits.append(
                {
                    "op": op,
                    "detail": detail,
                    "ms": round((time.monotonic() - started) * 1000, 1),
                    "ok": ok,
                }
            )

    # -- targets -----------------------------------------------------------

    def _locate(self, target: Target) -> Locator:
        page = self._require_page()
        exact = target.matches_exactly()
        if target.kind == "role":
            loc = page.get_by_role(target.value, name=target.name, exact=exact)  # type: ignore[arg-type]
        elif target.kind == "label":
            loc = page.get_by_label(target.value, exact=exact)
        elif target.kind == "text":
            loc = page.get_by_text(target.value, exact=exact)
        elif target.kind == "testid":
            loc = page.get_by_test_id(target.value)
        elif target.kind == "placeholder":
            loc = page.get_by_placeholder(target.value, exact=exact)
        else:
            loc = page.locator(target.value)
        if target.nth is not None:
            loc = loc.nth(target.nth)
        return loc

    def _require_page(self) -> Page:
        if self._page is None:
            raise RuntimeError("engine not started")
        return self._page

    # -- actions -------------------------------------------------------------

    def goto(self, url: str) -> None:
        full = url if url.startswith(("http", "file:")) else f"{self.base_url}{url}"
        # "domcontentloaded", not the default "load": load waits for every
        # secondary resource (fonts, images, dev-server chunks), which on a slow
        # target can time out on assets no test cares about. Readiness is decided by
        # wait_until_rendered below, which asks the only question that matters —
        # has the app painted anything.
        with self._timed("goto", url):
            self._require_page().goto(full, wait_until="domcontentloaded")
        self.wait_until_rendered()

    def navigate(self, url: str, *, hard: bool = False) -> bool:
        """Go to an in-app route, preferring client-side routing.

        A full document load re-downloads the bundle and re-boots the application.
        This method instead pushes state and lets the app's router react, exactly as
        clicking a link in the navigation does, and falls back to a full load when
        there is no app running yet (first navigation or cross-origin navigation).

        Returns True when it navigated client-side. **Client-side navigation keeps
        component state**: a route that is already mounted does not remount, so a
        case whose subject is first-load behaviour must pass ``hard=True`` — that
        distinction is the price of the speed, and it is deliberate rather than
        hidden.
        """
        full = url if url.startswith(("http", "file:")) else f"{self.base_url}{url}"
        page = self._require_page()
        current = page.url
        same_origin = (
            not hard
            and self.base_url
            and current.startswith(self.base_url)
            and full.startswith(self.base_url)
        )
        if not same_origin:
            self.goto(url)
            return False
        path = full[len(self.base_url) :] or "/"
        with self._timed("navigate(spa)", path):
            page.evaluate(
                """(target) => {
                    history.pushState({}, '', target);
                    window.dispatchEvent(new PopStateEvent('popstate'));
                }""",
                path,
            )
        return True

    def wait_until_rendered(self, timeout_ms: int = _RENDER_TIMEOUT_MS) -> bool:
        """Wait for a single-page app to actually paint something.

        ``load`` fires when the bundle arrives, which for an SPA is before the app
        has rendered anything. Text alone is not a readiness signal: a React root
        may validly render only inputs, icons, canvas or another semantic control.
        Prefer a known SPA root when present and accept either text or meaningful
        non-text UI inside it. This remains a best-effort heuristic rather than an
        assertion; the next locator action owns its precise readiness wait.
        """
        with self._timed("wait_until_rendered"):
            try:
                self._require_page().wait_for_function(
                    """() => {
                        const body = document.body;
                        if (!body) return false;
                        const roots = [...document.querySelectorAll(
                            '#root, #app, [data-reactroot], [data-react-app]'
                        )];
                        const scopes = roots.length ? roots : [body];
                        return scopes.some(scope => {
                            if ((scope.innerText || '').trim().length) return true;
                            return !!scope.querySelector(
                                'input, textarea, select, button, a[href], img, svg,'
                                + ' canvas, video, [role], [aria-label], [contenteditable]'
                            );
                        });
                    }""",
                    timeout=timeout_ms,
                )
                return True
            except Exception:  # noqa: BLE001 - readiness probes fail closed
                return False

    def settle(self, timeout_ms: int = 1_500) -> bool:
        """Wait for network quiet. Short and optional by design: apps that poll or
        stream never go idle, so this must never be load-bearing."""
        with self._timed("settle", f"{timeout_ms}ms budget"):
            try:
                self._require_page().wait_for_load_state("networkidle", timeout=timeout_ms)
                return True
            except Exception:  # noqa: BLE001 - readiness probes fail closed
                return False

    def click(self, target: Target, *, fast: bool = False) -> None:
        """Click, waiting for the element to be actionable first.

        ``fast=True`` skips Playwright's actionability checks — visible, enabled,
        stable (two identical animation frames), receives-events (a hit test).
        Measured on this project's host-template rows: 215 ms with the checks,
        132 ms without, against a 102 ms backend floor. The checks are also the
        safety net that turns "an overlay swallowed my click" into a readable
        timeout instead of a silent no-op, so this is opt-in per call and belongs
        only where a preceding wait has already proved the element is there.
        """
        with self._timed("click(fast)" if fast else "click", target.describe()):
            self._locate(target).click(force=fast)

    def fill(self, target: Target, value: str, *, fast: bool = False) -> None:
        """Fill through Playwright so controlled inputs receive an input event.

        Directly assigning ``element.value`` is a tempting micro-optimization but
        can bypass React's value tracker and application handlers. ``force=True``
        keeps Playwright's event-correct fill path while skipping actionability
        checks for callers that already established readiness.
        """
        with self._timed("fill(fast)" if fast else "fill", target.describe()):
            self._locate(target).fill(value, force=fast)

    def select(self, target: Target, value: str) -> None:
        self._locate(target).select_option(value)

    def press(self, key: str) -> None:
        self._require_page().keyboard.press(key)

    # -- observation -----------------------------------------------------------

    def expect_text(
        self, target: Target, text: str, timeout_ms: int | None = None, *, exact: bool = True
    ) -> None:
        # Exact by default, for the reason already written into `Target`: loose
        # matching on an identity value is a silent hazard. Here it is worse than on
        # a locator, because the failure mode is a *passing* assertion — "the
        # counter shows 4" held against 48, 45 and 14 alike, and a benchmark run
        # caught it racing a transient value on its way to the right one. Pass
        # exact=False where the element genuinely carries surrounding text.
        matcher: Any = re.compile(rf"^\s*{re.escape(text)}\s*$") if exact else text
        with self._timed("expect_text", f"{target.describe()} {'==' if exact else '~'} {text!r}"):
            self._locate(target).filter(has_text=matcher).first.wait_for(
                state="visible", timeout=timeout_ms or self.timeout_ms
            )

    def expect_visible(self, target: Target, timeout_ms: int | None = None) -> None:
        with self._timed("expect_visible", target.describe()):
            self._locate(target).first.wait_for(
                state="visible", timeout=timeout_ms or self.timeout_ms
            )

    def wait_while_visible(self, target: Target, timeout_ms: int | None = None) -> None:
        with self._timed("wait_while_visible", target.describe()):
            self._locate(target).first.wait_for(
                state="hidden", timeout=timeout_ms or self.timeout_ms
            )

    def wait_for_url_contains(self, fragment: str, timeout_ms: int | None = None) -> None:
        with self._timed("wait_for_url", fragment):
            self._require_page().wait_for_url(
                lambda url: fragment in url, timeout=timeout_ms or self.timeout_ms
            )

    # -- session -------------------------------------------------------------

    def cookies(self) -> list[dict[str, Any]]:
        if self._context is None:
            return []
        return [dict(c) for c in self._context.cookies()]

    def add_cookies(self, cookies: list[dict[str, Any]]) -> None:
        if self._context is None:
            raise RuntimeError("engine not started")
        self._context.add_cookies(cookies)  # type: ignore[arg-type]

    def set_extra_http_headers(self, headers: dict[str, str]) -> None:
        if self._context is None:
            raise RuntimeError("engine not started")
        self._extra_headers.update(headers)
        self._context.set_extra_http_headers(self._extra_headers)

    def set_storage_item(self, key: str, value: str, *, session: bool = False) -> None:
        store = "sessionStorage" if session else "localStorage"
        page = self._require_page()
        script = f"([k, v]) => {store}.setItem(k, v)"
        if page.url in ("about:blank", ""):
            # Nothing loaded yet: schedule for every future document instead of
            # failing — token-based auth is normally set up before first navigation.
            page.add_init_script(f"{store}.setItem({key!r}, {value!r})")
            return
        page.evaluate(script, [key, value])

    def storage_snapshot(self) -> dict[str, str]:
        page = self._require_page()
        if page.url in ("about:blank", ""):
            return {}
        try:
            return page.evaluate("() => Object.fromEntries(Object.entries(localStorage))")
        except Exception:  # noqa: BLE001 - browser evidence is best-effort
            return {}

    def wait_for_request(
        self,
        url_contains: str,
        *,
        method: str | None = None,
        since: int = 0,
        timeout_ms: int | None = None,
    ) -> bool:
        """Poll the capture buffer, which already records every API call from the
        first moment of the test — so a request that fired before this call was
        made still counts.

        ``method`` filters on the HTTP verb, and it exists because the obvious
        call did the wrong thing silently: ``wait_for_request("POST")`` searched
        the *URL* for the literal string "POST", never matched, burned the whole
        budget, and made ``assert not sent`` pass for the wrong reason. Four call
        sites in this repo did exactly that. Passing a verb as the URL fragment is
        now a loud error rather than a quiet false negative.
        """
        if url_contains.upper() in _HTTP_VERBS:
            raise ValueError(
                f"wait_for_request({url_contains!r}) matches the URL, never the "
                f'method — call wait_for_request("/api/", method='
                f'"{url_contains.upper()}") instead'
            )
        page = self._require_page()
        wanted = method.upper() if method else None
        remaining = timeout_ms or self.timeout_ms
        with self._timed("wait_for_request", f"{method or 'ANY'} {url_contains}"):
            while True:
                for record in self._net[since:]:
                    if url_contains in record.url and (wanted is None or record.method == wanted):
                        return True
                if remaining <= 0:
                    return False
                # Matching wait_for_response: the poll interval is a floor on how
                # late an answer can arrive, and it is paid on every wait.
                step = min(_POLL_MS, remaining)
                page.wait_for_timeout(step)
                remaining -= step

    def net_mark(self) -> int:
        return len(self._net)

    def wait_for_response(
        self,
        url_contains: str,
        *,
        method: str | None = None,
        since: int = 0,
        timeout_ms: int | None = None,
    ) -> NetRecord | None:
        """Wait for a completed response — see the protocol docstring.

        Scans the same capture buffer as ``wait_for_request`` (so a response that
        landed before the call still counts), but insists on ``status`` being set:
        a request that has been *sent* is not yet an outcome.

        Stops early on a matching request the browser *aborted*: no response will
        ever arrive for it, so waiting out the budget only delays the report. The
        ledger detail records it, and the caller gets ``None`` — which for an
        aborted mutation means "the server may well have applied it, ask an
        oracle", not "nothing happened".
        """
        wanted = method.upper() if method else None
        page = self._require_page()
        remaining = timeout_ms or self.timeout_ms
        aborted: str | None = None
        with self._timed("wait_for_response", f"{method or 'ANY'} {url_contains}"):
            while True:
                for record in self._net[since:]:
                    if url_contains not in record.url:
                        continue
                    if wanted is not None and record.method != wanted:
                        continue
                    if record.status is not None:
                        return record
                    if record.failure:
                        aborted = record.failure
                if aborted or remaining <= 0:
                    break
                step = min(_POLL_MS, remaining)
                page.wait_for_timeout(step)
                remaining -= step
        if aborted:
            self._waits.append(
                {
                    "op": "wait_for_response",
                    "ok": False,
                    "ms": 0.0,
                    "detail": f"{method or 'ANY'} {url_contains} aborted: {aborted}",
                }
            )
        return None

    def ws_mark(self) -> int:
        return len(self._ws)

    def wait_for_ws(
        self, payload_contains: str, *, since: int = 0, timeout_ms: int | None = None
    ) -> dict[str, Any] | None:
        """Wait for a WebSocket frame whose payload contains the fragment.

        Live-update apps announce mutations over WS (``...Updated`` events); for a
        change made by *another* session that event is the only push signal there
        is, so a case that checks live updates synchronizes here — never on sleeps.
        """
        page = self._require_page()
        remaining = timeout_ms or self.timeout_ms
        with self._timed("wait_for_ws", payload_contains):
            while True:
                for frame in self._ws[since:]:
                    if payload_contains in frame["payload"]:
                        return frame
                if remaining <= 0:
                    return None
                step = min(_POLL_MS, remaining)
                page.wait_for_timeout(step)
                remaining -= step

    def wait_for_value(self, target: Target, timeout_ms: int | None = None) -> str:
        """Wait until an input carries a non-empty value — the form-control
        counterpart of ``wait_for_content`` (input values are not text nodes)."""
        with self._timed("wait_for_value", target.describe()):
            pw_expect(self._locate(target).first).not_to_have_value(
                "", timeout=timeout_ms or self.timeout_ms
            )
            return self._locate(target).first.input_value()

    def wait_for_predicate_js(self, expression: str, timeout_ms: int | None = None) -> bool:
        """Wait until a JS predicate holds; returns whether it did.

        For readiness conditions no locator can express ("every row matches the
        filter"). Playwright evaluates the function on rAF — event-driven at frame
        granularity, strictly better than polling from Python.
        """
        with self._timed("wait_for_predicate", expression[:80]):
            try:
                self._require_page().wait_for_function(
                    expression, timeout=timeout_ms or self.timeout_ms
                )
                return True
            except Exception:  # noqa: BLE001 - readiness probes fail closed
                return False

    def wait_for_content(
        self, target: Target, minimum: int = 1, timeout_ms: int | None = None
    ) -> int:
        locator = self._locate(target).filter(has_text=re.compile(r"\S"))
        locator.nth(max(0, minimum - 1)).wait_for(
            state="visible", timeout=(timeout_ms or self.timeout_ms)
        )
        return locator.count()

    def count(self, target: Target) -> int:
        return self._locate(target).count()

    def wait_for_count(
        self, target: Target, minimum: int = 1, timeout_ms: int | None = None
    ) -> int:
        deadline = (timeout_ms or self.timeout_ms) / 1000
        locator = self._locate(target)
        # nth(minimum-1) resolves only once that many elements exist, so this is an
        # actionability wait rather than a poll loop.
        locator.nth(max(0, minimum - 1)).wait_for(
            state="attached", timeout=(timeout_ms or self.timeout_ms)
        )
        del deadline
        return locator.count()

    def read_text(self, target: Target) -> str:
        return self._locate(target).inner_text()

    def read_all_texts(self, target: Target) -> list[str]:
        return [text.strip() for text in self._locate(target).all_inner_texts()]

    def aria_snapshot(self) -> str:
        """ARIA tree of the page. Retries once after giving a still-rendering app a
        moment: a blank snapshot must mean "the page was blank", never "we looked
        too early" — a triage agent cannot tell those apart from the artifact."""
        page = self._require_page()
        snapshot = ""
        for attempt in (0, 1):
            try:
                snapshot = page.locator("body").aria_snapshot(timeout=2_000)
            except Exception as exc:  # noqa: BLE001 - browser evidence is best-effort
                snapshot = f"<aria snapshot failed: {type(exc).__name__}>"
            if snapshot.strip() and not snapshot.startswith("<aria"):
                return snapshot
            if attempt == 0:
                self.wait_until_rendered(timeout_ms=2_000)
        return snapshot or "<page rendered no accessible content>"

    def screenshot(self, path: str) -> None:
        self._require_page().screenshot(path=path, full_page=False)

    def current_url(self) -> str:
        return self._require_page().url

    def eval_js(self, expression: str) -> Any:
        return self._require_page().evaluate(expression)

    #: One definition of "what this element looks like", shared by the green-run
    #: fingerprint and the failure-time candidate scan. They must agree: computing
    #: an attribute differently in the two places makes the same element score
    #: against itself as a stranger, which reads as "element gone".
    _FINGERPRINT_FN = """el => {
        const implicitRole = {BUTTON: 'button', A: 'link', H1: 'heading',
            H2: 'heading', H3: 'heading', SELECT: 'combobox', TEXTAREA: 'textbox',
            LI: 'listitem', INPUT: 'textbox'}[el.tagName] || null;
        return {
            tag: el.tagName.toLowerCase(),
            role: el.getAttribute('role') || implicitRole,
            ariaLabel: el.getAttribute('aria-label') || null,
            testid: el.getAttribute('data-testid') || null,
            text: (el.textContent || '').trim().slice(0, 80),
            id: el.id || null,
            classes: [...el.classList].slice(0, 5),
        };
    }"""

    def element_fingerprint(self, target: Target) -> dict[str, Any]:
        """Multi-attribute fingerprint captured on green runs; heal-diff fuel.

        Returns ``{}`` when the element is absent — an expected outcome after a step
        that waited for something to disappear, not an error worth waiting for.
        ``evaluate_all`` snapshots the current match set without auto-waiting and
        avoids the old count-then-evaluate pair of browser round-trips.
        """
        try:
            fingerprint = self._locate(target).evaluate_all(
                "(elements, source) => elements.length ? eval(source)(elements[0]) : null",
                self._FINGERPRINT_FN,
            )
            return fingerprint or {}
        except Exception:  # noqa: BLE001 - browser evidence is best-effort
            return {}

    def candidate_elements(self) -> list[dict[str, Any]]:
        script = """(fpSource) => {
            const fpOf = eval(fpSource);
            const sel = 'button, a, input, select, textarea, [role], [aria-label],'
                      + ' [data-testid], h1, h2, h3, li, label';
            const label = el => (el.getAttribute('aria-label')
                || el.getAttribute('placeholder')
                || (el.textContent || '').trim()).slice(0, 80);
            return [...document.querySelectorAll(sel)].slice(0, 400).map(el => {
                const fp = fpOf(el);
                const name = label(el);
                let target;
                // Addressing preference: stable test id, then semantics, then id.
                if (fp.testid) target = {kind: 'testid', value: fp.testid, name: null};
                else if (fp.role && name) target = {kind: 'role', value: fp.role, name};
                else if (fp.id) target = {kind: 'css', value: '#' + fp.id, name: null};
                else if (name) target = {kind: 'text', value: name, name: null};
                else return null;
                return {target, fingerprint: fp};
            }).filter(Boolean);
        }"""
        try:
            return self._require_page().evaluate(script, self._FINGERPRINT_FN)
        except Exception:  # noqa: BLE001 - browser evidence is best-effort
            return []

    # -- evidence taps -----------------------------------------------------------

    def network_log(self) -> list[NetRecord]:
        return list(self._net)

    def console_log(self) -> list[dict[str, Any]]:
        return list(self._console)

    def ws_log(self) -> list[dict[str, Any]]:
        return list(self._ws)

    def wait_ledger(self) -> list[dict[str, Any]]:
        return list(self._waits)

    def reset_taps(self) -> None:
        self._net.clear()
        self._pending.clear()
        self._console.clear()
        self._ws.clear()
        self._waits.clear()

    # -- triage hand-off -----------------------------------------------------------

    def browser_manifest(self) -> dict[str, Any]:
        endpoint = self.cdp_url or f"http://127.0.0.1:{self.debug_port}"
        return {
            "cdp_endpoint": endpoint,
            "page_url": self._page.url if self._page else None,
            "note": "browser left at failure state; attach with any CDP/MCP client",
        }
