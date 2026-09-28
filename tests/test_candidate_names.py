"""Candidate targets carry the name a role locator resolves (review 2026-09-28, P0-4).

``candidate_elements`` backs heal proposals. It named a labelled field by its
placeholder, cut names at 80 characters without collapsing whitespace and looked at
the first 400 elements only, so a proposal could be a target that finds nothing.
"""

from __future__ import annotations

import urllib.parse

import pytest

from testence.engine import Target
from testence.engine.playwright_cdp import PlaywrightCdpEngine

HIDDEN = "".join(f"<li hidden>row {n}</li>" for n in range(1000))
PAGE = "data:text/html," + urllib.parse.quote(
    f"""<!doctype html>
<ul>{HIDDEN}</ul>
<label for=task>New task</label><input id=task placeholder="Buy milk">
<span id=hint>Due date</span><input aria-labelledby=hint placeholder="dd.mm.yyyy">
<button>Save
    and   close</button>
"""
)


@pytest.fixture
def engine():
    engine = PlaywrightCdpEngine(headed=False)
    try:
        engine.start()
        engine.goto(PAGE)
        yield engine
    finally:
        engine.stop()


def _targets(engine: PlaywrightCdpEngine) -> list[Target]:
    found = [candidate["target"] for candidate in engine.candidate_elements()]
    return [Target(t["kind"], t["value"], name=t.get("name")) for t in found]


def test_every_named_candidate_resolves_to_its_element(engine):
    targets = _targets(engine)
    names = {target.name for target in targets if target.kind == "role"}
    assert {"New task", "Due date", "Save and close"} <= names
    for target in targets:
        if target.kind == "role" and target.name in {"New task", "Due date", "Save and close"}:
            assert engine.count(target) == 1, target.describe()


def test_hidden_elements_do_not_crowd_out_the_visible_ones(engine):
    assert all(target.value != "row 0" for target in _targets(engine))
