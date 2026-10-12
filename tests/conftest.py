"""Test-suite configuration."""

from __future__ import annotations

import subprocess
from contextlib import suppress

import pytest

from testence.engine.playwright_cdp import PlaywrightCdpEngine

# Fixture projects are inputs that tests run in subprocesses, not tests of this suite.
collect_ignore_glob = ["fixtures/*"]

#: Engines started in this process, in order. Playwright's sync API allows one driver per
#: thread: a test that fails between ``engine.start()`` and ``engine.stop()`` left its
#: driver running, and every later test on that worker died with "Sync API inside the
#: asyncio loop", which read as a dozen unrelated failures behind one timeout.
_STARTED: list[PlaywrightCdpEngine] = []
_original_start = PlaywrightCdpEngine.start


def _tracked_start(self: PlaywrightCdpEngine) -> None:
    _original_start(self)
    _STARTED.append(self)


PlaywrightCdpEngine.start = _tracked_start  # type: ignore[method-assign]


@pytest.fixture(autouse=True)
def _stop_engines_a_test_left_running():
    """Stop what the test itself started and did not stop.

    Engines a module- or session-scoped fixture started before this test are the
    fixture's to stop; only later ones are the test's.
    """
    mark = len(_STARTED)
    yield
    for engine in reversed(_STARTED[mark:]):
        with suppress(Exception):
            engine.stop()
    del _STARTED[mark:]


#: How much of a killed subprocess's output a failure report keeps.
_TIMEOUT_TAIL_CHARS = 12_000


def _tail(output: bytes | str | None) -> str:
    if output is None:
        return "(none)"
    text = output.decode("utf-8", "replace") if isinstance(output, bytes) else output
    return text[-_TIMEOUT_TAIL_CHARS:] or "(empty)"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Show what a nested process printed before its timeout killed it.

    ``TimeoutExpired`` carries the output, but the report only names the command, so
    a nested pytest that hung on a CI runner left nothing to read. With
    ``faulthandler_timeout`` in ``PYTEST_ADDOPTS`` (CI sets it) that output includes
    the stack of every thread of the hung process.
    """
    outcome = yield
    excinfo = call.excinfo
    if excinfo is None or not isinstance(excinfo.value, subprocess.TimeoutExpired):
        return
    report = outcome.get_result()
    error = excinfo.value
    report.sections.append(("nested process stdout before the timeout", _tail(error.stdout)))
    report.sections.append(("nested process stderr before the timeout", _tail(error.stderr)))
