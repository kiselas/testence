"""Soft checks, tabs and fake time in the DSL (stage 4, L12 items 3, 5 and 7)."""

from __future__ import annotations

import json
import urllib.parse

import pytest

from testence.dsl import Actions
from testence.dsl.steps import SoftAssertionsFailed, StepFailed
from testence.engine import Target, UnsupportedCapability
from testence.engine.playwright_cdp import PlaywrightCdpEngine
from testence.evidence import EvidenceWriter
from testence.pytest_plugin import _error_kind


def _page(html: str) -> str:
    return "data:text/html," + urllib.parse.quote(html)


SUMMARY = _page(
    """<span id=total>9</span><span id=items>2</span><span id=status>paid</span>
<button id=open onclick="window.open('about:blank#second')">open</button>"""
)
TOTAL = Target("css", "#total")
ITEMS = Target("css", "#items")
STATUS = Target("css", "#status")
OPEN = Target("css", "#open")
MISSING = Target("css", "#missing")
STAMP = Target("css", "#stamp")


#: How long a check waits for a state in these tests; navigation keeps the engine's
#: default, which a slow hosted runner needs for its first page.
CHECK_TIMEOUT_MS = 500


@pytest.fixture
def ex(tmp_path):
    engine = PlaywrightCdpEngine(headed=False)
    writer = EvidenceWriter(tmp_path)
    try:
        engine.start()
        engine.timeout_ms = CHECK_TIMEOUT_MS
        yield Actions(engine, writer, "test_dsl_soft_tabs_clock.py::case")
    finally:
        writer.close()
        engine.stop()


def _events(ex: Actions) -> list[dict]:
    ex.writer.close()
    return [json.loads(line) for line in ex.writer.path.read_text(encoding="utf-8").splitlines()]


# -- soft checks ----------------------------------------------------------------------


def test_soft_runs_every_check_and_fails_once_listing_the_failures(ex):
    ex.goto(SUMMARY)
    reached_the_end = False
    with pytest.raises(StepFailed) as caught:
        with ex.soft("the order summary"):
            ex.expect_text(TOTAL, "10", intent="the total is 10")
            ex.expect_text(ITEMS, "2", intent="two items")
            ex.expect_text(STATUS, "shipped", intent="the order is shipped")
            reached_the_end = True
    assert reached_the_end
    cause = caught.value.cause
    assert isinstance(cause, SoftAssertionsFailed)
    assert [failure.intent for failure in cause.failures] == [
        "the total is 10",
        "the order is shipped",
    ]
    assert "2 checks failed in 'the order summary'" in str(cause)
    # A failed soft block is the product disagreeing: Allure "failed".
    assert _error_kind(caught.value) == "assertion"

    ends = [event for event in _events(ex) if event["kind"] == "step.end"]
    softened = [event for event in ends if event.get("soft")]
    assert len(softened) == 2 and all(event["status"] == "fail" for event in softened)


def test_soft_block_with_passing_checks_passes(ex):
    ex.goto(SUMMARY)
    with ex.soft("the order summary"):
        ex.expect_text(TOTAL, "9")
        ex.expect_text(ITEMS, "2")


def test_an_action_that_fails_inside_soft_still_stops_the_test(ex):
    ex.goto(SUMMARY)
    # An action waits for its element by the page's default timeout; keep it short.
    ex.engine.native_page().set_default_timeout(CHECK_TIMEOUT_MS)
    after = False
    with pytest.raises(StepFailed) as caught:
        with ex.soft("the order summary"):
            ex.expect_text(TOTAL, "10")
            ex.click(MISSING, intent="open the missing panel")
            after = True
    assert not after
    # The action's failure, not a soft summary.
    assert not isinstance(caught.value.cause, SoftAssertionsFailed)


def test_soft_blocks_do_not_nest_and_need_an_intent(ex):
    ex.goto(SUMMARY)
    with pytest.raises(ValueError, match="intent"):
        with ex.soft(" "):
            pass
    with pytest.raises(StepFailed) as caught:
        with ex.soft("outer"):
            with ex.soft("inner"):
                pass
    assert isinstance(caught.value.cause, RuntimeError)


# -- tabs -----------------------------------------------------------------------------


def test_a_tab_the_page_opens_is_reached_by_url_and_closed_back(ex):
    ex.goto(SUMMARY)
    ex.click(OPEN, intent="open the second tab")
    ex.switch_page(url_contains="#second", intent="continue in the second tab")
    assert ex.engine.page_count() == 2
    ex.expect_url(contains="#second")
    ex.close_page(intent="close the second tab")
    assert ex.engine.page_count() == 1
    ex.expect_text(TOTAL, "9")


def test_switch_page_by_index_and_its_errors(ex):
    ex.goto(SUMMARY)
    ex.click(OPEN)
    ex.switch_page(url_contains="#second")
    ex.switch_page(0, intent="back to the first tab")
    ex.expect_text(TOTAL, "9")
    with pytest.raises(ValueError, match="exactly one"):
        ex.switch_page()
    with pytest.raises(ValueError, match="exactly one"):
        ex.switch_page(0, url_contains="#second")
    with pytest.raises(StepFailed) as caught:
        ex.switch_page(url_contains="#never")
    assert isinstance(caught.value.cause, AssertionError)


def test_the_only_page_cannot_be_closed(ex):
    ex.goto(SUMMARY)
    with pytest.raises(StepFailed, match="only open page"):
        ex.close_page()


# -- clock ----------------------------------------------------------------------------


def test_an_installed_clock_decides_the_date_the_page_renders(ex):
    ex.clock.install("2030-05-01T10:00:00Z", intent="it is the first of May 2030")
    ex.goto(
        _page(
            "<span id=stamp></span><script>"
            "document.getElementById('stamp').textContent = new Date().toISOString().slice(0, 10)"
            "</script>"
        )
    )
    ex.expect_text(STAMP, "2030-05-01")


def test_fast_forward_runs_a_timer_without_waiting_for_it(ex):
    ex.clock.install()
    ex.goto(
        _page(
            "<span id=stamp>pending</span><script>"
            "setTimeout(() => document.getElementById('stamp').textContent = 'expired', 60000)"
            "</script>"
        )
    )
    ex.expect_text(STAMP, "pending")
    ex.clock.fast_forward("01:01", intent="a minute passes")
    ex.expect_text(STAMP, "expired")
    starts = [event for event in _events(ex) if event["kind"] == "step.start"]
    assert "a minute passes" in [event["intent"] for event in starts]


class _EngineWithoutClock:
    def __init__(self, inner: PlaywrightCdpEngine) -> None:
        self._inner = inner

    def capabilities(self) -> frozenset[str]:
        return self._inner.capabilities() - {"browser.clock"}

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


def test_an_engine_without_the_clock_capability_refuses(ex):
    old = Actions(_EngineWithoutClock(ex.engine), ex.writer, ex.test_id)  # type: ignore[arg-type]
    with pytest.raises(UnsupportedCapability, match="browser.clock"):
        old.clock.install()
