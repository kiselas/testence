"""The canonical suite the corpus runs against every mutated page.

Deliberately ordinary: this is what a project's test looks like, so what the corpus
measures is the framework's behaviour on realistic cases rather than on a rig built
to make the framework look good.

Driven by ``TESTENCE_CORPUS_PAGE`` (a file:// URL), set by ``corpus/run.py``.
"""

from __future__ import annotations

import os

import pytest

from testence.engine import Target

PAGE = os.environ.get("TESTENCE_CORPUS_PAGE", "")

INC = Target("css", "#inc")
COUNT = Target("css", "#count")
NAME = Target("placeholder", "name")
ADD = Target("role", "button", name="add")
ROW = Target("css", "#list li")
LOAD = Target("role", "button", name="load async")
ASYNC_OUT = Target("css", "#asyncout")


@pytest.fixture(autouse=True)
def _require_page():
    if not PAGE:
        pytest.skip("TESTENCE_CORPUS_PAGE not set; run via corpus/run.py")


def test_counter(ex):
    ex.goto(PAGE, intent="open the page")
    ex.click(INC, intent="increment the counter")
    ex.expect_text(COUNT, "1", intent="counter shows 1")


def test_add_row(ex):
    ex.goto(PAGE, intent="open the page")
    ex.fill(NAME, "alice", intent="type a name")
    ex.click(ADD, intent="add the row")
    ex.expect_text(ROW, "row-alice", intent="row appears in the list")


def test_async_load(ex):
    ex.goto(PAGE, intent="open the page")
    ex.click(LOAD, intent="trigger async load")
    ex.expect_text(ASYNC_OUT, "loaded-1", intent="async result rendered")
