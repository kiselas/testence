"""Step primitives: every action is logged with its *intent*.

The intent (a human sentence: "open the host panel", "save the subnet form") is not
decoration. It is (a) what a triage agent reads instead of replaying the run,
(b) the future cache key for AI-materialized steps (``ai_step`` escape hatch),
(c) what a heal-diff preserves when a locator drifts. Project ActionMaps compose
these primitives; test cases should read as 5–15 intent-bearing lines.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Iterator

from testence.engine import (
    Capability,
    Engine,
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
    def __init__(self, intent: str, cause: Exception, target: Target | None = None) -> None:
        super().__init__(f"step failed: {intent} ({cause.__class__.__name__}: {cause})")
        self.intent = intent
        self.cause = cause
        self.target = target


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


class Actions:
    """Engine + evidence, bound to one test. Projects build ActionMaps on top."""

    def __init__(
        self,
        engine: Engine,
        writer: EvidenceWriter,
        test_id: str,
        store: FingerprintStore | None = None,
    ) -> None:
        self.engine = engine
        self.writer = writer
        self.test_id = test_id
        self.store = store
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
        #: Failed checks collected by the open ``ex.soft`` block, if any.
        self._soft: list[StepFailure] | None = None

    # -- core wrapper ------------------------------------------------------

    @contextmanager
    def step(
        self,
        intent: str,
        target: Target | None = None,
        *,
        weakenings: tuple[str, ...] = (),
        check: bool = False,
    ) -> Iterator[None]:
        """One recorded step. ``check=True`` marks an assertion, which an open
        ``ex.soft`` block records and lets the test continue past."""
        self._step_no += 1
        step_id = f"s{self._step_no}"
        depth = len(self._children)
        if self._children:
            self._children[-1] += 1
        self._children.append(0)
        self.writer.emit(
            "step.start",
            test=self.test_id,
            step=step_id,
            intent=intent,
            target=target.describe() if target else None,
            weakenings=list(weakenings),
            depth=depth,
        )
        started = time.perf_counter()
        try:
            yield
        except Exception as exc:
            error = f"{exc.__class__.__name__}: {exc}"
            self.last_failure = StepFailure(intent=intent, target=target, error=error)
            # Only a completed check that disagreed is softened: an action that failed,
            # an unavailable engine or a broken browser still stops the test.
            softened = (
                check
                and self._soft is not None
                and isinstance(exc, AssertionError)
                and not isinstance(exc, UnsupportedCapability)
            )
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
            )
            if softened:
                assert self._soft is not None
                self._soft.append(self.last_failure)
                return
            if isinstance(exc, UnsupportedCapability):
                raise
            raise StepFailed(intent, exc, target) from exc
        fingerprint = self.engine.element_fingerprint(target) if target else None
        if fingerprint and target is not None and self.store is not None:
            # Remember what "working" looked like: the only baseline a heal
            # proposal can honestly be measured against.
            self.store.record(self.test_id, intent, target.describe(), fingerprint)
        self.writer.emit(
            "step.end",
            test=self.test_id,
            step=step_id,
            status="ok",
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
            fingerprint=fingerprint or None,
            depth=depth,
            children=self._children.pop(),
        )

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

    def click(self, target: Target, intent: str | None = None, *, fast: bool = False) -> None:
        """Click. ``fast=True`` drops the actionability checks — see Engine.click.

        Worth it in a loop over rows that a readiness wait has already proved are
        rendered; never worth it on the first interaction with a screen, where the
        checks are the only thing that reports an overlay swallowing the click.
        """
        weakening = ("fast-actionability",) if fast else ()
        with self.step(intent or f"click {target.describe()}", target, weakenings=weakening):
            require_capabilities(self.engine, "click", Capability.DOM)
            self.engine.click(target, fast=fast)

    def fill(
        self, target: Target, value: str, intent: str | None = None, *, fast: bool = False
    ) -> None:
        """Fill a control, preserving application input events.

        ``fast=True`` skips actionability checks only. Use it for repeated fields
        after a readiness assertion, never as a way around a disabled or covered
        control.
        """
        weakening = ("fast-actionability",) if fast else ()
        with self.step(intent or f"fill {target.describe()}", target, weakenings=weakening):
            require_capabilities(self.engine, "fill", Capability.DOM)
            if fast:
                self.engine.fill(target, value, fast=True)
            else:
                # Keep the default call compatible with existing Engine adapters
                # whose pre-fast signature accepted only target and value.
                self.engine.fill(target, value)

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
        with self.step(intent or f"expect {target.describe()} gone", target, check=True):
            require_capabilities(self.engine, "expect_hidden", Capability.DOM)
            method = getattr(self.engine, "expect_hidden", None)
            if callable(method):
                method(target)
            else:  # engines written before expect_hidden: a wait, reported as before
                self.engine.wait_while_visible(target)

    # -- state assertions --------------------------------------------------------
    #
    # Exact by default, like expect_text. A state that never holds is a failed
    # assertion (AssertionError), which reports file as ``failed``.

    def expect_value(self, target: Target, value: str, intent: str | None = None) -> None:
        """A form control holds exactly ``value`` (inputs have no text to match)."""
        with self.step(
            intent or f"expect {target.describe()} to hold {value!r}", target, check=True
        ):
            require_capabilities(self.engine, "expect_value", Capability.DOM)
            self._engine_method("expect_value")(target, value)

    def expect_count(self, target: Target, count: int, intent: str | None = None) -> None:
        with self.step(intent or f"expect {count} of {target.describe()}", target, check=True):
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

        ``with ex.native("drag the card to Done") as page: page.mouse...`` runs as one
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

    def note(self, text: str, **data: Any) -> None:
        self.writer.emit("note", test=self.test_id, text=text, **data)


class Clock:
    """``ex.clock``: the page's fake timers, each call a recorded step.

    Install before the page reads the time (before ``goto`` for a page that renders
    it on load). ``fast_forward`` runs the timers due in the interval;
    ``pause_at`` stops time at a moment; ``set_fixed_time`` pins ``Date.now()``
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

    def pause_at(self, time: Any, intent: str | None = None) -> None:
        self._run(intent or f"pause the clock at {time!r}", "clock_pause_at", time)

    def resume(self, intent: str | None = None) -> None:
        self._run(intent or "resume the clock", "clock_resume")

    def set_fixed_time(self, time: Any, intent: str | None = None) -> None:
        self._run(intent or f"fix the time at {time!r}", "clock_set_fixed_time", time)
