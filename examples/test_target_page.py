"""Self-test of the full pipeline against the bench target page.

Run:  pytest examples/ --testence-headless -p testence.pytest_plugin
The deliberately failing pack-demo test is opt-in:  -m demo_failure
"""

from pathlib import Path

import pytest

from testence.engine import Target

TARGET_URL = (Path(__file__).parent.parent / "bench" / "target" / "index.html").resolve().as_uri()

INC = Target("css", "#inc")
COUNT = Target("css", "#count")
NAME = Target("placeholder", "name")
ADD = Target("role", "button", name="add")
ASYNC_OUT = Target("css", "#asyncout")
LOAD = Target("role", "button", name="load async")


def test_counter_increments(ex):
    ex.goto(TARGET_URL, intent="open the target page")
    ex.click(INC, intent="increment the counter")
    ex.expect_text(COUNT, "1", intent="counter shows 1")


def test_row_added_and_async_load(ex):
    ex.goto(TARGET_URL, intent="open the target page")
    ex.fill(NAME, "alice", intent="type a name")
    ex.click(ADD, intent="add the row")
    ex.expect_text(Target("css", "#list li"), "row-alice", intent="row appears in the list")
    ex.click(LOAD, intent="trigger async load")
    ex.expect_text(ASYNC_OUT, "loaded-1", intent="async result rendered (auto-wait)")


@pytest.mark.demo_failure
def test_pack_assembly_demo(ex):
    """Fails on purpose: asserts an element that never appears -> evidence pack."""
    ex.goto(TARGET_URL, intent="open the target page")
    ex.click(INC, intent="increment the counter")
    ex.expect_text(COUNT, "999", intent="counter shows 999 (deliberately wrong)")
