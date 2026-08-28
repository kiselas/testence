"""Text assertions match exactly unless told otherwise.

This is a regression test for a *passing* assertion, which is the worst kind of
defect a test framework can have. `expect_text` filtered by substring, so
"the counter shows 4" held against 48, 45 and 14 alike — and a benchmark run
caught it settling on a transient 48 on the way to the right value, turning a
seeded defect into a green run.

The project had already ruled on this shape once, for locators: loose matching on
an identity value is a silent hazard, so `Target` matches identity attributes
exactly and says so. The assertion path is the same hazard with a worse outcome.
"""

from __future__ import annotations

import pytest

from testence.engine import Target
from testence.engine.playwright_cdp import PlaywrightCdpEngine

PAGE = (
    "data:text/html,"
    "<span id=counter>48</span>"
    "<span id=greeting>Welcome, alice</span>"
    "<span id=exact>4</span>"
)

COUNTER = Target("css", "#counter")
GREETING = Target("css", "#greeting")
EXACT = Target("css", "#exact")


@pytest.fixture
def engine():
    eng = PlaywrightCdpEngine(headed=False)
    eng.start()
    eng.goto(PAGE)
    yield eng
    eng.stop()


def test_a_substring_of_the_value_does_not_satisfy_the_assertion(engine):
    """The regression: 48 must not answer for 4."""
    with pytest.raises(Exception):
        engine.expect_text(COUNTER, "4", timeout_ms=500)


def test_the_whole_value_satisfies_it(engine):
    engine.expect_text(COUNTER, "48", timeout_ms=1_000)
    engine.expect_text(EXACT, "4", timeout_ms=1_000)


def test_surrounding_whitespace_is_not_a_difference(engine):
    """Markup wraps and indents; a value is still the value."""
    engine.goto("data:text/html,<span id=counter>\n  48\n</span>")
    engine.expect_text(COUNTER, "48", timeout_ms=1_000)


def test_substring_matching_is_available_when_it_is_meant(engine):
    """A greeting legitimately wraps the value in other words — but the caller has
    to say so, which is the whole point."""
    with pytest.raises(Exception):
        engine.expect_text(GREETING, "alice", timeout_ms=500)
    engine.expect_text(GREETING, "alice", timeout_ms=1_000, exact=False)
