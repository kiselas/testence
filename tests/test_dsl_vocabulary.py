"""The everyday DSL vocabulary (stage 4, L19).

A tester coming from Playwright or Cypress reaches for "the field holds X", "three
rows", "the button is disabled", "press Enter" on the first day. Without them the
test drops to ``ex.native`` and loses its intent-bearing steps and evidence. Each
check here is exact by default, and a state that never holds is an AssertionError —
reported as ``failed``, the product disagreeing — never as ``broken``.
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
from testence.pytest_plugin import _error_kind

PAGE = "data:text/html," + urllib.parse.quote(
    """<!doctype html>
<input id=name value="alice">
<input id=agree type=checkbox>
<button id=save disabled>Save</button>
<button id=go>Go</button>
<a id=link href="/x" data-state="ready">Link</a>
<ul><li>a</li><li>b</li><li>c</li></ul>
<select id=size><option value="s">Small</option><option value="l">Large</option></select>
<div id=tip hidden>Tip</div>
<button id=help onmouseenter="document.getElementById('tip').hidden = false">?</button>
<input id=q onkeydown="if (event.key === 'Enter') this.dataset.submitted = 'yes'">
<div id=gone>bye</div>
"""
)

NAME = Target("css", "#name")
AGREE = Target("css", "#agree")
SAVE = Target("css", "#save")
GO = Target("css", "#go")
LINK = Target("css", "#link")
ROWS = Target("css", "li")
SIZE = Target("css", "#size")
TIP = Target("css", "#tip")
HELP = Target("css", "#help")
QUERY = Target("css", "#q")
GONE = Target("css", "#gone")


#: How long a check waits for a state in these tests. Starting the browser and the
#: first navigation keep the engine's default: a hosted macOS runner can take longer
#: than this to load even a data: page.
CHECK_TIMEOUT_MS = 500


@pytest.fixture
def ex(tmp_path):
    engine = PlaywrightCdpEngine(headed=False)
    writer = EvidenceWriter(tmp_path)
    try:
        engine.start()
        engine.goto(PAGE)
        engine.timeout_ms = CHECK_TIMEOUT_MS
        yield Actions(engine, writer, "test_dsl_vocabulary.py::case")
    finally:
        writer.close()
        engine.stop()


def _failure(call) -> BaseException:
    with pytest.raises(StepFailed) as caught:
        call()
    return caught.value.cause


def test_state_checks_pass_on_the_state_they_name(ex):
    ex.expect_value(NAME, "alice")
    ex.expect_count(ROWS, 3)
    ex.expect_enabled(GO)
    ex.expect_disabled(SAVE)
    ex.expect_checked(AGREE, checked=False)
    ex.expect_attribute(LINK, "data-state", "ready")
    ex.expect_hidden(TIP)
    ex.expect_url(contains="data:text/html")


@pytest.mark.parametrize(
    ("check", "message"),
    [
        (lambda ex: ex.expect_value(NAME, "ali"), "expect_value"),
        (lambda ex: ex.expect_count(ROWS, 2), "expect_count"),
        (lambda ex: ex.expect_enabled(SAVE), "expect_enabled"),
        (lambda ex: ex.expect_disabled(GO), "expect_disabled"),
        (lambda ex: ex.expect_checked(AGREE), "expect_checked"),
        (lambda ex: ex.expect_attribute(LINK, "data-state", "read"), "expect_attribute"),
        (lambda ex: ex.expect_hidden(GONE), "expect_hidden"),
        (lambda ex: ex.expect_url(contains="/checkout"), "expect_url"),
    ],
)
def test_a_state_that_never_holds_is_a_failed_assertion(ex, check, message):
    cause = _failure(lambda: check(ex))
    assert isinstance(cause, AssertionError)
    assert message in str(cause)
    # The plugin files it as the product disagreeing: Allure "failed", not "broken".
    assert _error_kind(StepFailed("check", cause)) == "assertion"


def test_value_matching_is_exact(ex):
    """A prefix of the value must not answer for it — the expect_text regression."""
    cause = _failure(lambda: ex.expect_value(NAME, "alic"))
    assert isinstance(cause, AssertionError)


def test_check_uncheck_select_hover_and_press_change_the_page(ex):
    ex.check(AGREE)
    ex.expect_checked(AGREE)
    ex.uncheck(AGREE)
    ex.expect_checked(AGREE, checked=False)

    ex.select(SIZE, label="Large")
    ex.expect_value(SIZE, "l")
    ex.select(SIZE, "s")
    ex.expect_value(SIZE, "s")

    ex.hover(HELP)
    ex.expect_visible(TIP)

    ex.press("Enter", target=QUERY)
    ex.expect_attribute(QUERY, "data-submitted", "yes")


def test_select_needs_exactly_one_of_value_and_label(ex):
    with pytest.raises(ValueError, match="exactly one"):
        ex.select(SIZE)
    with pytest.raises(ValueError, match="exactly one"):
        ex.select(SIZE, "s", label="Small")


def test_expect_url_needs_exactly_one_form(ex):
    with pytest.raises(ValueError, match="exactly one"):
        ex.expect_url()
    with pytest.raises(ValueError, match="exactly one"):
        ex.expect_url(contains="a", equals="b")


def test_a_relative_url_is_resolved_against_base_url(ex):
    ex.engine.base_url = "https://shop.example.test"
    cause = _failure(lambda: ex.expect_url(equals="/cart"))
    assert "https://shop.example.test/cart" in str(cause)


def test_every_check_and_action_is_an_intent_step_in_the_ledger(ex):
    ex.expect_value(NAME, "alice", intent="the name field keeps the saved name")
    ex.check(AGREE, intent="accept the terms")
    ex.writer.close()
    events = [json.loads(line) for line in ex.writer.path.read_text(encoding="utf-8").splitlines()]
    starts = {event["intent"]: event for event in events if event["kind"] == "step.start"}
    assert starts["the name field keeps the saved name"]["target"] == NAME.describe()
    ends = [event for event in events if event["kind"] == "step.end"]
    assert [event["status"] for event in ends] == ["ok", "ok"]
    assert all(event.get("fingerprint") for event in ends)


class _EngineWithoutVocabulary:
    """A third-party engine written against the first Engine protocol."""

    def __init__(self, inner: PlaywrightCdpEngine) -> None:
        self._inner = inner

    def __getattr__(self, name: str):
        if name in {"expect_value", "set_checked", "hover", "select_label", "expect_url"}:
            raise AttributeError(name)
        return getattr(self._inner, name)


def test_an_engine_without_the_new_operations_gets_a_named_unsupported_error(ex):
    old = Actions(_EngineWithoutVocabulary(ex.engine), ex.writer, ex.test_id)  # type: ignore[arg-type]
    for call in (
        lambda: old.expect_value(NAME, "alice"),
        lambda: old.check(AGREE),
        lambda: old.hover(HELP),
        lambda: old.select(SIZE, label="Large"),
    ):
        with pytest.raises(UnsupportedCapability, match="not implemented by"):
            call()
