"""``ex.drag``: a kanban card, a sortable row, a drop zone (stage 4, L12 item 1).

Without it a drag dropped to ``ex.native`` and lost its intent-bearing step, its
fingerprint and the failure account of what the targets matched.
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

PAGE = "data:text/html," + urllib.parse.quote(
    """<!doctype html>
<style>div { min-height: 40px; margin: 8px; border: 1px solid; }</style>
<div id=todo><p id=card draggable=true>Write docs</p></div>
<div id=done></div>
<div id=track style="position: relative; width: 300px">
  <span id=knob style="position: absolute; left: 0">o</span>
</div>
<div id=end style="margin-left: 250px; width: 40px">end</div>
<output id=moved></output>
<script>
  const card = document.getElementById('card');
  card.addEventListener('dragstart', e => e.dataTransfer.setData('text/plain', card.id));
  const done = document.getElementById('done');
  done.addEventListener('dragover', e => e.preventDefault());
  done.addEventListener('drop', e => {
    e.preventDefault();
    done.appendChild(document.getElementById(e.dataTransfer.getData('text/plain')));
  });
  // A mouse-driven control: no HTML5 events, only down, move and up.
  let dragging = false;
  document.getElementById('knob').addEventListener('mousedown', () => { dragging = true; });
  document.addEventListener('mouseup', e => {
    if (dragging) document.getElementById('moved').textContent = e.clientX > 200 ? 'far' : 'near';
    dragging = false;
  });
</script>
"""
)

CARD = Target("css", "#card")
DONE = Target("css", "#done")
KNOB = Target("css", "#knob")
END = Target("css", "#end")
MISSING = Target("css", "#archive")


@pytest.fixture
def ex(tmp_path):
    engine = PlaywrightCdpEngine(headed=False)
    writer = EvidenceWriter(tmp_path)
    try:
        engine.start()
        engine.goto(PAGE)
        engine.timeout_ms = 2_000
        yield Actions(engine, writer, "test_dsl_drag.py::case")
    finally:
        writer.close()
        engine.stop()


def test_an_html5_drag_drops_the_card_where_it_was_dropped(ex):
    ex.drag(CARD, DONE, intent="move the card to Done")
    ex.expect_text(Target("css", "#done p"), "Write docs")


def test_a_mouse_driven_control_sees_a_press_move_and_release(ex):
    ex.drag(KNOB, END)
    ex.expect_text(Target("css", "#moved"), "far")


def test_a_missing_destination_is_named_in_the_failure(ex):
    with pytest.raises(StepFailed) as caught:
        ex.drag(CARD, MISSING)
    assert "destination: no element matches" in str(caught.value)


def test_the_drag_is_one_step_with_the_source_fingerprint(ex):
    ex.drag(CARD, DONE, intent="move the card to Done")
    ex.writer.close()
    events = [json.loads(line) for line in ex.writer.path.read_text(encoding="utf-8").splitlines()]
    (start,) = [e for e in events if e["kind"] == "step.start"]
    assert (start["intent"], start["target"]) == ("move the card to Done", CARD.describe())
    (end,) = [e for e in events if e["kind"] == "step.end"]
    assert end["status"] == "ok" and end["fingerprint"]


class _EngineWithoutDrag:
    def __init__(self, inner: PlaywrightCdpEngine) -> None:
        self._inner = inner

    def __getattr__(self, name: str):
        if name == "drag":
            raise AttributeError(name)
        return getattr(self._inner, name)


def test_an_engine_without_drag_gets_a_named_unsupported_error(ex):
    old = Actions(_EngineWithoutDrag(ex.engine), ex.writer, ex.test_id)  # type: ignore[arg-type]
    with pytest.raises(UnsupportedCapability, match="drag .not implemented by"):
        old.drag(CARD, DONE)
