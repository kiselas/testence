"""Step primitives: every action is logged with its *intent*.

The intent (a human sentence: "open the host panel", "save the subnet form") is not
decoration. It is (a) what a triage agent reads instead of replaying the run,
(b) the future cache key for AI-materialized steps (``ai_step`` escape hatch),
(c) what a heal-diff preserves when a locator drifts. Project ActionMaps compose
these primitives; test cases should read as 5–15 intent-bearing lines.
"""

from __future__ import annotations

import re
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterator

from testence.engine import (
    Box,
    Capability,
    Engine,
    NetRecord,
    Target,
    UnsupportedCapability,
    engine_capabilities,
    require_capabilities,
)
from testence.evidence import EvidenceWriter
from testence.fingerprints import FingerprintStore

if TYPE_CHECKING:
    from testence.api import Response
    from testence.oracle import ExpectedState, OracleObservation


class StepFailed(AssertionError):
    def __init__(
        self, intent: str, cause: Exception, target: Target | None = None, matches: str = ""
    ) -> None:
        # What the target matched goes before the cause: Playwright appends a
        # multi-line call log to its message, and the answer should not sit under it.
        found = f": {matches}" if matches else ""
        super().__init__(f"step failed: {intent}{found} ({cause.__class__.__name__}: {cause})")
        self.intent = intent
        self.cause = cause
        self.target = target
        #: What the target resolved to when the step failed, or "" if unknown.
        self.matches = matches


@dataclass
class StepFailure:
    """What the runner needs to reason about a failure after the fact."""

    intent: str
    target: Target | None
    error: str


class SoftAssertionsFailed(AssertionError):
    """Checks that failed inside ``with ex.soft(...)``, raised once at its end."""

    def __init__(self, intent: str, failures: list[StepFailure]) -> None:
        self.intent = intent
        self.failures = list(failures)
        listed = "\n".join(f"  - {failure.intent}: {failure.error}" for failure in failures)
        count = len(failures)
        super().__init__(
            f"{count} check{'s' if count != 1 else ''} failed in {intent!r}:\n{listed}"
        )


def describe_matches(engine: Any, target: Target) -> str:
    """The engine's account of what ``target`` matches now; "" if it has none.

    A failed step puts it in its message; the MCP click and fill tools answer with it
    too, so an agent exploring a page reads the same hint as one running a test.
    """
    describe = getattr(engine, "describe_matches", None)
    if not callable(describe):
        return ""
    try:
        return str(describe(target))
    except Exception:  # noqa: BLE001 - a diagnostic never replaces the failure
        return ""


_UNSET: Any = object()


class ExpectedRequest:
    """What ``ex.expect_request`` found; ``record`` is set when the block ends."""

    def __init__(self, label: str) -> None:
        self.label = label
        self.record: NetRecord | None = None

    @property
    def response(self) -> NetRecord:
        """The completed record; raises before the block has finished or found one."""
        if self.record is None:
            raise RuntimeError(f"no response for {self.label} yet: read it after the block")
        return self.record


@dataclass
class ExpectedOutcome:
    name: str | None = None


@dataclass
class _EngineOperation:
    """DSL producer metadata, not an attestation of browser-side dispatch."""

    producer: str
    engine_type: str
    method: str
    dispatch: str = "not_called"

    def to_json(self) -> dict[str, str]:
        return {
            "producer": self.producer,
            "engine_type": self.engine_type,
            "method": self.method,
            "dispatch": self.dispatch,
        }

    def invoke(self, method: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        try:
            result = method(*args, **kwargs)
        except Exception:
            self.dispatch = "raised"
            raise
        self.dispatch = "returned"
        return result


#: How often a green step's element fingerprint is taken (``evidence.fingerprints``).
FINGERPRINT_POLICIES = ("every-green", "once")


def _check_minimum(reader: str, minimum: Any) -> None:
    if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 0:
        raise ValueError(f"{reader} minimum must be a non-negative integer")


class Actions:
    """Engine + evidence, bound to one test. Projects build ActionMaps on top."""

    def __init__(
        self,
        engine: Engine,
        writer: EvidenceWriter,
        test_id: str,
        store: FingerprintStore | None = None,
        *,
        fingerprints: str = "every-green",
    ) -> None:
        if fingerprints not in FINGERPRINT_POLICIES:
            raise ValueError(f"fingerprints must be one of {', '.join(FINGERPRINT_POLICIES)}")
        self.engine = engine
        self.writer = writer
        self.test_id = test_id
        self.store = store
        #: ``every-green``: a fingerprint after every green step with a target, so the
        #: store holds the last green run; ``once``: only when the store lacks it.
        self.fingerprints = fingerprints
        #: Set when a step raises; the runner reads it to build a heal proposal.
        self.last_failure: StepFailure | None = None
        self._step_no = 0
        #: Child counters, one per open step. An ActionMap method composes
        #: primitives, so steps nest — and a composite step's duration *contains*
        #: its children's. Recording how many children each step had is what lets
        #: `metrics.py` average leaves only: summing every step.end double-counted
        #: half of them (48 of 95 step starts in a recent run were nested, and the
        #: step total came out larger than the test total, which cannot be true).
        self._children: list[int] = []
        #: Fields the open steps add to their ``step.end`` (innermost last).
        self._annotations: list[dict[str, Any]] = []
        #: Failed checks collected by the open ``ex.soft`` block, if any.
        self._soft: list[StepFailure] | None = None
        observer = getattr(engine, "set_native_mock_observer", None)
        if callable(observer):
            observer(lambda **data: self.writer.emit("network.mocked", test=self.test_id, **data))
        # A goto's render probe waits for the first step that has no element to
        # wait for; a step with a target waits for its own element (B3).
        if hasattr(engine, "defer_render_probe"):
            engine.defer_render_probe = True
        #: Gates opened by ``ws_gate``; each is summarized when the test ends.
        self._ws_gates: list[WebSocketGate] = []
        gate_observer = getattr(engine, "set_ws_gate_observer", None)
        if callable(gate_observer):
            gate_observer(
                lambda **data: self.writer.emit("websocket.gated", test=self.test_id, **data)
            )

    # -- core wrapper ------------------------------------------------------

    @contextmanager
    def step(
        self,
        intent: str,
        target: Target | None = None,
        *,
        weakenings: tuple[str, ...] = (),
        check: bool = False,
        destination: Target | None = None,
        _operation: _EngineOperation | None = None,
        _absence: bool = False,
    ) -> Iterator[None]:
        """One recorded step. ``check=True`` marks an assertion, which an open
        ``ex.soft`` block records and lets the test continue past. ``destination``
        is a second element the step acts on; a failure describes it too."""
        self._step_no += 1
        step_id = f"s{self._step_no}"
        depth = len(self._children)
        if self._children:
            self._children[-1] += 1
        self._children.append(0)
        self._annotations.append({})
        # A check that passes when the element is absent (expect_hidden, a count of
        # zero) proves nothing about a page that has not rendered yet: it gets the
        # render probe like a step without a target.
        self._render_probe(None if _absence else target)
        self.writer.emit(
            "step.start",
            test=self.test_id,
            step=step_id,
            intent=intent,
            target=target.describe() if target else None,
            weakenings=list(weakenings),
            depth=depth,
            **({"operation": _operation.to_json()} if _operation else {}),
        )
        started = time.perf_counter()
        try:
            yield
        except Exception as exc:
            matches = (
                self._describe_matches(target)
                if target is not None and not isinstance(exc, UnsupportedCapability)
                else ""
            )
            if destination is not None and not isinstance(exc, UnsupportedCapability):
                there = self._describe_matches(destination)
                if there:
                    matches = f"source: {matches or 'unknown'}; destination: {there}"
            error = f"{exc.__class__.__name__}: {exc}"
            if matches:
                error = f"{error} [{matches}]"
            self.last_failure = StepFailure(intent=intent, target=target, error=error)
            # Only a completed check that disagreed is softened: an action that failed,
            # an unavailable engine or a broken browser still stops the test.
            softened = (
                check
                and self._soft is not None
                and isinstance(exc, AssertionError)
                and not isinstance(exc, UnsupportedCapability)
            )
            self._annotations.pop()
            self.writer.emit(
                "step.end",
                test=self.test_id,
                step=step_id,
                status="fail",
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
                error=error,
                depth=depth,
                children=self._children.pop(),
                **({"soft": True} if softened else {}),
                **({"operation": _operation.to_json()} if _operation else {}),
            )
            if softened:
                assert self._soft is not None
                self._soft.append(self.last_failure)
                return
            if isinstance(exc, UnsupportedCapability):
                raise
            raise StepFailed(intent, exc, target, matches) from exc
        fingerprint, kept = self._fingerprint(intent, target)
        if kept:
            self._annotations[-1]["fingerprint_kept"] = kept
        self.writer.emit(
            "step.end",
            test=self.test_id,
            step=step_id,
            status="ok",
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
            fingerprint=fingerprint or None,
            depth=depth,
            children=self._children.pop(),
            **self._annotations.pop(),
            **({"operation": _operation.to_json()} if _operation else {}),
        )

    def _fingerprint(self, intent: str, target: Target | None) -> tuple[dict[str, Any] | None, str]:
        """The element's fingerprint after a green step, and why none was taken.

        It is the baseline a heal proposal is measured against. By default
        (``every-green``) it is taken after every green step with a target, so the
        store holds the last green run. With ``evidence.fingerprints: once`` a store
        that already holds it for the same step and target is not asked again
        (``"stored"``): one browser round trip saved per step on every green replay,
        and the baseline is the first green run of that step and target.
        """
        if target is None:
            return None, ""
        if (
            self.fingerprints == "once"
            and self.store is not None
            and self.store.holds(self.test_id, intent, target.describe())
        ):
            return None, "stored"
        fingerprint = self.engine.element_fingerprint(target)
        if fingerprint and self.store is not None:
            # Remember what "working" looked like: the only baseline a heal
            # proposal can honestly be measured against.
            self.store.record(self.test_id, intent, target.describe(), fingerprint)
        return fingerprint or None, ""

    def _render_probe(self, target: Target | None) -> None:
        """Settle a goto's deferred render probe before this step starts.

        A step that needs its element present waits for it, which is a stronger
        readiness signal than "the app painted something"; a step without a target (a
        URL check, a screenshot, raw access, an oracle) and a check that passes on an
        absent element (``expect_hidden``, ``expect_count(..., 0)``) get the probe.
        """
        due = getattr(self.engine, "render_probe_due", None)
        if not callable(due) or not due():
            return
        if target is not None:
            self.engine.skip_render_probe()  # type: ignore[attr-defined]
        else:
            self.engine.flush_render_probe()  # type: ignore[attr-defined]

    def finish(self) -> None:
        """End of the test: a deferred render probe still due runs now.

        After a failed step it is dropped instead: it would only wait out its timeout
        on a page that broke, and evidence code that reads the page runs it anyway.
        """
        due = getattr(self.engine, "render_probe_due", None)
        if callable(due) and due():
            if self.last_failure is not None:
                self.engine.skip_render_probe()  # type: ignore[attr-defined]
            else:
                self.engine.flush_render_probe()  # type: ignore[attr-defined]
        self._finish_ws_gates()

    def _describe_matches(self, target: Target) -> str:
        return describe_matches(self.engine, target)

    def _engine_method(self, name: str) -> Callable[..., Any]:
        """An engine operation added after the first Engine protocol.

        A third-party engine written earlier may not have it; it then gets the same
        UnsupportedCapability as a missing capability, naming the operation, rather
        than an AttributeError from deep inside a step.
        """
        method = getattr(self.engine, name, None)
        if not callable(method):
            raise UnsupportedCapability(
                name,
                {f"{name} (not implemented by {type(self.engine).__name__})"},
                set(engine_capabilities(self.engine)),
            )
        return method  # type: ignore[no-any-return]

    # -- primitives ------------------------------------------------------------

    def _operation(self, method: str) -> _EngineOperation:
        engine_type = type(self.engine)
        return _EngineOperation(
            producer=f"testence.dsl.steps.Actions.{method}",
            engine_type=f"{engine_type.__module__}.{engine_type.__qualname__}",
            method=method,
        )

    def goto(self, url: str, intent: str | None = None) -> None:
        with self.step(intent or f"open {url}"):
            require_capabilities(self.engine, "goto", Capability.NAVIGATION)
            self.engine.goto(url)

    def navigate(self, url: str, intent: str | None = None, *, hard: bool = False) -> bool:
        """Reach a route the fast way (client-side routing) — see Engine.navigate.

        Prefer this over ``goto`` for in-app navigation: a full reload costs
        seconds per call, the app's router costs milliseconds. Use ``hard=True``
        only when the case is *about* a fresh page load.
        """
        with self.step(intent or f"go to {url}"):
            require_capabilities(self.engine, "navigate", Capability.NAVIGATION)
            return self.engine.navigate(url, hard=hard)

    def open(self, route: str, intent: str | None = None) -> str:
        """Open a route the fastest correct way: the app's own router when the
        application is mounted on this origin, a document load otherwise (the first
        navigation, another origin, a route outside ``base_url``).

        Returns ``"navigate"`` or ``"goto"``, and the step's ``step.end`` records it as
        ``navigation``. Client-side navigation keeps mounted state: a case about a
        first load uses ``goto``.
        """
        with self.step(intent or f"open {route}"):
            require_capabilities(self.engine, "open", Capability.NAVIGATION)
            opener = getattr(self.engine, "open", None)
            if callable(opener):
                path = str(opener(route))
            else:  # engines written before open(): a document load, said so
                self.engine.goto(route)
                path = "goto"
            self._annotations[-1]["navigation"] = path
            return path

    def click(self, target: Target, intent: str | None = None, *, fast: bool = False) -> None:
        """Click. ``fast=True`` drops the actionability checks — see Engine.click.

        Worth it in a loop over rows that a readiness wait has already proved are
        rendered; never worth it on the first interaction with a screen, where the
        checks are the only thing that reports an overlay swallowing the click.
        """
        weakening = ("fast-actionability",) if fast else ()
        operation = self._operation("click")
        with self.step(
            intent or f"click {target.describe()}",
            target,
            weakenings=weakening,
            _operation=operation,
        ):
            require_capabilities(self.engine, "click", Capability.DOM)
            operation.invoke(self.engine.click, target, fast=fast)

    def fill(
        self, target: Target, value: str, intent: str | None = None, *, fast: bool = False
    ) -> None:
        """Fill a control, preserving application input events.

        ``fast=True`` skips actionability checks only. Use it for repeated fields
        after a readiness assertion, never as a way around a disabled or covered
        control.
        """
        weakening = ("fast-actionability",) if fast else ()
        operation = self._operation("fill")
        with self.step(
            intent or f"fill {target.describe()}",
            target,
            weakenings=weakening,
            _operation=operation,
        ):
            require_capabilities(self.engine, "fill", Capability.DOM)
            if fast:
                operation.invoke(self.engine.fill, target, value, fast=True)
            else:
                # Keep the default call compatible with existing Engine adapters
                # whose pre-fast signature accepted only target and value.
                operation.invoke(self.engine.fill, target, value)

    def select(
        self,
        target: Target,
        value: str | None = None,
        intent: str | None = None,
        *,
        label: str | None = None,
    ) -> None:
        """Choose an option by its ``value`` attribute, or by the ``label`` people read."""
        if (value is None) == (label is None):
            raise ValueError("select takes exactly one of value or label=")
        shown = repr(value) if value is not None else f"label {label!r}"
        with self.step(intent or f"select {shown} in {target.describe()}", target):
            require_capabilities(self.engine, "select", Capability.DOM)
            if label is not None:
                self._engine_method("select_label")(target, label)
            else:
                self.engine.select(target, str(value))

    def press(self, key: str, target: Target | None = None, intent: str | None = None) -> None:
        """Press a key (``"Enter"``, ``"Control+A"``), on ``target`` when given.

        With a target the control is focused first, so the key lands where the test
        says rather than wherever focus happens to be.
        """
        where = f" in {target.describe()}" if target is not None else ""
        with self.step(intent or f"press {key}{where}", target):
            if target is not None:
                require_capabilities(self.engine, "press", Capability.DOM, Capability.KEYBOARD)
                self.engine.focus(target)
            else:
                require_capabilities(self.engine, "press", Capability.KEYBOARD)
            self.engine.press(key)

    def check(self, target: Target, intent: str | None = None) -> None:
        with self.step(intent or f"check {target.describe()}", target):
            require_capabilities(self.engine, "check", Capability.DOM)
            self._engine_method("set_checked")(target, True)

    def uncheck(self, target: Target, intent: str | None = None) -> None:
        with self.step(intent or f"uncheck {target.describe()}", target):
            require_capabilities(self.engine, "uncheck", Capability.DOM)
            self._engine_method("set_checked")(target, False)

    def hover(self, target: Target, intent: str | None = None) -> None:
        with self.step(intent or f"hover {target.describe()}", target):
            require_capabilities(self.engine, "hover", Capability.DOM)
            self._engine_method("hover")(target)

    def drag(self, source: Target, destination: Target, intent: str | None = None) -> None:
        """Drag ``source`` onto ``destination``: a sortable list, a kanban card, a
        drop zone. The step's fingerprint is the source's, the element that moves."""
        described = f"drag {source.describe()} to {destination.describe()}"
        with self.step(intent or described, source, destination=destination):
            require_capabilities(self.engine, "drag", Capability.DOM)
            self._engine_method("drag")(source, destination)

    def expect_text(
        self, target: Target, text: str, intent: str | None = None, *, exact: bool = True
    ) -> None:
        with self.step(intent or f"expect {text!r} at {target.describe()}", target, check=True):
            require_capabilities(self.engine, "expect_text", Capability.DOM)
            self.engine.expect_text(target, text, exact=exact)

    def expect_visible(
        self,
        target: Target,
        intent: str | None = None,
        *,
        assertion_id: str | None = None,
        claim_id: str | None = None,
    ) -> None:
        """Assert visibility, optionally binding the observed result to a UI claim."""
        from testence.oracle import _assertion_identity, _emit_assertion, _source_location

        bound = _assertion_identity(assertion_id, claim_id)
        source = _source_location()
        with self.step(intent or f"expect {target.describe()} visible", target, check=True):
            require_capabilities(self.engine, "expect_visible", Capability.DOM)
            try:
                self.engine.expect_visible(target)
            except Exception as exc:
                if bound:
                    # A browser/transport failure is not proof that the UI claim
                    # is false. Only a completed visibility wait can violate it.
                    _emit_assertion(
                        self.writer,
                        self.test_id,
                        assertion_id=str(assertion_id),
                        claim_id=str(claim_id),
                        oracle_kind="ui",
                        expected={"visible": True, "target": target.describe()},
                        actual={"error": str(exc)},
                        diffs=[],
                        source=source,
                        outcome="failed" if isinstance(exc, AssertionError) else "inconclusive",
                    )
                raise
            if bound:
                _emit_assertion(
                    self.writer,
                    self.test_id,
                    assertion_id=str(assertion_id),
                    claim_id=str(claim_id),
                    oracle_kind="ui",
                    expected={"visible": True, "target": target.describe()},
                    actual={"visible": True, "target": target.describe()},
                    diffs=[],
                    source=source,
                )

    def expect_hidden(self, target: Target, intent: str | None = None) -> None:
        with self.step(
            intent or f"expect {target.describe()} gone", target, check=True, _absence=True
        ):
            require_capabilities(self.engine, "expect_hidden", Capability.DOM)
            method = getattr(self.engine, "expect_hidden", None)
            if callable(method):
                method(target)
            else:  # engines written before expect_hidden: a wait, reported as before
                self.engine.wait_while_visible(target)

    def reset_storage(
        self, keys: list[str] | tuple[str, ...], intent: str | None = None, *, session: bool = False
    ) -> int:
        """Remove the named keys from the page's ``localStorage`` (``sessionStorage``
        with ``session=True``); returns how many were set. For a page shared with the
        previous test (``page_reuse: module``): clear what that test left behind and
        this test must not read, such as a saved filter or a draft."""
        names = [str(key) for key in keys]
        if not names:
            raise ValueError("reset_storage needs at least one key")
        area = "sessionStorage" if session else "localStorage"
        with self.step(intent or f"reset {area} {', '.join(names)}"):
            require_capabilities(self.engine, "reset_storage", Capability.SESSION)
            return int(self._engine_method("remove_storage_items")(names, session=session))

    def expect_settled(
        self, target: Target, intent: str | None = None, *, timeout_ms: int | None = None
    ) -> None:
        """Wait until the target has stopped moving: the same box two frames running,
        wholly inside the viewport. Use it before reading the geometry of anything that
        animates in (a drawer, a sliding panel), whose size mid-transition is not the
        size it keeps."""
        with self.step(intent or f"expect {target.describe()} settled", target, check=True):
            require_capabilities(self.engine, "expect_settled", Capability.DOM)
            self._engine_method("expect_settled")(target, timeout_ms=timeout_ms)

    # -- readers ------------------------------------------------------------------
    #
    # A reader returns what the page shows to the test, which then asserts on it.
    # The step adds the read's size to the ledger, not its value: text on a page can
    # be a secret. (The element's fingerprint, taken after every green step with a
    # target, keeps its first 80 characters, redacted like all evidence.) Unlike
    # ``ex.native`` a reader leaves the page fit to hand on to the next test
    # (``page_reuse: module``).

    def _read(self, **size: Any) -> None:
        self._annotations[-1]["read"] = size

    def text(self, target: Target, intent: str | None = None) -> str:
        """The visible text of the one element ``target`` matches, once it exists.

        Two matches fail the step, naming both: a reader is as strict as a click.
        """
        with self.step(intent or f"read the text of {target.describe()}", target):
            require_capabilities(self.engine, "text", Capability.DOM)
            value = str(self.engine.read_text(target))
            self._read(chars=len(value))
            return value

    def texts(self, target: Target, intent: str | None = None, *, minimum: int = 1) -> list[str]:
        """The texts of every element ``target`` matches, in document order.

        Waits until at least ``minimum`` elements exist, so a list read right after a
        navigation is not read empty. ``minimum=0`` reads what is there now, which may
        be nothing.
        """
        _check_minimum("texts", minimum)
        with self.step(
            intent or f"read the texts of {target.describe()}", target, _absence=minimum == 0
        ):
            require_capabilities(self.engine, "texts", Capability.DOM)
            if minimum:
                self.engine.wait_for_count(target, minimum)
            values = [str(value) for value in self.engine.read_all_texts(target)]
            self._read(items=len(values), chars=sum(len(value) for value in values))
            return values

    def count(self, target: Target, intent: str | None = None) -> int:
        """How many elements ``target`` matches now. No waiting: to wait for a
        number, use ``expect_count``."""
        with self.step(intent or f"count {target.describe()}", target, _absence=True):
            require_capabilities(self.engine, "count", Capability.DOM)
            found = int(self.engine.count(target))
            self._read(items=found)
            return found

    def is_visible(self, target: Target, intent: str | None = None) -> bool:
        """Whether the element is visible now, without waiting for it either way.

        For a branch the product really has (a banner that may or may not be shown);
        a check that the element appears or goes is ``expect_visible`` or
        ``expect_hidden``.
        """
        with self.step(intent or f"is {target.describe()} visible", target, _absence=True):
            require_capabilities(self.engine, "is_visible", Capability.DOM)
            visible = bool(self._engine_method("is_visible")(target))
            self._read(visible=visible)
            return visible

    def attribute(self, target: Target, name: str, intent: str | None = None) -> str | None:
        """The attribute ``name`` of the one element ``target`` matches, or None."""
        with self.step(intent or f"read [{name}] of {target.describe()}", target):
            require_capabilities(self.engine, "attribute", Capability.DOM)
            value = self._engine_method("read_attribute")(target, name)
            self._read(chars=len(value) if value is not None else None)
            return None if value is None else str(value)

    def box(self, target: Target, intent: str | None = None, *, settled: bool = False) -> Box:
        """Where the element is drawn, once it is visible.

        ``settled=True`` first waits until it has stopped moving (``expect_settled``):
        a panel that slides in has its final width only at the end of the slide.
        """
        with self.step(intent or f"measure {target.describe()}", target):
            require_capabilities(self.engine, "box", Capability.DOM)
            if settled:
                self._engine_method("expect_settled")(target, timeout_ms=None)
            box = Box.of(self._engine_method("bounding_box")(target))
            self._read(width=round(box.width, 1), height=round(box.height, 1))
            return box

    def boxes(self, target: Target, intent: str | None = None, *, minimum: int = 1) -> list[Box]:
        """Where every visible element ``target`` matches is drawn, in document order:
        the headers of a table, the cards of a board."""
        _check_minimum("boxes", minimum)
        with self.step(
            intent or f"measure every {target.describe()}", target, _absence=minimum == 0
        ):
            require_capabilities(self.engine, "boxes", Capability.DOM)
            if minimum:
                self.engine.wait_for_count(target, minimum)
            found = [Box.of(box) for box in self._engine_method("bounding_boxes")(target)]
            self._read(items=len(found))
            return found

    def url(self, intent: str | None = None) -> str:
        """The address of the current page. To wait for one, use ``expect_url``."""
        with self.step(intent or "read the page address"):
            require_capabilities(self.engine, "url", Capability.NAVIGATION)
            return str(self.engine.current_url())

    def storage_item(
        self, key: str, intent: str | None = None, *, session: bool = False
    ) -> str | None:
        """One value of the page's ``localStorage`` (``sessionStorage`` with
        ``session=True``), or None when it is not set."""
        area = "sessionStorage" if session else "localStorage"
        with self.step(intent or f"read {area} {key}"):
            require_capabilities(self.engine, "storage_item", Capability.SESSION)
            value = self._engine_method("storage_item")(key, session=session)
            self._read(chars=len(value) if value is not None else None)
            return None if value is None else str(value)

    def read_js(self, intent: str, function: str, arg: Any = None) -> Any:
        """Call a JavaScript function that reads the page, and return its result.

        ``ex.read_js("read the stored widths", "key => JSON.parse(localStorage[key])",
        "widths")``. For what no reader above expresses: a computed style, a value
        the product keeps in a global. It is one recorded step and, unlike
        ``ex.native``, does not stop the page from being handed to the next test:
        the function must only read. Anything that acts on the page belongs in an
        action or in ``ex.native``.
        """
        if not isinstance(intent, str) or not intent.strip():
            raise ValueError("ex.read_js needs an intent saying what the function reads")
        if not isinstance(function, str) or not function.strip():
            raise ValueError("ex.read_js needs the JavaScript function as a string")
        with self.step(intent):
            require_capabilities(self.engine, "read_js", Capability.JAVASCRIPT)
            result = self._engine_method("evaluate")(function, arg)
            self._read(type=type(result).__name__)
            return result

    # -- state assertions --------------------------------------------------------
    #
    # Exact by default, like expect_text. A state that never holds is a failed
    # assertion (AssertionError), which reports file as ``failed``.

    def input_value(self, target: Target, intent: str | None = None) -> str:
        """Read a field once. Use expect_value first when waiting for an app suggestion.

        The value is returned to test code, never included in the step ledger.
        """
        with self.step(intent or f"read value of {target.describe()}", target):
            return self.engine.input_value(target)

    def expect_value(self, target: Target, value: str, intent: str | None = None) -> None:
        """A form control holds exactly ``value`` (inputs have no text to match)."""
        with self.step(
            intent or f"expect {target.describe()} to hold {value!r}", target, check=True
        ):
            require_capabilities(self.engine, "expect_value", Capability.DOM)
            self._engine_method("expect_value")(target, value)

    def expect_count(self, target: Target, count: int, intent: str | None = None) -> None:
        with self.step(
            intent or f"expect {count} of {target.describe()}",
            target,
            check=True,
            _absence=count == 0,
        ):
            require_capabilities(self.engine, "expect_count", Capability.DOM)
            self._engine_method("expect_count")(target, count)

    def expect_enabled(self, target: Target, intent: str | None = None) -> None:
        with self.step(intent or f"expect {target.describe()} enabled", target, check=True):
            require_capabilities(self.engine, "expect_enabled", Capability.DOM)
            self._engine_method("expect_enabled")(target, True)

    def expect_disabled(self, target: Target, intent: str | None = None) -> None:
        with self.step(intent or f"expect {target.describe()} disabled", target, check=True):
            require_capabilities(self.engine, "expect_disabled", Capability.DOM)
            self._engine_method("expect_enabled")(target, False)

    def expect_checked(
        self, target: Target, intent: str | None = None, *, checked: bool = True
    ) -> None:
        state = "checked" if checked else "unchecked"
        with self.step(intent or f"expect {target.describe()} {state}", target, check=True):
            require_capabilities(self.engine, "expect_checked", Capability.DOM)
            self._engine_method("expect_checked")(target, checked)

    def expect_attribute(
        self, target: Target, name: str, value: str, intent: str | None = None
    ) -> None:
        with self.step(
            intent or f"expect {target.describe()} [{name}] == {value!r}", target, check=True
        ):
            require_capabilities(self.engine, "expect_attribute", Capability.DOM)
            self._engine_method("expect_attribute")(target, name, value)

    def expect_url(
        self,
        *,
        contains: str | None = None,
        equals: str | None = None,
        intent: str | None = None,
    ) -> None:
        """The page URL contains ``contains``, or equals ``equals`` (relative to base_url)."""
        if (contains is None) == (equals is None):
            raise ValueError("expect_url takes exactly one of contains= or equals=")
        shown = f"to contain {contains!r}" if contains is not None else f"to be {equals!r}"
        with self.step(intent or f"expect the URL {shown}", check=True):
            require_capabilities(self.engine, "expect_url", Capability.NAVIGATION)
            self._engine_method("expect_url")(contains=contains, equals=equals)

    def expect_screenshot(
        self,
        baseline: str,
        *,
        baseline_digest: str,
        assertion_id: str,
        claim_id: str,
        intent: str = "Viewport matches the accepted visual baseline",
    ) -> dict[str, Any]:
        """Bound visual UI assertion; unusable evidence is inconclusive, never green."""
        from pathlib import Path

        from testence.oracle import _emit_assertion, _source_location
        from testence.visual import compare_baseline

        source = _source_location()
        expected = {"baseline_digest": baseline_digest}
        with self.step(intent, check=True):
            try:
                result = compare_baseline(
                    self.engine,
                    Path(baseline),
                    self.writer.test_dir(self.test_id) / "pack",
                    baseline_digest=baseline_digest,
                )
            except Exception as exc:
                _emit_assertion(
                    self.writer,
                    self.test_id,
                    assertion_id=assertion_id,
                    claim_id=claim_id,
                    oracle_kind="ui",
                    expected=expected,
                    actual={"error": str(exc)},
                    diffs=[],
                    source=source,
                    outcome="inconclusive",
                )
                raise
            _emit_assertion(
                self.writer,
                self.test_id,
                assertion_id=assertion_id,
                claim_id=claim_id,
                oracle_kind="ui",
                expected=expected,
                actual=result,
                diffs=[]
                if result["outcome"] == "passed"
                else [{"field": "viewport", "visual": result}],
                source=source,
                outcome=result["outcome"],
            )
            if result["outcome"] != "passed":
                raise AssertionError(f"visual mismatch: {result['changed_pixels']} pixels changed")
            return result

    def focus(self, target: Target, intent: str | None = None) -> None:
        with self.step(intent or f"focus {target.describe()}", target):
            require_capabilities(self.engine, "focus", Capability.DOM, Capability.KEYBOARD)
            self.engine.focus(target)

    def scroll_into_view(self, target: Target, intent: str | None = None) -> None:
        with self.step(intent or f"scroll to {target.describe()}", target):
            require_capabilities(self.engine, "scroll_into_view", Capability.DOM)
            self.engine.scroll_into_view(target)

    def upload(self, target: Target, paths: list[str], intent: str | None = None) -> None:
        with self.step(intent or f"upload file through {target.describe()}", target):
            require_capabilities(self.engine, "upload", Capability.DOM, Capability.FILES)
            self.engine.upload(target, paths)

    def download(self, target: Target, path: str, intent: str | None = None) -> str:
        with self.step(intent or f"download from {target.describe()}", target):
            require_capabilities(self.engine, "download", Capability.DOM, Capability.FILES)
            return self.engine.click_and_download(target, path)

    def popup(self, target: Target, intent: str | None = None) -> None:
        with self.step(intent or f"open popup from {target.describe()}", target):
            require_capabilities(self.engine, "popup", Capability.DOM, Capability.POPUPS)
            self.engine.click_and_popup(target)

    def dialog(
        self,
        target: Target,
        intent: str | None = None,
        *,
        accept: bool = True,
        prompt: str | None = None,
    ) -> str:
        with self.step(intent or f"handle dialog from {target.describe()}", target):
            require_capabilities(self.engine, "dialog", Capability.DOM, Capability.DIALOGS)
            return self.engine.click_with_dialog(target, accept=accept, prompt=prompt)

    @contextmanager
    def frame(self, target: Target, intent: str | None = None) -> Iterator[None]:
        with self.step(intent or f"enter frame {target.describe()}", target):
            require_capabilities(self.engine, "frame", Capability.DOM, Capability.FRAMES)
            with self.engine.frame(target):
                yield

    @contextmanager
    def soft(self, intent: str) -> Iterator[None]:
        """Run every check in the block, then fail once listing the ones that failed.

        ``with ex.soft("the order summary"):`` suits a screen of independent facts —
        totals, badges, labels — where the first wrong one should not hide the rest.
        Each failed check is still its own failed step in the ledger (marked
        ``soft``). Actions, unavailable engines and browser errors are not softened:
        they stop the test at once, as outside the block. Blocks do not nest.
        """
        if not isinstance(intent, str) or not intent.strip():
            raise ValueError("ex.soft needs an intent naming what the checks describe")
        if self._soft is not None:
            raise RuntimeError("ex.soft blocks do not nest")
        with self.step(intent):
            self._soft = []
            try:
                yield
            finally:
                failures, self._soft = self._soft, None
            if failures:
                raise SoftAssertionsFailed(intent, failures)

    def switch_page(
        self,
        index: int | None = None,
        intent: str | None = None,
        *,
        url_contains: str | None = None,
    ) -> None:
        """Continue on another open page (tab): by position, or by part of its URL.

        ``url_contains`` waits for a tab the application is still opening.
        """
        if (index is None) == (url_contains is None):
            raise ValueError("switch_page takes exactly one of index or url_contains=")
        shown = f"page {index}" if index is not None else f"the page at {url_contains!r}"
        with self.step(intent or f"switch to {shown}"):
            require_capabilities(self.engine, "switch_page", Capability.POPUPS)
            if index is not None:
                self.engine.switch_page(index)
            else:
                self._engine_method("switch_page_matching")(url_contains)

    def close_page(self, intent: str | None = None) -> None:
        """Close the current page and continue on the most recently opened one left."""
        with self.step(intent or "close the current page"):
            require_capabilities(self.engine, "close_page", Capability.POPUPS)
            self._engine_method("close_page")()

    @property
    def clock(self) -> Clock:
        """Fake time for the page: ``ex.clock.install(...)``, ``fast_forward``, ..."""
        return Clock(self)

    @contextmanager
    def native(self, intent: str) -> Iterator[Any]:
        """Hand the engine's own page object to code the DSL does not express.

        ``with ex.native("sign on the pad") as page: page.mouse...`` runs as one
        recorded step: its intent, duration and failure land in the ledger like any
        other, and a ``native.used`` event marks that the interactions inside were not
        recorded one by one. Healing is not proposed for a failure inside, because no
        target was addressed through the DSL. An engine without the ``browser.native``
        capability refuses before the block runs (ADR-0027).
        """
        if not isinstance(intent, str) or not intent.strip():
            raise ValueError("ex.native needs an intent saying what the native code does")
        with self.step(intent):
            require_capabilities(self.engine, "native", Capability.NATIVE)
            provider = getattr(self.engine, "native_page", None)
            if not callable(provider):
                raise UnsupportedCapability(
                    "native",
                    {Capability.NATIVE.value},
                    set(engine_capabilities(self.engine)) - {Capability.NATIVE.value},
                )
            self.writer.emit("native.used", test=self.test_id, intent=intent)
            yield provider()

    def verify(
        self,
        name: str,
        expected: dict[str, Any],
        actual: dict[str, Any],
        *,
        assertion_id: str | None = None,
        claim_id: str | None = None,
        oracle_kind: str = "api",
    ) -> None:
        """Compare two semantic views and optionally satisfy a PlanSpec assertion."""

        from testence.oracle import _source_location, verify

        verify(
            self.writer,
            self.test_id,
            name,
            expected,
            actual,
            assertion_id=assertion_id,
            claim_id=claim_id,
            oracle_kind=oracle_kind,
            source=_source_location(),
        )

    def verify_state(
        self,
        name: str,
        read: Callable[[], Response],
        expected: ExpectedState,
        *,
        deadline_ms: int = 3_000,
        poll_ms: int = 100,
        assertion_id: str | None = None,
        claim_id: str | None = None,
    ) -> OracleObservation:
        """Poll a fresh authoritative read until the declared state is stable."""

        from testence.oracle import _source_location, verify_expected_state

        return verify_expected_state(
            self.writer,
            self.test_id,
            name,
            read,
            expected,
            deadline_ms=deadline_ms,
            poll_ms=poll_ms,
            assertion_id=assertion_id,
            claim_id=claim_id,
            source=_source_location(),
        )

    def settle(self, timeout_ms: int = 1_500) -> bool:
        """Wait for in-flight requests. Not a step: it records nothing and asserts
        nothing, it just stops the test from reading a half-loaded page."""
        require_capabilities(self.engine, "settle", Capability.NETWORK)
        return self.engine.settle(timeout_ms)

    def attach(
        self,
        name: str,
        data: bytes | str | Path,
        *,
        media_type: str | None = None,
    ) -> None:
        """Keep a file with this test's evidence and ship it in every export.

        A payload the test built, a server log excerpt, a picture: ``data`` is text,
        bytes or a path. Text is redacted like all evidence; a binary file cannot be
        and is stored as given (``redaction: none``), so only a ``full`` export carries
        it. ``media_type`` defaults from the name's extension.
        """
        content = data.read_bytes() if isinstance(data, Path) else data
        self.writer.attach(self.test_id, name, content, media_type)

    @contextmanager
    def expect_request(
        self,
        request: str | Any,
        *,
        method: str | None = None,
        timeout_ms: int = 3_000,
        intent: str | None = None,
    ) -> Iterator[ExpectedRequest]:
        """The request this block causes, and its response.

        ``with ex.expect_request("/api/widgets", method="POST") as sent: ex.click(SAVE)``
        marks the network log before the block, runs it, then waits for the completed
        response that belongs to it (an earlier list or save cannot satisfy it). Read
        the outcome from ``sent.record`` after the block: ``sent.record.status``,
        ``sent.record.json_body()``, ``sent.record.mocked``. A request that was never
        sent, or was cut off before a response, fails the block rather than passing
        silently. ``request`` is a URL fragment or a ``RequestExpectation`` (method,
        origin, correlation id, GraphQL operation), which also fixes the method.
        """
        from testence.oracle import RequestExpectation

        require_capabilities(self.engine, "expect_request", Capability.NETWORK)
        verb: str | None
        predicate: Callable[[NetRecord], bool] | None
        if isinstance(request, RequestExpectation):
            fragment, verb, predicate = request.path, request.method, request.matches
        else:
            fragment, verb, predicate = str(request), method, None
        label = f"{verb + ' ' if verb else ''}{fragment}"
        holder = ExpectedRequest(label)
        with self.step(intent or f"the block sends {label}"):
            mark = self.engine.net_mark()
            yield holder
            record = self.engine.wait_for_response(
                fragment, method=verb, since=mark, timeout_ms=timeout_ms, predicate=predicate
            )
            holder.record = record
            if record is not None:
                return
            sent = self.engine.wait_for_request(fragment, method=verb, since=mark, timeout_ms=1)
            if sent:
                raise AssertionError(
                    f"{label} was sent but no response arrived within {timeout_ms} ms "
                    "(aborted by the page, or slow): the server may have applied it, "
                    "ask an oracle"
                )
            raise AssertionError(
                f"the block sent no request matching {label}: the UI accepted the "
                "action but nothing reached the server"
            )

    @contextmanager
    def expect_outcome(
        self,
        outcomes: dict[str, Target],
        *,
        expected: str | None = None,
        timeout_ms: int = 3_000,
        intent: str | None = None,
    ) -> Iterator[ExpectedOutcome]:
        """Send the action once, then observe one declared UI result within a deadline.

        Existing visible results and conflicting results fail explicitly. No result
        means unobserved, not evidence of silent rejection.
        """
        if not outcomes or not all(
            isinstance(k, str) and k and isinstance(v, Target) for k, v in outcomes.items()
        ):
            raise ValueError("outcomes must map non-empty names to Targets")
        if type(timeout_ms) is not int or timeout_ms <= 0:
            raise ValueError("timeout_ms must be a positive integer")
        if expected is not None and expected not in outcomes:
            raise ValueError("expected outcome must be declared")
        outcomes = dict(outcomes)
        holder = ExpectedOutcome()
        with self.step(intent or "observe the action's UI outcome"):
            existing = self.engine.visible_outcomes(outcomes)
            if existing:
                raise AssertionError(f"outcomes already visible before the action: {existing}")
            yield holder
            holder.name = self.engine.wait_for_outcome(outcomes, timeout_ms)
            self.writer.emit(
                "note", test=self.test_id, text="UI outcome observed", outcome=holder.name
            )
            if expected is not None and holder.name != expected:
                raise AssertionError(f"expected outcome {expected!r}, observed {holder.name!r}")

    def rewrite_response(
        self,
        pattern: str,
        transform: Callable[[Any], Any],
        *,
        method: str | None = None,
        intent: str | None = None,
    ) -> None:
        """Adapt a JSON response after the original browser request is sent once.

        Chromium/CDP only. Responses are mocked evidence, never proof of persistence.
        """
        rewrite = getattr(self.engine, "rewrite_response", None)
        if not callable(rewrite):
            raise UnsupportedCapability("rewrite_response", {"browser.response-rewrite"}, set())
        require_capabilities(self.engine, "rewrite_response", Capability.RESPONSE_REWRITE)
        with self.step(intent or f"adapt JSON responses for {pattern}"):
            rewrite(pattern, transform, method=method)

    def route(
        self,
        pattern: str,
        *,
        status: int = 200,
        json: Any = _UNSET,
        body: str | bytes | None = None,
        headers: dict[str, str] | None = None,
        content_type: str | None = None,
        abort: bool = False,
        intent: str | None = None,
    ) -> None:
        """Answer requests matching ``pattern`` (a URL glob such as ``**/api/widgets*``)
        from the test: a canned ``json`` or ``body`` with ``status``, or ``abort=True``
        to drop the connection.

        Recorded as a ``network.mocked`` event, and every response it produces is marked
        ``mocked``: it never reached the server, so ``save_and_verify_state`` refuses to
        take it for the mutation. Use it for the UI's behaviour on an error, an empty
        list or a slow answer; prove persistence against the real backend.
        """
        if abort and (json is not _UNSET or body is not None):
            raise ValueError("ex.route: abort has no response body")
        if json is not _UNSET and body is not None:
            raise ValueError("ex.route: give json or body, not both")
        payload: str | bytes | None = body
        kind = content_type
        if json is not _UNSET:
            import json as _json

            payload = _json.dumps(json)
            kind = kind or "application/json"
        outcome = "abort" if abort else str(status)
        with self.step(intent or f"answer {pattern} from the test ({outcome})"):
            require_capabilities(self.engine, "route", Capability.NETWORK_MOCK)
            self.writer.emit(
                "network.mocked",
                test=self.test_id,
                pattern=pattern,
                outcome=outcome,
                content_type=kind,
                size=len(payload) if payload is not None else 0,
            )
            self.engine.route(
                pattern,
                status=status,
                body=payload,
                headers=headers,
                content_type=kind,
                abort=abort,
            )

    def ws_gate(
        self,
        pattern: str | re.Pattern[str],
        *,
        protocol: str = "socket.io",
        drop: Callable[[Any], bool] | None = None,
        offline: bool = False,
        intent: str | None = None,
    ) -> WebSocketGate:
        """Gate the WebSockets matching ``pattern`` so this tab can miss server pushes.

        ``pattern`` is a URL glob (``**/socket.io/**``) or a compiled regex. Install it
        before the page connects: a gate applies only to sockets opened after it, and
        one installed over an open socket fails. The gate covers every page of the
        session. Client frames always pass; server frames pass until
        ``gate.go_offline()``. Offline, ``protocol="socket.io"`` holds back event
        packets and keeps pings, pongs and acknowledgements flowing, so the socket
        stays open and the tab goes stale; ``"raw"`` holds back every server frame;
        ``drop`` replaces the rule with a predicate over one frame.

        A held frame never reaches ``wait_for_ws``. Each change of state is a step and a
        ``websocket.gated`` event. What the UI shows while offline is its behaviour on
        stale data; the server's state still needs an independent read (ADR-0035).
        """
        gate_factory = getattr(self.engine, "ws_gate", None)
        if not callable(gate_factory):
            raise UnsupportedCapability(
                "ws_gate",
                {Capability.WEBSOCKET_MOCK.value},
                set(engine_capabilities(self.engine)) - {Capability.WEBSOCKET_MOCK.value},
            )
        label = pattern.pattern if isinstance(pattern, re.Pattern) else pattern
        state = "offline" if offline else "online"
        with self.step(intent or f"gate the WebSockets at {label} ({protocol}, {state})"):
            require_capabilities(self.engine, "ws_gate", Capability.WEBSOCKET_MOCK)
            engine_gate = gate_factory(pattern, protocol=protocol, drop=drop, offline=offline)
            self.writer.emit(
                "websocket.gated",
                test=self.test_id,
                action="installed",
                pattern=engine_gate.label,
                protocol=protocol,
                custom_drop=drop is not None,
                offline=offline,
            )
        gate = WebSocketGate(self, engine_gate)
        self._ws_gates.append(gate)
        return gate

    def _finish_ws_gates(self) -> None:
        """Summarize every gate of this test in the ledger, once, at its end."""
        gates, self._ws_gates = self._ws_gates, []
        for gate in gates:
            self.writer.emit(
                "websocket.gated",
                test=self.test_id,
                action="summary",
                **gate.engine_gate.summary(),
            )

    def note(self, text: str, **data: Any) -> None:
        self.writer.emit("note", test=self.test_id, text=text, **data)


class WebSocketGate:
    """The handle ``ex.ws_gate`` returns: switch the gate, read its counters.

    ``go_offline()`` and ``go_online()`` are recorded steps. Before switching, each
    makes one round trip to the browser, so frames already waiting are decided under
    the state they arrived in: the sync driver runs the gate only while the test is
    inside a browser call, and a frame the server pushed while the test was busy
    with its own HTTP client is still queued. ``drain_ms`` waits longer for frames
    still on the network; choose it from the product's push latency.
    """

    def __init__(self, actions: Actions, engine_gate: Any) -> None:
        self._actions = actions
        self.engine_gate = engine_gate

    @property
    def pattern(self) -> str:
        return str(self.engine_gate.label)

    @property
    def is_offline(self) -> bool:
        return bool(self.engine_gate.offline)

    @property
    def dropped(self) -> int:
        """Server frames held back so far."""
        return int(self.engine_gate.dropped)

    @property
    def delivered(self) -> int:
        """Server frames that reached the page so far."""
        return int(self.engine_gate.delivered)

    def go_offline(self, intent: str | None = None, *, drain_ms: int = 0) -> None:
        """Start holding back server frames; the socket stays open."""
        actions = self._actions
        with actions.step(intent or f"hold back server frames of {self.pattern}"):
            self.engine_gate.set_offline(True, drain_ms)
            actions.writer.emit(
                "websocket.gated",
                test=actions.test_id,
                action="offline",
                pattern=self.pattern,
                drain_ms=drain_ms,
            )

    def go_online(self, intent: str | None = None, *, drain_ms: int = 0) -> int:
        """Deliver server frames again; return how many were held back while offline.

        Held frames are gone, as for a tab that missed them: the page only gets what
        the server sends from now on.
        """
        actions = self._actions
        with actions.step(intent or f"deliver server frames of {self.pattern} again"):
            held = int(self.engine_gate.set_offline(False, drain_ms))
            actions.writer.emit(
                "websocket.gated",
                test=actions.test_id,
                action="online",
                pattern=self.pattern,
                dropped=held,
                drain_ms=drain_ms,
            )
        return held


class Clock:
    """``ex.clock``: the page's fake timers, each call a recorded step.

    Install before the page reads the time (before ``goto`` for a page that renders
    it on load). ``run_for`` advances time and fires every timer on the way,
    including ones those timers schedule — a countdown of ``setTimeout(tick, 1000)``
    reaches zero. ``fast_forward`` jumps, like a laptop lid closed and opened: each
    due timer fires at most once, so a chain started during the jump does not finish
    until real time catches up. ``pause_at`` stops time at a moment; ``set_fixed_time`` pins ``Date.now()``
    while timers keep running. Times are Playwright's: an ISO string, a
    ``datetime`` or epoch milliseconds; ticks are milliseconds or ``"mm:ss"``.
    """

    def __init__(self, actions: Actions) -> None:
        self._actions = actions

    def _run(self, intent: str, operation: str, *args: Any) -> None:
        actions = self._actions
        with actions.step(intent):
            require_capabilities(actions.engine, operation, Capability.CLOCK)
            actions._engine_method(operation)(*args)

    def install(self, time: Any = None, intent: str | None = None) -> None:
        shown = f" at {time!r}" if time is not None else ""
        self._run(intent or f"install the clock{shown}", "clock_install", time)

    def fast_forward(self, ticks: int | str, intent: str | None = None) -> None:
        self._run(intent or f"fast-forward the clock by {ticks!r}", "clock_fast_forward", ticks)

    def run_for(self, ticks: int | str, intent: str | None = None) -> None:
        self._run(intent or f"run the clock for {ticks!r}", "clock_run_for", ticks)

    def pause_at(self, time: Any, intent: str | None = None) -> None:
        self._run(intent or f"pause the clock at {time!r}", "clock_pause_at", time)

    def resume(self, intent: str | None = None) -> None:
        self._run(intent or "resume the clock", "clock_resume")

    def set_fixed_time(self, time: Any, intent: str | None = None) -> None:
        self._run(intent or f"fix the time at {time!r}", "clock_set_fixed_time", time)
