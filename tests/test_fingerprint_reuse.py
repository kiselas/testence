"""A green replay does not take element fingerprints it already has.

A fingerprint is the baseline of a heal proposal. It was taken after every green step
with a target, one browser round trip each, on every run. Now it is taken once per
step and target: a replay whose store holds it skips the call, a changed target takes
it again, and a CSS selector, which has no accessible name to heal towards, never.
"""

from __future__ import annotations

import json
import urllib.parse
from collections.abc import Iterator
from typing import Any

import pytest

from testence.dsl import Actions
from testence.engine import Target
from testence.engine.playwright_cdp import PlaywrightCdpEngine
from testence.evidence import EvidenceWriter
from testence.fingerprints import FingerprintStore

PAGE = "data:text/html," + urllib.parse.quote(
    """<!doctype html>
<label for=name>Name</label><input id=name>
<button>Save</button><button>Cancel</button>
<p id=out>ready</p>
"""
)

NAME = Target("label", "Name")
SAVE = Target("role", "button", name="Save")
CANCEL = Target("role", "button", name="Cancel")
OUT = Target("css", "#out")


@pytest.fixture(scope="module")
def browser() -> Iterator[PlaywrightCdpEngine]:
    engine = PlaywrightCdpEngine(headed=False)
    try:
        engine.start()
        yield engine
    finally:
        engine.stop()


class _Counting:
    """The engine, counting the separate fingerprint calls."""

    def __init__(self, engine: PlaywrightCdpEngine) -> None:
        self._engine = engine
        self.fingerprints = 0

    def element_fingerprint(self, target: Target) -> dict[str, Any]:
        self.fingerprints += 1
        return self._engine.element_fingerprint(target)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._engine, name)


def _replay(browser, tmp_path, store: FingerprintStore, save: Target = SAVE) -> tuple[int, int]:
    browser.goto(PAGE)
    counting = _Counting(browser)
    writer = EvidenceWriter(tmp_path / f"run-{id(counting)}")
    try:
        ex = Actions(counting, writer, "test_fp.py::case", store=store)  # type: ignore[arg-type]
        ex.fill(NAME, "alice", "type the name")
        ex.click(save, "save")
        ex.click(CANCEL, "cancel")
        ex.expect_visible(NAME, "the name field stays")
        ex.expect_text(OUT, "ready", "the status reads ready")
        steps = [
            doc
            for doc in map(json.loads, writer.path.read_text(encoding="utf-8").splitlines())
            if doc["kind"] == "step.end"
        ]
    finally:
        writer.close()
    assert all(step["status"] == "ok" for step in steps)
    return counting.fingerprints, len(steps)


def test_a_green_replay_takes_no_fingerprint_it_has(browser, tmp_path):
    store = FingerprintStore(tmp_path / "fingerprints.json")
    first, steps = _replay(browser, tmp_path, store)
    assert first == 4  # every step with a non-CSS target
    store.flush()

    replay, steps = _replay(browser, tmp_path, FingerprintStore(tmp_path / "fingerprints.json"))
    assert replay / steps <= 0.10
    assert replay == 0


def test_a_changed_target_is_fingerprinted_again(browser, tmp_path):
    store = FingerprintStore(tmp_path / "fingerprints.json")
    _replay(browser, tmp_path, store)
    changed, _steps = _replay(
        browser, tmp_path, store, save=Target("role", "button", name="Save", nth=0)
    )
    assert changed == 1


def test_a_css_target_is_never_fingerprinted(browser, tmp_path):
    store = FingerprintStore(tmp_path / "fingerprints.json")
    _replay(browser, tmp_path, store)
    assert store.get("test_fp.py::case", "the status reads ready") is None
