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
from typing import Any, Iterator

from testence.engine import Engine, Target
from testence.evidence import EvidenceWriter
from testence.fingerprints import FingerprintStore


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
    def step(self, intent: str, target: Target | None = None) -> Iterator[None]:
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
            self.engine.goto(url)

    def navigate(self, url: str, intent: str | None = None, *, hard: bool = False) -> bool:
        """Reach a route the fast way (client-side routing) — see Engine.navigate.

        Prefer this over ``goto`` for in-app navigation: a full reload costs
        seconds per call, the app's router costs milliseconds. Use ``hard=True``
        only when the case is *about* a fresh page load.
        """
        with self.step(intent or f"go to {url}"):
            return self.engine.navigate(url, hard=hard)

    def click(self, target: Target, intent: str | None = None, *, fast: bool = False) -> None:
        """Click. ``fast=True`` drops the actionability checks — see Engine.click.

        Worth it in a loop over rows that a readiness wait has already proved are
        rendered; never worth it on the first interaction with a screen, where the
        checks are the only thing that reports an overlay swallowing the click.
        """
        with self.step(intent or f"click {target.describe()}", target):
            self.engine.click(target, fast=fast)

    def fill(
        self, target: Target, value: str, intent: str | None = None, *, fast: bool = False
    ) -> None:
        """Fill a control, preserving application input events.

        ``fast=True`` skips actionability checks only. Use it for repeated fields
        after a readiness assertion, never as a way around a disabled or covered
        control.
        """
        with self.step(intent or f"fill {target.describe()}", target):
            if fast:
                self.engine.fill(target, value, fast=True)
            else:
                # Keep the default call compatible with existing Engine adapters
                # whose pre-fast signature accepted only target and value.
                self.engine.fill(target, value)

    def select(self, target: Target, value: str, intent: str | None = None) -> None:
        with self.step(intent or f"select {value!r} in {target.describe()}", target):
            self.engine.select(target, value)

    def expect_text(
        self, target: Target, text: str, intent: str | None = None, *, exact: bool = True
    ) -> None:
        with self.step(intent or f"expect {text!r} at {target.describe()}", target):
            self.engine.expect_text(target, text, exact=exact)

    def expect_visible(self, target: Target, intent: str | None = None) -> None:
        with self.step(intent or f"expect {target.describe()} visible", target):
            self.engine.expect_visible(target)

    def expect_hidden(self, target: Target, intent: str | None = None) -> None:
        with self.step(intent or f"expect {target.describe()} gone", target):
            self.engine.wait_while_visible(target)

    def settle(self, timeout_ms: int = 1_500) -> bool:
        """Wait for in-flight requests. Not a step: it records nothing and asserts
        nothing, it just stops the test from reading a half-loaded page."""
        return self.engine.settle(timeout_ms)

    def note(self, text: str, **data: Any) -> None:
        self.writer.emit("note", test=self.test_id, text=text, **data)
