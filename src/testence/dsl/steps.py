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

    # -- core wrapper ------------------------------------------------------

    @contextmanager
    def step(
        self,
        intent: str,
        target: Target | None = None,
        *,
        weakenings: tuple[str, ...] = (),
    ) -> Iterator[None]:
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
            self.writer.emit(
                "step.end",
                test=self.test_id,
                step=step_id,
                status="fail",
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
                error=error,
                depth=depth,
                children=self._children.pop(),
            )
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

    def select(self, target: Target, value: str, intent: str | None = None) -> None:
        with self.step(intent or f"select {value!r} in {target.describe()}", target):
            require_capabilities(self.engine, "select", Capability.DOM)
            self.engine.select(target, value)

    def expect_text(
        self, target: Target, text: str, intent: str | None = None, *, exact: bool = True
    ) -> None:
        with self.step(intent or f"expect {text!r} at {target.describe()}", target):
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
        with self.step(intent or f"expect {target.describe()} visible", target):
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
        with self.step(intent or f"expect {target.describe()} gone", target):
            require_capabilities(self.engine, "expect_hidden", Capability.DOM)
            self.engine.wait_while_visible(target)

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
        with self.step(intent):
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
