"""``ex.native``: the one recorded way out of the DSL to raw Playwright (ADR-0027)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from testence.dsl import Actions
from testence.dsl.steps import StepFailed
from testence.engine import Capability, Target, UnsupportedCapability
from testence.engine.playwright_cdp import PlaywrightCdpEngine
from testence.evidence import EvidenceWriter

PAGE = (
    "data:text/html,<input id=box><div id=out></div>"
    "<script>document.addEventListener('keydown',e=>{if(e.ctrlKey&&e.key==='k')"
    "document.querySelector('%23out').textContent='palette'})</script>"
)


def _events(writer: EvidenceWriter) -> list[dict[str, Any]]:
    return [json.loads(line) for line in writer.path.read_text(encoding="utf-8").splitlines()]


@pytest.fixture
def engine():
    eng = PlaywrightCdpEngine(headed=False, debug_port=0)
    eng.start()
    eng.goto(PAGE)
    yield eng
    eng.stop()


def test_native_code_drives_the_page_inside_one_recorded_step(engine, tmp_path):
    with EvidenceWriter(tmp_path, worker="") as writer:
        ex = Actions(engine, writer, "native")
        with ex.native("open the command palette with Ctrl+K") as page:
            page.keyboard.press("Control+k")
        ex.expect_text(Target("css", "#out"), "palette")
        events = _events(writer)
    (used,) = [event for event in events if event["kind"] == "native.used"]
    assert used["intent"] == "open the command palette with Ctrl+K"
    step = next(event for event in events if event["kind"] == "step.start")
    assert step["intent"] == "open the command palette with Ctrl+K"


def test_a_failure_inside_is_a_failed_step_without_a_heal_target(engine, tmp_path):
    with EvidenceWriter(tmp_path, worker="") as writer:
        ex = Actions(engine, writer, "native-fail")
        with pytest.raises(StepFailed, match="drag the missing card"):
            with ex.native("drag the missing card") as page:
                page.locator("#nope").click(timeout=200)
        ends = [event for event in _events(writer) if event["kind"] == "step.end"]
    assert ends[-1]["status"] == "fail"
    assert ex.last_failure is not None and ex.last_failure.target is None


class _NoNativeEngine:
    def capabilities(self) -> frozenset[str]:
        return frozenset({Capability.DOM.value, Capability.NAVIGATION.value})


def test_an_engine_without_the_capability_refuses_before_the_block_runs(tmp_path):
    ran = []
    with EvidenceWriter(tmp_path, worker="") as writer:
        ex = Actions(_NoNativeEngine(), writer, "no-native")  # type: ignore[arg-type]
        with pytest.raises(UnsupportedCapability, match="browser.native"):
            with ex.native("anything"):
                ran.append(True)
    assert ran == []


@pytest.mark.parametrize("intent", ["", "   "])
def test_native_requires_an_intent(tmp_path, intent):
    with EvidenceWriter(tmp_path, worker="") as writer:
        ex = Actions(_NoNativeEngine(), writer, "no-intent")  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="needs an intent"):
            with ex.native(intent):
                pass
