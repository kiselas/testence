"""Actions a suite wrote through ``ex.native``: double and right clicks, held keys,
a drag by an offset, HTML5 drag events, typing at the caret, the window size, a
reload, storage and a second tab. Each is one recorded step with a target."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import pytest

from testence.dsl import Actions
from testence.engine import Target
from testence.engine.playwright_cdp import PlaywrightCdpEngine
from testence.evidence import EvidenceWriter
from testence.loopback import LoopbackHTTPServer

PAGE = """<!doctype html>
<style>
  body { margin: 0; }
  #panel { position: fixed; top: 0; right: 0; height: 120px; width: 300px; background: #eee; }
  #edge { position: absolute; left: 0; top: 0; width: 8px; height: 100%; cursor: ew-resize; }
  #spacer { height: 1600px; }
  li { height: 30px; }
</style>
<button id=node>node</button>
<output id=said></output>
<aside id=panel><div id=edge></div></aside>
<textarea id=editor></textarea>
<output id=keys>0</output>
<div id=spacer></div>
<ol id=rows>
  <li id=r1><span class=grip>::</span> one</li>
  <li id=r2><span class=grip>::</span> two</li>
  <li id=r3><span class=grip>::</span> three</li>
</ol>
<script>
  const said = document.getElementById('said');
  const node = document.getElementById('node');
  node.addEventListener('dblclick', () => { said.textContent = 'opened'; });
  node.addEventListener('contextmenu', (e) => { e.preventDefault(); said.textContent = 'menu'; });
  node.addEventListener('click', (e) => { if (e.shiftKey) said.textContent = 'added'; });
  const panel = document.getElementById('panel');
  let from = null;
  document.getElementById('edge').addEventListener('mousedown', (e) => { from = e.clientX; });
  document.addEventListener('mousemove', (e) => {
    if (from === null) return;
    panel.style.width = (300 + from - e.clientX) + 'px';
  });
  document.addEventListener('mouseup', () => { from = null; });
  let keys = 0;
  document.getElementById('editor').addEventListener('keydown', () => {
    document.getElementById('keys').textContent = String(++keys);
  });
  // draggable only after a mousedown on the grip, as some sortable tables do
  const list = document.getElementById('rows');
  let dragged = null;
  for (const row of list.children) {
    row.querySelector('.grip').addEventListener('mousedown', () => { row.draggable = true; });
    row.addEventListener('dragstart', (e) => {
      if (!row.draggable) return;
      dragged = row; e.dataTransfer.setData('text/plain', row.id);
    });
    row.addEventListener('dragover', (e) => e.preventDefault());
    row.addEventListener('drop', (e) => {
      e.preventDefault();
      if (dragged && e.dataTransfer.getData('text/plain') === dragged.id) list.insertBefore(dragged, row);
    });
    row.addEventListener('dragend', () => { row.draggable = false; });
  }
</script>
"""


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - http.server's name
        body = PAGE.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass


@pytest.fixture(scope="module")
def site() -> Iterator[str]:
    server = LoopbackHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def ex(tmp_path: Path, site: str) -> Iterator[Actions]:
    engine = PlaywrightCdpEngine(base_url=site, headed=False)
    writer = EvidenceWriter(tmp_path)
    try:
        engine.start()
        engine.timeout_ms = 3_000
        engine.goto("/board")
        yield Actions(engine, writer, "test_dsl_actions.py::case")
    finally:
        writer.close()
        engine.stop()


NODE = Target("css", "#node")
SAID = Target("css", "#said")


def test_double_and_right_click_and_a_held_key(ex: Actions) -> None:
    ex.double_click(NODE, intent="open the node")
    ex.expect_text(SAID, "opened")
    ex.right_click(NODE)
    ex.expect_text(SAID, "menu")
    # Shift, not Control: on macOS a Control-click is a right click.
    ex.click(NODE, modifiers=["Shift"])
    ex.expect_text(SAID, "added")


def test_click_refuses_unknown_modifiers_and_fast_with_modifiers(ex: Actions) -> None:
    with pytest.raises(Exception, match="unknown modifier"):
        ex.click(NODE, modifiers=["Hyper"])
    with pytest.raises(ValueError, match="fast= or modifiers="):
        ex.click(NODE, fast=True, modifiers=["Shift"])


def test_drag_by_moves_the_panel_edge(ex: Actions) -> None:
    edge = Target("css", "#edge")
    ex.drag_by(edge, -80, intent="widen the panel by its left edge")
    assert ex.box(Target("css", "#panel")).width == pytest.approx(380, abs=2)
    with pytest.raises(ValueError):
        ex.drag_by(edge, 10, steps=0)


def test_html5_drag_reaches_rows_outside_the_window_through_their_grip(ex: Actions) -> None:
    rows = Target("css", "#rows li")
    ex.drag(
        Target("css", "#r3"),
        Target("css", "#r1"),
        html5=True,
        handle=Target("css", "#r3 .grip"),
        intent="move row three above row one",
    )
    assert ex.texts(rows) == [":: three", ":: one", ":: two"]
    with pytest.raises(ValueError, match="html5=True"):
        ex.drag(Target("css", "#r1"), Target("css", "#r2"), handle=Target("css", "#r1 .grip"))


def test_type_presses_every_key_where_fill_presses_none(ex: Actions) -> None:
    editor = Target("css", "#editor")
    ex.fill(editor, "ab")
    ex.expect_text(Target("css", "#keys"), "0")
    ex.type(editor, "cd", intent="type at the end")
    ex.expect_value(editor, "abcd")
    ex.expect_text(Target("css", "#keys"), "2")


def test_viewport_storage_reload_and_a_second_tab(ex: Actions) -> None:
    ex.set_viewport(900, 600)
    assert ex.viewport() == (900, 600)
    ex.set_storage({"lang": "en", "widths": "{}"})
    ex.reload()
    assert ex.storage_item("lang") == "en"
    ex.new_page("/board?tab=two", intent="open the same board in a second tab")
    assert ex.url().endswith("/board?tab=two")
    assert ex.storage_item("lang") == "en"
    ex.switch_page(0)
    assert ex.url().endswith("/board")
    blockers = ex.engine.reuse_blockers()  # type: ignore[attr-defined]
    assert "viewport" in blockers and "new_page" in blockers
    with pytest.raises(ValueError):
        ex.set_viewport(0, 600)
    with pytest.raises(ValueError):
        ex.set_storage({})
