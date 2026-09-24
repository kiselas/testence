"""Playwright-backed Engine implementation.

Two attach modes (ADR-0008):
- ``cdp_url`` given → connect_over_cdp to an already-running headed Chrome
  (developer's profile, existing session cookies, shared triage substrate).
- otherwise → launch a browser (Playwright's bundled ``chromium`` unless
  ``TESTENCE_BROWSER_CHANNEL`` or the caller names another channel), headed by
  default, with ``--remote-debugging-port`` so triage clients can attach later.

On failure the browser is deliberately left running (``keep_browser=True``):
the page at the failure state IS evidence.
"""

from __future__ import annotations

import re
import socket
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any, Callable

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Locator,
    Page,
    Playwright,
    sync_playwright,
)
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import expect as pw_expect

from testence.config import default_browser_channel

from .capabilities import Capability
from .protocol import Engine, NetRecord, Target

_DEFAULT_TIMEOUT_MS = 10_000
_RENDER_TIMEOUT_MS = 2_000
_BODY_CAP_BYTES = 64 * 1024
_WS_FRAME_CAP_BYTES = 8 * 1024
_TAP_RECORD_CAP = 2_000
_TAP_BYTE_CAP = 8 * 1024 * 1024
#: Poll interval for capture-buffer waits. Playwright events are dispatched while
#: ``wait_for_timeout`` yields to its message loop, so this is not a busy Python
#: poll. It is still a floor on how late an already completed mutation is observed:
#: 50 ms was visible on fast React APIs, while 10 ms stays cheap and responsive.
_POLL_MS = 10
#: Any scheme means the caller addressed a document directly: http(s), file, data,
#: about. Matching only "http"/"file:" prefixed base_url onto everything else.
_URL_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
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


def _free_tcp_port() -> int:
    """A port the operating system is currently willing to hand out.

    ``--remote-debugging-port=0`` lets the browser choose, but it reports the choice
    only inside its own profile directory, which Playwright creates somewhere the
    caller never learns. The triage manifest then advertises ``127.0.0.1:0``, which no
    CDP client can attach to, and the documented way to run isolated browsers side by
    side silently loses the "attach to the failure" promise. Pick the port here so the
    manifest names an endpoint that works.
    """

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


_EMULATION_KEYS = frozenset(
    {"device", "locale", "timezone_id", "geolocation", "permissions", "color_scheme", "user_agent"}
)
_COLOR_SCHEMES = ("light", "dark", "no-preference")


def _check_emulation(value: Any) -> dict[str, Any]:
    """Validate the ``emulation`` settings object before any browser starts."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("emulation must be an object")
    unknown = sorted(set(value) - _EMULATION_KEYS)
    if unknown:
        raise ValueError(
            "unknown emulation field(s): "
            + ", ".join(unknown)
            + "; known: "
            + ", ".join(sorted(_EMULATION_KEYS))
        )
    for key in ("device", "locale", "timezone_id", "user_agent"):
        if key in value and (not isinstance(value[key], str) or not value[key].strip()):
            raise ValueError(f"emulation.{key} must be a non-empty string")
    if "color_scheme" in value and value["color_scheme"] not in _COLOR_SCHEMES:
        raise ValueError("emulation.color_scheme must be one of " + ", ".join(_COLOR_SCHEMES))
    if "permissions" in value and (
        not isinstance(value["permissions"], list)
        or not all(isinstance(item, str) and item for item in value["permissions"])
    ):
        raise ValueError("emulation.permissions must be a list of permission names")
    if "geolocation" in value:
        position = value["geolocation"]
        if (
            not isinstance(position, dict)
            or not {"latitude", "longitude"}
            <= set(position)
            <= {"latitude", "longitude", "accuracy"}
            or not all(
                isinstance(position[key], (int, float)) and not isinstance(position[key], bool)
                for key in position
            )
            or not -90 <= position["latitude"] <= 90
            or not -180 <= position["longitude"] <= 180
        ):
            raise ValueError(
                "emulation.geolocation needs numeric latitude (-90..90) and longitude "
                "(-180..180), optionally accuracy"
            )
    return dict(value)


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
        browser_channel: str | None = None,
        ignore_https_errors: bool = False,
        reduce_motion: bool = False,
        user_data_dir: str | None = None,
        test_id_attribute: str = "",
        capture_network_bodies: bool = False,
        capture_screenshots: bool = False,
        admitted_body_content_types: tuple[str, ...] = ("application/json",),
        body_cap_bytes: int = _BODY_CAP_BYTES,
        viewport: dict[str, int] | None = None,
        screenshot_masks: tuple[Target, ...] = (),
        emulation: dict[str, Any] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.cdp_url = cdp_url
        self.headed = headed
        self.debug_port = debug_port
        self.api_prefix = api_prefix
        self.timeout_ms = timeout_ms
        self.browser_channel = browser_channel or default_browser_channel()
        self.ignore_https_errors = ignore_https_errors
        self.reduce_motion = reduce_motion
        self.user_data_dir = user_data_dir
        if viewport is not None and (
            not isinstance(viewport, dict)
            or set(viewport) != {"width", "height"}
            or any(type(v) is not int or not 1 <= v <= 4096 for v in viewport.values())
        ):
            raise ValueError("viewport requires integer width/height in 1..4096")
        if viewport is not None and cdp_url:
            raise ValueError("configure viewport in the owner of an attached browser")
        self.viewport = dict(viewport) if viewport is not None else None
        #: Context options for device, locale, time zone and the rest (``emulation``).
        self.emulation = _check_emulation(emulation)
        if self.emulation and cdp_url:
            raise ValueError(
                "emulation applies to a browser context Testence creates; configure it in "
                "the owner of an attached browser"
            )
        #: Painted over in every screenshot: text redaction cannot reach pixels.
        self.screenshot_masks = tuple(screenshot_masks)
        #: DOM attribute that ``Target("testid", ...)`` resolves against. Apps
        #: rarely ship `data-testid`; they do ship something stable (this project's
        #: tables carry `data-key` with the row's id). Pointing the test-id
        #: selector at it buys a measured 215 ms per row click against 261-332 ms
        #: for `:has()`/xpath addressing — not because resolution is slow (1.7-3.5
        #: ms either way) but because Playwright re-evaluates the selector on every
        #: actionability retry, and a flat attribute match is the cheapest one.
        self.test_id_attribute = test_id_attribute
        if body_cap_bytes < 0 or body_cap_bytes > _BODY_CAP_BYTES:
            raise ValueError(f"body_cap_bytes must be between 0 and {_BODY_CAP_BYTES}")
        self.capture_network_bodies = capture_network_bodies
        self.capture_screenshots = capture_screenshots
        self.admitted_body_content_types = tuple(
            value.strip().lower() for value in admitted_body_content_types if value.strip()
        )
        self.body_cap_bytes = body_cap_bytes
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._scope: Any | None = None
        self._js_scope: Any | None = None
        self._net: list[NetRecord] = []
        self._pending: dict[Any, NetRecord] = {}
        self._console: list[dict[str, Any]] = []
        self._ws: list[dict[str, Any]] = []
        self._capture_omissions: dict[str, int] = {}
        self._capture_bytes = 0
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
        try:
            self._open_session()
        except BaseException:
            # A start that fails halfway still owns a driver process, and often a
            # browser: the channel is unavailable, the debug port is taken, the
            # browser was never installed. Callers put `engine.stop()` in a finally
            # that only guards a successful start, so without this the processes
            # outlive every failed run and accumulate across a suite.
            self.stop()
            self._pw = None
            self._browser = None
            self._context = None
            raise

    def _open_session(self) -> None:
        if not self.cdp_url and self.debug_port == 0:
            self.debug_port = _free_tcp_port()
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
                **self._context_options(),
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
            self._context = self._browser.new_context(
                ignore_https_errors=self.ignore_https_errors, **self._context_options()
            )
            self._owns_context = True
        self._configure_context()

    def _context_options(self) -> dict[str, Any]:
        """``new_context`` keyword arguments for the configured emulation.

        A named ``device`` expands to Playwright's descriptor (viewport, user agent,
        scale factor, touch, mobile); explicit keys override it. Geolocation is useless
        without the permission, so it is granted along with the position.
        """
        if not self.emulation:
            return {}
        options: dict[str, Any] = {}
        device = self.emulation.get("device")
        if device:
            devices = self._pw.devices if self._pw is not None else {}
            if device not in devices:
                close = sorted(name for name in devices if device.lower() in name.lower())[:5]
                hint = f"; did you mean {', '.join(close)}" if close else ""
                raise ValueError(f"unknown emulation device {device!r}{hint}")
            options.update(devices[device])
            options.pop("default_browser_type", None)
        for key in ("locale", "timezone_id", "color_scheme", "user_agent"):
            if self.emulation.get(key):
                options[key] = self.emulation[key]
        permissions = list(self.emulation.get("permissions") or [])
        if self.emulation.get("geolocation"):
            options["geolocation"] = dict(self.emulation["geolocation"])
            if "geolocation" not in permissions:
                permissions.append("geolocation")
        if permissions:
            options["permissions"] = permissions
        return options

    def _configure_context(self) -> None:
        if self._context is None:
            raise RuntimeError("browser context was not created")
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
        self._scope = self._page
        self._js_scope = self._page
        if self.viewport is not None:
            self._page.set_viewport_size(
                {"width": self.viewport["width"], "height": self.viewport["height"]}
            )
        if self.reduce_motion:
            self._page.emulate_media(reduced_motion="reduce")
        self._attach_taps(self._page)

    def reset_session(self) -> None:
        """Give the next warm test a fresh context without relaunching Chromium."""
        self.reset_taps()
        if self.cdp_url:
            # An attached context belongs to its launcher and is explicitly an
            # authoring surface. Never discard its pages, cookies or storage.
            return
        if self.user_data_dir:
            # A persistent profile is itself the requested state boundary.
            return
        if self._browser is None:
            raise RuntimeError("engine is not started")
        if self._context is not None and self._owns_context:
            self._context.close()
        self._context = self._browser.new_context(
            ignore_https_errors=self.ignore_https_errors, **self._context_options()
        )
        self._owns_context = True
        self._configure_context()

    def capabilities(self) -> frozenset[str]:
        return frozenset(cap.value for cap in Capability)

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
        def admitted(content_type: str) -> bool:
            media_type = content_type.partition(";")[0].strip().lower()
            return self.capture_network_bodies and any(
                media_type == allowed
                or media_type.endswith("+json")
                and allowed == "application/json"
                for allowed in self.admitted_body_content_types
            )

        def bounded(value: str, limit: int | None = None) -> str:
            cap = self.body_cap_bytes if limit is None else limit
            raw = value.encode("utf-8")
            if len(raw) <= cap:
                return value
            return raw[:cap].decode("utf-8", errors="ignore")

        def declared_size(headers: dict[str, str]) -> int | None:
            try:
                value = int(headers.get("content-length", ""))
            except ValueError:
                return None
            return value if value >= 0 else None

        def omit(reason: str) -> None:
            self._capture_omissions[reason] = self._capture_omissions.get(reason, 0) + 1

        def reserve(size: int, reason: str) -> bool:
            if self._capture_bytes + size > _TAP_BYTE_CAP:
                omit(reason)
                return False
            self._capture_bytes += size
            return True

        def on_request(request: Any) -> None:
            if self.api_prefix not in request.url:
                return
            if len(self._net) >= _TAP_RECORD_CAP:
                omit("network_record_cap")
                return
            headers = request.headers
            content_type = str(headers.get("content-type", ""))
            size = declared_size(headers)
            captured_body = None
            if admitted(content_type) and size is not None and size <= self.body_cap_bytes:
                body = request.post_data or None
                captured_body = bounded(body) if body else None
            elif request.method not in {"GET", "HEAD"}:
                omit("request_body_policy")
            base_bytes = len(request.method.encode("utf-8")) + len(request.url.encode("utf-8"))
            body_bytes = len(captured_body.encode("utf-8")) if captured_body else 0
            if not reserve(base_bytes + body_bytes, "network_byte_cap"):
                if captured_body is None or not reserve(base_bytes, "network_byte_cap"):
                    return
                captured_body = None
            rec = NetRecord(
                method=request.method,
                url=request.url,
                status=None,
                started_ms=time.monotonic() * 1000,
                duration_ms=None,
                request_body=captured_body,
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
            content_type = str(response.headers.get("content-type", ""))
            size = declared_size(response.headers)
            should_consider = (response.status >= 400) or rec.method != "GET"
            if (
                should_consider
                and admitted(content_type)
                and size is not None
                and size <= self.body_cap_bytes
            ):
                try:
                    captured = bounded(response.text())
                    if reserve(len(captured.encode("utf-8")), "network_byte_cap"):
                        rec.response_body = captured
                except Exception:  # noqa: BLE001 - evidence capture is best-effort
                    rec.response_body = "<body unavailable>"
                    omit("response_body_error")
            elif should_consider:
                omit("response_body_policy")
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
                text = bounded(str(msg.text))
                size = len(msg.type.encode("utf-8")) + len(text.encode("utf-8"))
                if len(self._console) >= _TAP_RECORD_CAP:
                    omit("console_record_cap")
                elif reserve(size, "console_byte_cap"):
                    self._console.append({"level": msg.type, "text": text})

        def on_websocket(ws: Any) -> None:
            def on_frame(payload: Any) -> None:
                text = payload if isinstance(payload, str) else "<binary frame>"
                text = bounded(text, _WS_FRAME_CAP_BYTES)
                size = len(str(ws.url).encode("utf-8")) + len(text.encode("utf-8"))
                if len(self._ws) >= _TAP_RECORD_CAP:
                    omit("websocket_record_cap")
                elif reserve(size, "websocket_byte_cap"):
                    self._ws.append(
                        {
                            "url": ws.url,
                            "at_ms": time.monotonic() * 1000,
                            "payload": text,
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
        page = self._scope or self._require_page()
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

    def _require_js_scope(self) -> Any:
        return self._js_scope if self._js_scope is not None else self._require_page()

    def _require_page(self) -> Page:
        if self._page is None:
            raise RuntimeError("engine not started")
        return self._page

    # -- actions -------------------------------------------------------------

    def goto(self, url: str) -> None:
        absolute = bool(_URL_SCHEME.match(url))
        if not absolute and not self.base_url:
            # Otherwise the missing configuration surfaces much later as a browser
            # navigation error against a path with nothing in front of it.
            raise RuntimeError(
                f"cannot open {url!r}: no base_url is configured. Set base_url in "
                "testence.json, TESTENCE_BASE_URL in the environment, or pass an "
                "absolute URL."
            )
        full = url if absolute else f"{self.base_url}{url}"
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

    def select_label(self, target: Target, label: str) -> None:
        """Choose the option a person reads, not its ``value`` attribute."""
        with self._timed("select_label", f"{target.describe()} {label!r}"):
            self._locate(target).select_option(label=label)

    def hover(self, target: Target) -> None:
        with self._timed("hover", target.describe()):
            self._locate(target).hover()

    def set_checked(self, target: Target, checked: bool) -> None:
        """Check or uncheck; a no-op when the control is already in that state."""
        with self._timed("check" if checked else "uncheck", target.describe()):
            self._locate(target).set_checked(checked)

    def press(self, key: str) -> None:
        self._require_page().keyboard.press(key)

    def focus(self, target: Target) -> None:
        with self._timed("focus", target.describe()):
            self._locate(target).focus()

    def scroll_into_view(self, target: Target) -> None:
        with self._timed("scroll_into_view", target.describe()):
            self._locate(target).scroll_into_view_if_needed()

    def upload(self, target: Target, paths: list[str]) -> None:
        with self._timed("upload", target.describe()):
            self._locate(target).set_input_files(paths)

    def click_and_download(self, target: Target, path: str) -> str:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self._timed("download", target.describe()):
            with self._require_page().expect_download() as pending:
                self._locate(target).click()
            download = pending.value
            download.save_as(destination)
        return download.suggested_filename

    def click_and_popup(self, target: Target) -> None:
        with self._timed("popup", target.describe()):
            with self._require_page().expect_popup() as pending:
                self._locate(target).click()
            self._page = pending.value
            self._scope = self._page
            self._js_scope = self._page
            self._attach_taps(self._page)

    def switch_page(self, index: int) -> None:
        if self._context is None:
            raise RuntimeError("engine not started")
        pages = self._context.pages
        if index < 0 or index >= len(pages):
            raise IndexError(f"page index {index} is outside 0..{len(pages) - 1}")
        self._page = pages[index]
        self._scope = self._page
        self._js_scope = self._page
        # Without this the new page records no network, console or websocket
        # evidence, and a pack for a second tab looks like nothing ever happened.
        self._attach_taps(self._page)

    def page_count(self) -> int:
        if self._context is None:
            raise RuntimeError("engine not started")
        return len(self._context.pages)

    def switch_page_matching(self, url_contains: str, timeout_ms: int | None = None) -> None:
        """Switch to the open page whose URL contains ``url_contains``.

        A tab opened by the application appears a moment after the click that opens
        it, so this waits for it; more than one match is an error, like a locator.
        """
        if self._context is None:
            raise RuntimeError("engine not started")
        context = self._context
        deadline = time.monotonic() + (timeout_ms or self.timeout_ms) / 1000
        with self._timed("switch_page", f"url contains {url_contains!r}"):
            while True:
                matches = [
                    index for index, page in enumerate(context.pages) if url_contains in page.url
                ]
                if len(matches) > 1:
                    raise RuntimeError(
                        f"{len(matches)} open pages have a URL containing {url_contains!r}; "
                        "switch by index instead"
                    )
                if matches:
                    self.switch_page(matches[0])
                    return
                if time.monotonic() >= deadline:
                    raise AssertionError(f"no open page has a URL containing {url_contains!r}")
                # Page events arrive on the Playwright connection; a short wait
                # on the current page lets them be dispatched.
                self._require_page().wait_for_timeout(50)

    def close_page(self) -> None:
        """Close the current page and continue on the most recently opened one left."""
        if self._context is None or self._page is None:
            raise RuntimeError("engine not started")
        if len(self._context.pages) < 2:
            raise RuntimeError("cannot close the only open page")
        with self._timed("close_page", self._page.url):
            self._page.close()
        self.switch_page(len(self._context.pages) - 1)

    # -- clock -----------------------------------------------------------------
    #
    # Playwright's fake timers (Page.clock, 1.45+) for the context: Date, timers and
    # animation frames follow the test instead of the wall clock.

    def _clock(self) -> Any:
        if self._context is None:
            raise RuntimeError("engine not started")
        return self._context.clock

    def clock_install(self, moment: Any = None) -> None:
        with self._timed("clock_install", repr(moment)):
            if moment is None:
                self._clock().install()
            else:
                self._clock().install(time=moment)

    def clock_fast_forward(self, ticks: int | str) -> None:
        with self._timed("clock_fast_forward", repr(ticks)):
            self._clock().fast_forward(ticks)

    def clock_pause_at(self, moment: Any) -> None:
        with self._timed("clock_pause_at", repr(moment)):
            self._clock().pause_at(moment)

    def clock_resume(self) -> None:
        with self._timed("clock_resume"):
            self._clock().resume()

    def clock_set_fixed_time(self, moment: Any) -> None:
        with self._timed("clock_set_fixed_time", repr(moment)):
            self._clock().set_fixed_time(moment)

    def click_with_dialog(
        self, target: Target, *, accept: bool = True, prompt: str | None = None
    ) -> str:
        message: list[str] = []

        def handle(dialog: Any) -> None:
            message.append(dialog.message)
            if accept:
                dialog.accept(prompt)
            else:
                dialog.dismiss()

        page = self._require_page()
        page.once("dialog", handle)
        with self._timed("dialog", target.describe()):
            self._locate(target).click()
        return message[0] if message else ""

    @contextmanager
    def frame(self, target: Target) -> Iterator[None]:
        previous = self._scope
        previous_js = self._js_scope
        locator = self._locate(target)
        frame_locator = locator.content_frame
        element = locator.element_handle()
        frame = element.content_frame() if element is not None else None
        if frame_locator is None or frame is None:
            raise RuntimeError(f"target is not an attached frame: {target.describe()}")
        self._scope = frame_locator
        self._js_scope = frame
        try:
            yield
        finally:
            self._scope = previous
            self._js_scope = previous_js

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
            try:
                self._locate(target).filter(has_text=matcher).wait_for(
                    state="visible", timeout=timeout_ms or self.timeout_ms
                )
            except PlaywrightTimeoutError as exc:
                # A completed wait for text that never appeared is the product
                # disagreeing with the test, exactly as in expect_visible; reports
                # must not file it as an environment failure.
                raise AssertionError(
                    f"expected text {text!r} {'exactly' if exact else 'within'} "
                    f"{target.describe()}, which did not appear"
                ) from exc

    def expect_visible(self, target: Target, timeout_ms: int | None = None) -> None:
        with self._timed("expect_visible", target.describe()):
            try:
                self._locate(target).wait_for(
                    state="visible", timeout=timeout_ms or self.timeout_ms
                )
            except PlaywrightTimeoutError as exc:
                raise AssertionError(f"target did not become visible: {target.describe()}") from exc

    # -- state assertions ---------------------------------------------------
    #
    # Each is one Playwright web-first assertion: it retries until the state holds or
    # the timeout ends, and a completed wait that never saw the state raises
    # AssertionError — the product disagreeing, reported as ``failed``, never as an
    # environment failure (the rule expect_text and expect_visible follow).

    def _assert_state(self, op: str, detail: str, check: Callable[[], None]) -> None:
        with self._timed(op, detail):
            try:
                check()
            except AssertionError as exc:
                # Playwright appends its call log; the first lines carry the verdict.
                lines = [line for line in str(exc).splitlines() if line.strip()]
                summary = "; ".join(lines[:3]) if lines else type(exc).__name__
                raise AssertionError(f"{op} {detail}: {summary}") from exc

    def expect_hidden(self, target: Target, timeout_ms: int | None = None) -> None:
        timeout = timeout_ms or self.timeout_ms
        self._assert_state(
            "expect_hidden",
            target.describe(),
            lambda: pw_expect(self._locate(target)).to_be_hidden(timeout=timeout),
        )

    def expect_value(self, target: Target, value: str, timeout_ms: int | None = None) -> None:
        timeout = timeout_ms or self.timeout_ms
        self._assert_state(
            "expect_value",
            f"{target.describe()} == {value!r}",
            lambda: pw_expect(self._locate(target)).to_have_value(value, timeout=timeout),
        )

    def expect_count(self, target: Target, count: int, timeout_ms: int | None = None) -> None:
        timeout = timeout_ms or self.timeout_ms
        self._assert_state(
            "expect_count",
            f"{target.describe()} == {count}",
            lambda: pw_expect(self._locate(target)).to_have_count(count, timeout=timeout),
        )

    def expect_enabled(
        self, target: Target, enabled: bool = True, timeout_ms: int | None = None
    ) -> None:
        timeout = timeout_ms or self.timeout_ms
        self._assert_state(
            "expect_enabled" if enabled else "expect_disabled",
            target.describe(),
            lambda: pw_expect(self._locate(target)).to_be_enabled(enabled=enabled, timeout=timeout),
        )

    def expect_checked(
        self, target: Target, checked: bool = True, timeout_ms: int | None = None
    ) -> None:
        timeout = timeout_ms or self.timeout_ms
        self._assert_state(
            "expect_checked" if checked else "expect_unchecked",
            target.describe(),
            lambda: pw_expect(self._locate(target)).to_be_checked(checked=checked, timeout=timeout),
        )

    def expect_attribute(
        self, target: Target, name: str, value: str, timeout_ms: int | None = None
    ) -> None:
        timeout = timeout_ms or self.timeout_ms
        self._assert_state(
            "expect_attribute",
            f"{target.describe()} [{name}] == {value!r}",
            lambda: pw_expect(self._locate(target)).to_have_attribute(name, value, timeout=timeout),
        )

    def expect_url(
        self,
        *,
        contains: str | None = None,
        equals: str | None = None,
        timeout_ms: int | None = None,
    ) -> None:
        """The page URL contains a fragment, or equals a URL (relative to base_url)."""
        if (contains is None) == (equals is None):
            raise ValueError("expect_url takes exactly one of contains= or equals=")
        timeout = timeout_ms or self.timeout_ms
        if equals is not None:
            expected: Any = (
                equals
                if _URL_SCHEME.match(equals) or not self.base_url
                else f"{self.base_url}{equals}"
            )
            detail = f"== {expected!r}"
        else:
            expected = re.compile(re.escape(str(contains)))
            detail = f"contains {contains!r}"
        self._assert_state(
            "expect_url",
            detail,
            lambda: pw_expect(self._require_page()).to_have_url(expected, timeout=timeout),
        )

    def wait_while_visible(self, target: Target, timeout_ms: int | None = None) -> None:
        with self._timed("wait_while_visible", target.describe()):
            self._locate(target).wait_for(state="hidden", timeout=timeout_ms or self.timeout_ms)

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
        predicate: Callable[[NetRecord], bool] | None = None,
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
                    if predicate is not None and not predicate(record):
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
                self._require_js_scope().wait_for_function(
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
        page = self._require_page()
        masks = [self._locate(target) for target in self.screenshot_masks]
        if masks:
            page.screenshot(path=path, full_page=False, mask=masks, mask_color="#000000")
        else:
            page.screenshot(path=path, full_page=False)

    def native_page(self) -> Page:
        """The Playwright page behind this engine, for ``Actions.native`` only.

        The one sanctioned place where a Playwright type leaves the engine
        (ADR-0027): the DSL records the step around it, so evidence still knows an
        unrecorded interaction happened and why.
        """
        return self._require_page()

    def current_url(self) -> str:
        return self._require_page().url

    def eval_js(self, expression: str) -> Any:
        return self._require_js_scope().evaluate(expression)

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
        self._capture_omissions.clear()
        self._capture_bytes = 0

    # -- triage hand-off -----------------------------------------------------------

    def browser_manifest(self) -> dict[str, Any]:
        endpoint = self.cdp_url or f"http://127.0.0.1:{self.debug_port}"
        return {
            "cdp_endpoint": endpoint,
            "page_url": self._page.url if self._page else None,
            "owns_browser": self._launched_here,
            "owns_context": self._owns_context,
            "mode": "attached" if self.cdp_url else "isolated",
            "viewport": self._page.viewport_size if self._page else None,
            "capture": {
                "network_bodies": self.capture_network_bodies,
                "screenshots": self.capture_screenshots,
                "screenshot_masks": [target.describe() for target in self.screenshot_masks],
                "admitted_body_content_types": list(self.admitted_body_content_types),
                "body_cap_bytes": self.body_cap_bytes,
                "record_cap": _TAP_RECORD_CAP,
                "byte_cap": _TAP_BYTE_CAP,
                "retained_bytes": self._capture_bytes,
                "omissions": dict(sorted(self._capture_omissions.items())),
            },
            "note": "browser left at failure state; attach with any CDP/MCP client",
        }
