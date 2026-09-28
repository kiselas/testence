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
from _pytest.runner import runtestprotocol

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

    A fixture whose setup raised caches the exception, and a collector whose setup
    raised keeps it on the setup stack; either would replay the old failure instead
    of trying again.
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
    # what the failed attempt stored on ``self``.
    if getattr(item, "_instance", None) is not None:
        del item._instance  # type: ignore[attr-defined]
        item._obj = None  # type: ignore[attr-defined]
    state: Any = getattr(item.session, "_setupstate", None)
    stack = getattr(state, "stack", None)
    if isinstance(stack, dict) and any(entry[1] is not None for entry in stack.values()):
        # Tearing everything down re-creates the broken scope on the repeat.
        state.teardown_exact(None)


class Reruns:
    """The pytest plugin object; registered only when reruns are requested."""

    def __init__(self, count: int) -> None:
        self.count = count

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_protocol(self, item: pytest.Item, nextitem: pytest.Item | None) -> bool:
        ihook = item.ihook
        for attempt in range(self.count + 1):
            ihook.pytest_runtest_logstart(nodeid=item.nodeid, location=item.location)
            reports = runtestprotocol(item, nextitem=nextitem, log=False)
            repeat = (
                attempt < self.count
                and any(report.failed for report in reports)
                and not item.session.shouldstop
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

    @pytest.hookimpl(tryfirst=True)
    def pytest_report_teststatus(self, report: pytest.TestReport) -> Any:
        if report.outcome == "rerun":
            return "rerun", "R", ("RERUN", {"yellow": True})
        return None
