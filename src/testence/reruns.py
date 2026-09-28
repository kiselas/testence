"""Repeat a failed test: ``--testence-reruns N`` (``TESTENCE_RERUNS``).

Testence repeats the whole test — setup, call and teardown — never an interaction
inside it (AGENTS.md). Each attempt runs pytest's own protocol; the failed reports of
an attempt that is repeated are relabelled ``rerun``, which the lifecycle plugin
records as its own attempt with its own evidence, and a pass after a repeat is
reported as flaky rather than as a clean pass (``docs/en/reporting.md``).

Written here rather than taken from pytest-rerunfailures so that the runner depends
on permissively licensed packages only (ADR-0007). The plugin still recognises that
package's ``rerun`` reports, so a suite already using it keeps working.
"""

from __future__ import annotations

from typing import Any

import pytest
from _pytest.runner import call_and_report, runtestprotocol
from _pytest.skipping import xfailed_key

RERUNS_ENV = "TESTENCE_RERUNS"
#: More repeats than this hide a defect behind luck; a value above it is a typo.
MAX_RERUNS = 5


def rerun_count(config: pytest.Config) -> int:
    raw = config.getoption("--testence-reruns")
    try:
        count = int(raw or 0)
    except (TypeError, ValueError):
        raise pytest.UsageError(f"--testence-reruns must be an integer, not {raw!r}") from None
    if not 0 <= count <= MAX_RERUNS:
        raise pytest.UsageError(f"--testence-reruns must be between 0 and {MAX_RERUNS}")
    return count


def _forget_failures(item: pytest.Item) -> None:
    """Drop what the failed attempt cached, so the repeat really runs again.

    A fixture whose setup raised caches the exception, which the repeat would replay
    instead of trying again. A collector whose setup raised is torn down with the
    attempt (``Reruns.pytest_runtest_teardown``).
    """
    info = getattr(item, "_fixtureinfo", None)
    for definitions in getattr(info, "name2fixturedefs", {}).values():
        for definition in definitions:
            cached = getattr(definition, "cached_result", None)
            if cached is not None and len(cached) > 2 and cached[2] is not None:
                definition.cached_result = None
                # The failed setup registered its finalizers; pytest 9 refuses to
                # execute a fixture that still has some.
                finalizers = getattr(definition, "_finalizers", None)
                if isinstance(finalizers, list):
                    finalizers.clear()
    # A test method's instance is created once per item; the repeat must not see
    # what the failed attempt stored on ``self``. pytest 8.1+ keeps it in
    # ``_instance``; 8.0 takes it from the bound method cached in ``_obj``.
    if getattr(item, "cls", None) is not None:
        if hasattr(item, "_instance"):
            del item._instance  # type: ignore[attr-defined]
        item._obj = None  # type: ignore[attr-defined]


def _expected_to_fail(item: pytest.Item) -> bool:
    """An xfail that pytest evaluated for this attempt, strict XPASS included."""
    return bool(item.stash.get(xfailed_key, None)) and not item.config.getoption("runxfail")


def _attempt(item: pytest.Item, nextitem: pytest.Item | None, may_repeat: bool) -> list[Any]:
    """``runtestprotocol``, except where a failed attempt will be repeated.

    Its teardown then keeps the scopes around the test — the module, the class, the
    session fixtures — instead of tearing down what ``nextitem`` does not need: the
    repeat is the next test, and for the last test of a module those scopes held a
    module fixture that the repeat would otherwise set up a second time.
    """
    config = item.config
    if not may_repeat or config.getoption("setuponly") or config.getoption("setupshow"):
        return runtestprotocol(item, nextitem=nextitem, log=False)
    hasrequest = hasattr(item, "_request")
    if hasrequest and not item._request:  # type: ignore[attr-defined]
        item._initrequest()  # type: ignore[attr-defined]
    try:
        reports = [call_and_report(item, "setup", log=False)]
        if reports[0].passed:
            reports.append(call_and_report(item, "call", log=False))
        session = item.session
        if session.shouldfail or session.shouldstop:
            following = None
        elif any(report.failed for report in reports) and not _expected_to_fail(item):
            following = item  # read by Reruns.pytest_runtest_teardown
        else:
            following = nextitem
        reports.append(call_and_report(item, "teardown", log=False, nextitem=following))
    finally:
        if hasrequest:
            item._request = False  # type: ignore[attr-defined]
            item.funcargs = None  # type: ignore[attr-defined]
    return reports


class Reruns:
    """The pytest plugin object; registered only when reruns are requested."""

    def __init__(self, count: int) -> None:
        self.count = count

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_protocol(self, item: pytest.Item, nextitem: pytest.Item | None) -> bool:
        ihook = item.ihook
        for attempt in range(self.count + 1):
            ihook.pytest_runtest_logstart(nodeid=item.nodeid, location=item.location)
            reports = _attempt(item, nextitem, may_repeat=attempt < self.count)
            repeat = (
                attempt < self.count
                and any(report.failed for report in reports)
                and not item.session.shouldstop
                and not _expected_to_fail(item)
            )
            for report in reports:
                if repeat and report.failed:
                    report.outcome = "rerun"  # type: ignore[assignment]
                ihook.pytest_runtest_logreport(report=report)
            if not repeat:
                break
            _forget_failures(item)
        ihook.pytest_runtest_logfinish(nodeid=item.nodeid, location=item.location)
        return True

    @pytest.hookimpl(trylast=True)
    def pytest_runtest_teardown(self, item: pytest.Item, nextitem: pytest.Item | None) -> None:
        """Tear down the test alone before its repeat; pytest kept every scope.

        A scope whose setup raised is torn down too, from the outermost broken one,
        so the repeat sets it up again instead of replaying its cached error. Errors
        raised here are the teardown errors of the attempt.
        """
        if nextitem is not item:
            return
        state: Any = item.session._setupstate
        broken = next((node for node, (_, exc) in state.stack.items() if exc is not None), None)
        keep = (broken if broken is not None else item).parent
        state.teardown_exact(keep)

    @pytest.hookimpl(tryfirst=True)
    def pytest_report_teststatus(self, report: pytest.TestReport) -> Any:
        if report.outcome == "rerun":
            return "rerun", "R", ("RERUN", {"yellow": True})
        return None
