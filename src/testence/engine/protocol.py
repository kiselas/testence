"""Engine facade: the only boundary the rest of the framework talks through.

ADR-0001: the browser-driving library is an implementation detail. Nothing outside
``testence.engine`` may import it or accept/return its types. This keeps the door open
for a CDP-native executor (the Stagehand-v3 route) as a future optimization instead
of a rewrite, and lets tests of upper layers use a fake engine.

Kept intentionally small: an entry is added only when a DSL primitive needs it.
CDP-specific abilities must be modeled as optional capabilities, not core methods.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

#: How a Target may address an element. Order reflects preference: semantics first,
#: raw CSS last (heal-diffs and intent caching key off semantic addressing).
TARGET_KINDS = ("role", "label", "text", "testid", "placeholder", "css")


@dataclass(frozen=True)
class Target:
    """Semantic element address. ``kind`` ∈ TARGET_KINDS.

    ``name`` refines role targets (ARIA accessible name); ``nth`` disambiguates
    legitimate repeats. A Target is data, not behavior — engines interpret it.

    ``exact`` controls string matching, and the default is deliberate: identity
    attributes (label, placeholder, role name) match **exactly**, while ``text``
    targets match as a substring. Loose matching on an identifier is a silent
    hazard — a renamed "name" field still matches "full name", so a test keeps
    passing against an element it was never meant to address. Exact matching turns
    that into a visible failure with a heal proposal. Pass ``exact=False``
    explicitly where a label genuinely carries a dynamic part.
    """

    kind: str
    value: str
    name: str | None = None
    nth: int | None = None
    exact: bool | None = None

    def __post_init__(self) -> None:
        if self.kind not in TARGET_KINDS:
            raise ValueError(f"unknown target kind: {self.kind!r}")

    def matches_exactly(self) -> bool:
        if self.exact is not None:
            return self.exact
        return self.kind != "text"

    def describe(self) -> str:
        parts = [f"{self.kind}={self.value!r}"]
        if self.name:
            parts.append(f"name={self.name!r}")
        if self.nth is not None:
            parts.append(f"nth={self.nth}")
        if not self.matches_exactly():
            parts.append("substring")
        return " ".join(parts)


@dataclass
class NetRecord:
    """One captured request/response pair (API traffic only, by prefix filter)."""

    method: str
    url: str
    status: int | None
    started_ms: float
    duration_ms: float | None
    request_body: str | None = None
    response_body: str | None = None
    #: Set when the browser never received a response — most often because the
    #: application aborted the request itself (a component unmounting cancels its
    #: in-flight fetch). The server may well have applied the change: a record with
    #: a ``failure`` and no ``status`` means "sent, outcome unobservable here", and
    #: a case must then synchronize on the request or on an API oracle instead.
    #: Without this field such a record simply stayed at ``status=None`` forever and
    #: every ``wait_for_response`` on it burned its whole budget in silence.
    failure: str | None = None

    def json_body(self) -> Any:
        """Parsed response body, or ``None`` when absent or not JSON.

        The tap captures bodies for every mutation and every error, so the record
        of a POST the UI just made carries the created entity — the id is right
        here, and reading it beats polling a list endpoint until the row appears.
        """
        if not self.response_body:
            return None
        import json

        try:
            return json.loads(self.response_body)
        except ValueError:
            return None


def dump_net(records: list[NetRecord]) -> str:
    """Serialize captured traffic as JSONL for an evidence pack.

    Lives here, next to NetRecord, because it touches only our own types — putting
    it in the Playwright module made the triage layer import from the engine
    implementation, which is exactly what ADR-0001 forbids.
    """
    import json

    lines = []
    for record in records:
        doc: dict[str, Any] = {
            "method": record.method,
            "url": record.url,
            "status": record.status,
            "ms": round(record.duration_ms, 1) if record.duration_ms is not None else None,
        }
        if record.failure:
            doc["failure"] = record.failure
        if record.request_body:
            doc["req"] = record.request_body
        if record.response_body:
            doc["resp"] = record.response_body
        lines.append(json.dumps(doc, ensure_ascii=False))
    return "\n".join(lines)


@runtime_checkable
class Engine(Protocol):
    """Synchronous driving surface. Implementations own waiting semantics:
    every action must wait for actionability internally — DSL code never sleeps."""

    # -- lifecycle -------------------------------------------------------
    def start(self) -> None: ...
    def stop(self, *, keep_browser: bool = False) -> None: ...

    # -- navigation / actions -------------------------------------------
    def goto(self, url: str) -> None: ...
    def navigate(self, url: str, *, hard: bool = False) -> bool:
        """Reach an in-app route, client-side when possible; True if it was.

        A full document load re-boots the whole application (seconds); the app's
        own router does the same navigation in tens of milliseconds. Since a suite
        navigates constantly, this is the difference between a slow suite and a
        fast one. ``hard=True`` forces a real reload — required when the case's
        subject is first-load behaviour, since client-side routing preserves the
        component state of an already-mounted route.
        """
        ...
    def click(self, target: Target, *, fast: bool = False) -> None:
        """Click the target. ``fast=True`` skips the actionability checks.

        The checks (visible, enabled, stable, receives-events) cost ~83 ms per
        click and are what turn "an overlay ate the click" into a readable
        timeout. Skip them only where a preceding wait already proved the element
        is present and hittable.
        """
        ...
    def fill(self, target: Target, value: str) -> None: ...
    def select(self, target: Target, value: str) -> None: ...
    def press(self, key: str) -> None: ...

    # -- session ------------------------------------------------------------
    def cookies(self) -> list[dict[str, Any]]: ...
    def add_cookies(self, cookies: list[dict[str, Any]]) -> None: ...
    def set_extra_http_headers(self, headers: dict[str, str]) -> None: ...
    def set_storage_item(self, key: str, value: str, *, session: bool = False) -> None: ...
    def storage_snapshot(self) -> dict[str, str]: ...

    # -- observation ------------------------------------------------------
    def expect_text(self, target: Target, text: str, timeout_ms: int | None = None,
                    *, exact: bool = True) -> None:
        """Wait until the target reads `text`. Exact by default — substring
        matching on a value is a silent hazard (see the note in `Target`)."""
        ...
    def expect_visible(self, target: Target, timeout_ms: int | None = None) -> None: ...
    def wait_while_visible(self, target: Target, timeout_ms: int | None = None) -> None: ...
    def wait_for_url_contains(self, fragment: str, timeout_ms: int | None = None) -> None: ...
    def wait_until_rendered(self, timeout_ms: int = 5_000) -> bool: ...
    def settle(self, timeout_ms: int = 1_500) -> bool:
        """Best-effort wait for in-flight requests to finish.

        Used before capturing evidence: an application that is still fetching its
        data yields a half-built snapshot, and a half-built snapshot sends a triage
        agent hunting for an element that simply had not arrived yet. Returns
        whether the page went quiet; never raises.
        """
        ...
    def count(self, target: Target) -> int: ...
    def wait_for_count(self, target: Target, minimum: int = 1,
                       timeout_ms: int | None = None) -> int:
        """Wait until at least ``minimum`` elements match, then return the count.

        Visibility of one element is not the same as a loaded collection: a data
        grid renders its frame, then remounts its rows when the response lands, so
        a read taken between those moments sees an empty table. This waits for the
        collection instead of for a container, without sleeping.
        """
        ...
    def wait_for_content(self, target: Target, minimum: int = 1,
                         timeout_ms: int | None = None) -> int:
        """Wait until at least ``minimum`` matching elements carry actual text.

        The strictest of the three collection waits, and usually the right one. A
        data grid renders skeleton rows first: the elements exist, are visible, and
        are empty. Waiting on their presence hands the test placeholders, so a real
        readiness check waits for content.
        """
        ...
    def read_text(self, target: Target) -> str: ...
    def read_all_texts(self, target: Target) -> list[str]:
        """Texts of every element matching the target.

        Exists so ActionMaps can read collections (table rows, list items) through
        semantic addressing instead of raw DOM queries: ARIA roles are largely
        *implicit* (a <th> is a rowheader without saying so), so
        querySelectorAll('[role=...]') finds nothing while the accessibility tree
        clearly shows the element.
        """
        ...
    def aria_snapshot(self) -> str: ...
    def screenshot(self, path: str) -> None: ...
    def current_url(self) -> str: ...
    def eval_js(self, expression: str) -> Any: ...
    def element_fingerprint(self, target: Target) -> dict[str, Any]: ...
    def candidate_elements(self) -> list[dict[str, Any]]:
        """Every addressable element on the page: ``{"fingerprint": {...},
        "target": {"kind": ..., "value": ..., "name": ...}}``.

        Used only on failure, to look for where a drifted element went. Proposing
        Target addressing (not raw DOM) keeps heal proposals expressible as edits
        to test code.
        """
        ...

    def wait_for_request(self, url_contains: str, *, method: str | None = None,
                         since: int = 0, timeout_ms: int | None = None) -> bool:
        """Wait until the application sends a request matching URL and method.

        Debounced inputs make "typed the query" and "searched" different events, and
        asserting on the table between them reports a false failure. This also lets a
        test prove the negative case — that a client-side validation stopped a
        request from ever leaving.

        ``url_contains`` is matched against the URL and ``method`` against the
        verb; the two are not interchangeable, and passing a verb as the fragment
        raises rather than never matching. Proving a negative costs the full
        timeout by construction, so give such calls a small explicit budget.
        """
        ...

    def net_mark(self) -> int:
        """Position marker in the capture buffer, for scoping response waits.

        Take a mark *before* the action, pass it to ``wait_for_response`` as
        ``since`` — otherwise an earlier request to the same endpoint (a list
        refetch, a previous save) satisfies the wait and the test synchronizes on
        the wrong round-trip.
        """
        ...

    def wait_for_response(self, url_contains: str, *, method: str | None = None,
                          since: int = 0,
                          timeout_ms: int | None = None) -> NetRecord | None:
        """Wait for a *completed* response matching the fragment (and method).

        The network tap is the synchronization primitive for UI mutations: every
        mutation has exactly one network consequence, and its response is the
        moment the outcome exists — before the DOM re-renders and before a list
        endpoint would show it. Waiting on anything else (network quiet, fixed
        sleeps, polling an oracle) is a race dressed up as a wait. Returns the
        record — its ``json_body()`` typically carries the created/updated entity —
        or ``None`` on timeout.
        """
        ...

    def wait_for_value(self, target: Target, timeout_ms: int | None = None) -> str:
        """Wait until an input carries a non-empty value, and return it.

        The form-control counterpart of ``wait_for_content``: an ``<input>``'s
        value is not a text node, so content waits never see it — while a panel
        that renders before its record arrives shows exactly such empty inputs.
        """
        ...

    def ws_mark(self) -> int:
        """Position marker in the WebSocket frame buffer (see ``net_mark``)."""
        ...

    def wait_for_ws(self, payload_contains: str, *, since: int = 0,
                    timeout_ms: int | None = None) -> dict[str, Any] | None:
        """Wait for a WebSocket frame whose payload contains the fragment.

        Live-update events (``...Created``/``...Updated`` pushed by the server) are
        the only push signal for changes made by another session — the correct
        thing to synchronize a live-update case on, instead of sleeping and hoping.
        """
        ...

    def wait_for_predicate_js(self, expression: str,
                              timeout_ms: int | None = None) -> bool:
        """Wait until a JS predicate holds (rAF-driven); returns whether it did.

        The escape hatch for readiness no locator expresses — "every visible row
        matches the filter". Prefer the specific waits above when one fits.
        """
        ...

    # -- evidence taps ----------------------------------------------------
    def network_log(self) -> list[NetRecord]: ...
    def console_log(self) -> list[dict[str, Any]]: ...
    def ws_log(self) -> list[dict[str, Any]]:
        """Captured WebSocket frames: ``{url, at_ms, payload}``."""
        ...
    def wait_ledger(self) -> list[dict[str, Any]]:
        """Every timed action/wait this test performed: ``{op, detail, ms, ok}``.

        The run's honest time budget. When a suite is slow, the answer is here:
        which waits burned the time, on what, and whether they even succeeded.
        """
        ...
    def reset_taps(self) -> None:
        """Clear per-test capture buffers (called between tests by the runner)."""
        ...

    # -- triage hand-off --------------------------------------------------
    def browser_manifest(self) -> dict[str, Any]:
        """Where a triage agent can attach: cdp endpoint, page url, liveness."""
        ...
