"""``ex.expect_settled``: measure an element after it has stopped moving.

A drawer that slides in is visible from its first frame, so a width read right after
``expect_visible`` is a width of the transition, not of the drawer: the measurement
flaked between runs. ``expect_settled`` waits until the box is the same two animation
frames running and lies wholly inside the viewport.
"""

from __future__ import annotations

import json
import urllib.parse

import pytest

from testence.dsl import Actions
from testence.dsl.steps import StepFailed
from testence.engine import Target, UnsupportedCapability
from testence.engine.playwright_cdp import PlaywrightCdpEngine
from testence.evidence import EvidenceWriter

#: Final width of the drawer; the transition takes long enough that an unsettled read
#: lands in the middle of it on any runner.
WIDTH = 320

PAGE = "data:text/html," + urllib.parse.quote(
    f"""<!doctype html>
<style>
  body {{ margin: 0; }}
  #drawer {{ position: fixed; top: 0; right: 0; height: 200px; width: 0;
            background: #456; overflow: hidden; transition: width 900ms linear; }}
  #drawer.open {{ width: {WIDTH}px; }}
  #runaway {{ position: fixed; top: 0; left: 0; width: 40px; height: 40px;
             background: #a33; animation: spin 400ms linear infinite; }}
  @keyframes spin {{ from {{ left: 0; }} to {{ left: 300px; }} }}
  #below {{ position: absolute; top: 4000px; width: 40px; height: 40px; background: #3a3; }}
</style>
<button id=open onclick="document.getElementById('drawer').classList.add('open')">Open</button>
<div id=drawer>Drawer</div>
<div id=runaway></div>
<div id=below>Below</div>
"""
)

OPEN = Target("css", "#open")
DRAWER = Target("css", "#drawer")
RUNAWAY = Target("css", "#runaway")
BELOW = Target("css", "#below")


@pytest.fixture(scope="module")
def browser():
    owned = PlaywrightCdpEngine(headed=False)
    try:
        owned.start()
        yield owned
    finally:
        owned.stop()


@pytest.fixture
def engine(browser):
    browser.goto(PAGE)  # a fresh document: the drawer closed, no animation running
    browser.reset_taps()
    return browser


@pytest.fixture
def ex(engine, tmp_path):
    writer = EvidenceWriter(tmp_path)
    try:
        yield Actions(engine, writer, "test_expect_settled.py::case")
    finally:
        writer.close()


def _width(engine) -> float:
    return float(engine.eval_js("document.getElementById('drawer').getBoundingClientRect().width"))


def test_without_settling_the_width_is_a_width_of_the_transition(ex, engine):
    ex.click(OPEN)
    ex.expect_visible(DRAWER)
    assert _width(engine) != WIDTH


def test_settled_width_is_the_width_the_drawer_keeps(ex, engine):
    ex.click(OPEN)
    ex.expect_settled(DRAWER, "the drawer has finished sliding in")
    assert _width(engine) == WIDTH


def test_settling_is_a_recorded_step_and_a_ledger_wait(ex, engine):
    ex.click(OPEN)
    ex.expect_settled(DRAWER)
    waits = [entry for entry in engine.wait_ledger() if entry["op"] == "expect_settled"]
    assert len(waits) == 1 and waits[0]["ok"] and waits[0]["ms"] >= 500
    events = [json.loads(line) for line in ex.writer.path.read_text("utf-8").splitlines()]
    (start,) = [e for e in events if e["kind"] == "step.start" and "settled" in e["intent"]]
    assert start["intent"] == "expect css='#drawer' settled"


def test_an_element_that_never_stops_fails_as_an_assertion(ex):
    with pytest.raises(StepFailed) as caught:
        ex.expect_settled(RUNAWAY, timeout_ms=1_500)
    assert isinstance(caught.value.cause, AssertionError)
    assert "still moving" in str(caught.value.cause)


def test_an_element_outside_the_viewport_is_not_settled(ex):
    with pytest.raises(StepFailed) as caught:
        ex.expect_settled(BELOW, timeout_ms=400)
    assert "not wholly inside the viewport" in str(caught.value.cause)


def test_an_engine_without_the_dom_capability_refuses(tmp_path):
    class _NoDom:
        def capabilities(self):
            return frozenset({"lifecycle"})

    writer = EvidenceWriter(tmp_path)
    try:
        actions = Actions(_NoDom(), writer, "t::case")  # type: ignore[arg-type]
        with pytest.raises(UnsupportedCapability, match="browser.dom"):
            actions.expect_settled(DRAWER)
    finally:
        writer.close()
