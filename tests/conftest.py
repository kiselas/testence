"""Test-suite configuration."""

from __future__ import annotations

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
