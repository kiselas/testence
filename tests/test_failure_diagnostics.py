"""A failed step says what the page held, and evidence is recorded once.

Launch-hardening audit, 26 September 2026 (A1-04, A1-07, A1-08, A1-09). A timeout
alone tells a reader how long something was waited for; the next question is what
the target matched instead — nothing, several elements, or one showing other text.
"""

from __future__ import annotations

import urllib.parse

import pytest

from testence.dsl import Actions
from testence.dsl.steps import StepFailed
from testence.engine import Target
from testence.engine.playwright_cdp import PlaywrightCdpEngine, _under
from testence.evidence import EvidenceWriter

PAGE = "data:text/html," + urllib.parse.quote(
    """<!doctype html>
<p id=count>0 items left</p>
<ul><li>alpha</li><li>beta</li><li>gamma</li><li>delta</li></ul>
<label>Show <select><option>All</option><option>Done</option></select></label>
"""
)

COUNT = Target("css", "#count")
ITEMS = Target("css", "li")
FILTER_BY_LABEL = Target("label", "Show")


@pytest.fixture
def ex(tmp_path):
    engine = PlaywrightCdpEngine(headed=False, debug_port=0)
    writer = EvidenceWriter(tmp_path, worker="")
    try:
        engine.start()
        engine.goto(PAGE)
        engine.timeout_ms = 500
        yield Actions(engine, writer, "test_failure_diagnostics.py::case")
    finally:
        writer.close()
        engine.stop()


def _failed(call) -> StepFailed:
    with pytest.raises(StepFailed) as caught:
        call()
    return caught.value


def test_a_wrong_text_names_the_text_that_is_there(ex):
    failure = _failed(lambda: ex.expect_text(COUNT, "5 items left"))

    assert "1 element matches, showing '0 items left'" in str(failure)
    assert str(failure).index("showing") < str(failure).index("AssertionError")


def test_an_ambiguous_target_says_how_many_matched(ex):
    failure = _failed(lambda: ex.click(ITEMS))

    assert "4 elements match ('alpha', 'beta', 'gamma', ...)" in str(failure)
    assert "nth=" in str(failure)


def test_a_missing_target_points_at_the_same_name_in_the_accessibility_tree(ex):
    failure = _failed(lambda: ex.select(FILTER_BY_LABEL, label="Done"))

    assert "no element matches" in str(failure)
    assert """combobox "Show" (Target('role', 'combobox', name='Show'))""" in str(failure)
    assert "no element matches label='Show'" in str(failure)


def test_the_ledger_step_carries_the_same_account(ex, tmp_path):
    _failed(lambda: ex.expect_text(COUNT, "5 items left"))
    ex.writer.close()

    ledger = next(tmp_path.glob("*/run.jsonl")).read_text(encoding="utf-8")
    assert "showing '0 items left'" in ledger


def test_switching_back_to_a_tab_does_not_record_its_events_twice(ex):
    engine = ex.engine
    engine._context.new_page()
    for index in (1, 0, 1, 0, 1, 0):
        engine.switch_page(index)
    engine._require_page().evaluate("console.error('marker-once')")
    engine._require_page().wait_for_timeout(100)

    messages = [entry for entry in engine.console_log() if "marker-once" in entry["text"]]
    assert len(messages) == 1


def test_waiting_for_at_least_zero_elements_does_not_wait(ex):
    assert ex.engine.wait_for_count(Target("css", ".absent"), minimum=0, timeout_ms=5_000) == 0


def test_a_default_browser_starts_while_another_run_holds_9222():
    """A fixed default port made a second run's browser fail to start its devtools
    server and hang in launch (seen under a parallel suite on 26 September 2026)."""
    import socket
    from urllib.parse import urlsplit

    from testence.config import Settings

    assert Settings().debug_port == 0
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        holder.bind(("127.0.0.1", 9222))
        holder.listen()
    except OSError:
        pass  # something else already holds it, which is the situation under test
    engine = PlaywrightCdpEngine(headed=False)
    try:
        engine.start()
        engine.goto(PAGE)
        endpoint = engine.browser_manifest()["cdp_endpoint"]
        # The devtools server is listening where the pack says it is.
        socket.create_connection(("127.0.0.1", urlsplit(endpoint).port), timeout=5).close()
    finally:
        engine.stop()
        holder.close()
    assert not endpoint.endswith((":9222", ":0"))


@pytest.mark.parametrize(
    ("url", "base", "under"),
    [
        ("http://localhost:3000/todos", "http://localhost:3000", True),
        ("http://localhost:3000", "http://localhost:3000", True),
        ("http://localhost:3000?q=1", "http://localhost:3000", True),
        ("http://localhost:30001/todos", "http://localhost:3000", False),
        ("http://localhost:3000.evil.test/", "http://localhost:3000", False),
        ("https://host/app/x", "https://host/app", True),
        ("https://host/apple", "https://host/app", False),
        ("https://host/app/x", "https://host/app/", True),
        ("http://host/app/x", "https://host/app", False),
    ],
)
def test_client_side_navigation_stays_on_the_configured_origin(url, base, under):
    assert _under(url, base) is under


def test_a_missing_visual_baseline_is_missing_evidence_not_an_os_error(tmp_path):
    from testence.visual import VisualUnavailable, _bytes

    with pytest.raises(VisualUnavailable, match="no reviewed visual baseline"):
        _bytes(tmp_path / "never-recorded" / "baseline.json")


@pytest.mark.parametrize(
    ("line", "role", "name"),
    [
        ('combobox "Say \\"hi\\" now"', "combobox", 'Say "hi" now'),
        ('graphics-symbol "Logo"', "graphics-symbol", "Logo"),
        (r'button "C:\\temp" [disabled]', "button", r"C:\temp"),
    ],
)
def test_a_hint_names_the_element_as_its_target_would(line, role, name):
    from testence.engine.playwright_cdp import _ARIA_ENTRY, _ARIA_ESCAPE

    matched = _ARIA_ENTRY.match(line)
    assert matched is not None
    assert (matched.group(1), _ARIA_ESCAPE.sub(r"\1", matched.group(2))) == (role, name)
