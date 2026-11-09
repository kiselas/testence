"""Readers: what the page shows, returned to the test as one recorded step each.

A suite that had no reader read a list, an attribute or a box through ``ex.native``:
a step with no target and no check, after which the page is no longer handed to the
next test. A reader is a step with a target, strict like a click, that records how
much it read and never what.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import pytest

from testence.dsl import Actions
from testence.dsl.steps import StepFailed
from testence.engine import Box, Target, UnsupportedCapability
from testence.engine.playwright_cdp import PlaywrightCdpEngine
from testence.evidence import EvidenceWriter
from testence.loopback import LoopbackHTTPServer

SECRET = "s3cret-banner-value"

PAGE = f"""<!doctype html>
<style>
  body {{ margin: 0; }}
  #panel {{ position: fixed; top: 0; right: 0; width: 320px; height: 200px;
    transform: translateX(100%); transition: transform 300ms linear; }}
  #panel.open {{ transform: translateX(0); }}
  th {{ width: 100px; padding: 0; }}
</style>
<h1 id=title data-state="ready">Widgets</h1>
<p class=note>first</p><p class=note>second</p>
<p id=banner>{SECRET}</p>
<p id=hidden hidden>not shown</p>
<ul id=late></ul>
<table><tr><th>Name</th><th>Owner</th><th>Updated</th></tr></table>
<aside id=panel>panel</aside>
<script>
  localStorage.setItem('widths', JSON.stringify({{name: 140}}));
  window.appState = {{rows: 3}};
  setTimeout(() => {{
    for (const name of ['alpha', 'beta']) {{
      const li = document.createElement('li');
      li.textContent = name;
      document.getElementById('late').appendChild(li);
    }}
  }}, 300);
  requestAnimationFrame(() => document.getElementById('panel').classList.add('open'));
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
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/widgets?tab=main"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def ex(tmp_path: Path, site: str) -> Iterator[Actions]:
    engine = PlaywrightCdpEngine(headed=False)
    writer = EvidenceWriter(tmp_path)
    try:
        engine.start()
        engine.timeout_ms = 3_000
        engine.goto(site)
        yield Actions(engine, writer, "test_dsl_readers.py::case")
    finally:
        writer.close()
        engine.stop()


def _events(ex: Actions) -> list[dict]:
    ex.writer.close()
    return [json.loads(line) for line in ex.writer.path.read_text(encoding="utf-8").splitlines()]


def test_text_reads_one_element_and_records_only_its_size(ex: Actions) -> None:
    assert ex.text(Target("css", "#banner"), intent="read the banner") == SECRET
    events = _events(ex)
    end = next(e for e in events if e["kind"] == "step.end" and e["status"] == "ok")
    assert end["read"] == {"chars": len(SECRET)}
    # The value is not part of the read; only the element's fingerprint holds text.
    without_fingerprints = [{k: v for k, v in e.items() if k != "fingerprint"} for e in events]
    assert SECRET not in json.dumps(without_fingerprints)


def test_text_of_two_matches_fails_naming_them(ex: Actions) -> None:
    with pytest.raises(StepFailed) as caught:
        ex.text(Target("css", ".note"))
    assert "2 elements" in str(caught.value) or "strict mode" in str(caught.value)


def test_texts_waits_for_the_list_to_arrive(ex: Actions) -> None:
    items = Target("css", "#late li")
    assert ex.texts(items, minimum=2) == ["alpha", "beta"]


def test_texts_with_minimum_zero_reads_what_is_there(ex: Actions) -> None:
    assert ex.texts(Target("css", "#archive li"), minimum=0) == []
    with pytest.raises(ValueError):
        ex.texts(Target("css", "p"), minimum=-1)


def test_count_and_is_visible_do_not_wait(ex: Actions) -> None:
    assert ex.count(Target("css", ".note")) == 2
    assert ex.count(Target("css", ".missing")) == 0
    assert ex.is_visible(Target("css", "#title")) is True
    assert ex.is_visible(Target("css", "#hidden")) is False
    assert ex.is_visible(Target("css", "#nowhere")) is False


def test_attribute_returns_the_value_or_none(ex: Actions) -> None:
    title = Target("role", "heading", name="Widgets")
    assert ex.attribute(title, "data-state") == "ready"
    assert ex.attribute(title, "data-missing") is None


def test_box_of_a_settled_panel_is_its_final_place(ex: Actions) -> None:
    panel = Target("css", "#panel")
    box = ex.box(panel, settled=True)
    assert isinstance(box, Box)
    assert box.width == pytest.approx(320, abs=1)
    viewport = ex.read_js("read the viewport width", "() => window.innerWidth")
    assert box.right == pytest.approx(viewport, abs=1)
    assert box.center == (box.x + box.width / 2, box.y + box.height / 2)


def test_boxes_measure_every_header(ex: Actions) -> None:
    headers = ex.boxes(Target("css", "th"))
    assert len(headers) == 3
    assert [round(b.width) for b in headers] == [100, 100, 100]
    assert headers[0].right <= headers[1].x + 0.5


def test_url_storage_and_read_js(ex: Actions, site: str) -> None:
    assert ex.url() == site
    assert json.loads(ex.storage_item("widths") or "") == {"name": 140}
    assert ex.storage_item("absent") is None
    assert ex.read_js("read the row count", "key => window.appState[key]", "rows") == 3
    with pytest.raises(ValueError):
        ex.read_js("", "() => 1")


def test_readers_leave_the_page_fit_to_hand_on(ex: Actions) -> None:
    ex.text(Target("css", "#banner"))
    ex.texts(Target("css", ".note"))
    ex.box(Target("css", "#title"))
    ex.read_js("read the state", "() => window.appState.rows")
    assert ex.engine.reuse_blockers() == []  # type: ignore[attr-defined]
    with ex.native("raw access"):
        pass
    assert "native" in ex.engine.reuse_blockers()  # type: ignore[attr-defined]


class _EngineWithoutReaders:
    """An engine written before the readers: no is_visible, box or evaluate."""

    def capabilities(self) -> frozenset[str]:
        return frozenset({"browser.dom", "browser.javascript"})

    def element_fingerprint(self, target: Target) -> dict:
        return {}


@pytest.mark.parametrize(
    "read",
    [
        lambda ex: ex.is_visible(Target("css", "#x")),
        lambda ex: ex.box(Target("css", "#x")),
        lambda ex: ex.read_js("read", "() => 1"),
    ],
    ids=["is_visible", "box", "read_js"],
)
def test_an_older_engine_says_which_reader_it_lacks(tmp_path: Path, read) -> None:
    writer = EvidenceWriter(tmp_path)
    try:
        actions = Actions(_EngineWithoutReaders(), writer, "t")  # type: ignore[arg-type]
        with pytest.raises(UnsupportedCapability):
            read(actions)
    finally:
        writer.close()
