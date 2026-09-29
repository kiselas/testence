"""A test that leaves its browser running must not break the tests after it.

Playwright's sync API allows one driver per thread. The first test below starts an engine
and never stops it, as a test does when an assertion fails between ``start()`` and
``stop()``; the second needs a driver of its own. Without the guard in ``conftest.py`` it
fails with "Sync API inside the asyncio loop", as a dozen unrelated tests did behind one
timeout on a CI runner.
"""

from __future__ import annotations

from testence.config import Settings
from testence.engine import create_engine


def _engine(tmp_path):
    settings = Settings.load(tmp_path, runs_root=str(tmp_path / "runs"))
    settings.headed = False
    return create_engine(settings)


def test_a_test_starts_an_engine_and_forgets_it(tmp_path):
    _engine(tmp_path).start()


def test_the_next_test_still_gets_a_browser(tmp_path):
    engine = _engine(tmp_path)
    engine.start()
    try:
        engine.goto("about:blank")
    finally:
        engine.stop()
