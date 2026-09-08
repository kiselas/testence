"""Regressions for the event-driven SPA latency path."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from testence.dsl import Actions
from testence.engine import NetRecord, Target
from testence.engine.playwright_cdp import PlaywrightCdpEngine
from testence.oracle import save_and_verify

NAME = Target("css", "#name")
MIRROR = Target("css", "#mirror")


@pytest.fixture(scope="module")
def engine():
    instance = PlaywrightCdpEngine(headed=False)
    instance.start()
    yield instance
    instance.stop()


def test_non_textual_spa_root_counts_as_rendered(engine):
    engine.goto(
        "data:text/html,<div id=root></div><script>"
        "setTimeout(()=>root.innerHTML='<input id=name aria-label=Name>',20)"
        "</script>"
    )

    assert engine.wait_until_rendered(timeout_ms=250) is True


def test_fast_fill_preserves_controlled_input_events(engine):
    engine.goto(
        "data:text/html,<input id=name><output id=mirror></output><script>"
        "document.getElementById('name').addEventListener('input',e=>"
        "document.getElementById('mirror').textContent=e.target.value)"
        "</script>"
    )

    engine.fill(NAME, "alice", fast=True)

    engine.expect_text(MIRROR, "alice", timeout_ms=500)
    assert engine.wait_ledger()[-2]["op"] == "fill(fast)"


def test_fingerprint_is_one_non_waiting_browser_evaluation(monkeypatch):
    expected = {"tag": "input", "role": "textbox", "id": "name"}

    class LocatorProbe:
        def evaluate_all(self, expression, argument):
            assert "elements.length" in expression
            assert "ariaLabel" in argument
            return expected

        def count(self):  # pragma: no cover - a regression would call this
            raise AssertionError("fingerprint must not make a count round-trip")

        def evaluate(self, *_args, **_kwargs):  # pragma: no cover
            raise AssertionError("fingerprint must use the non-waiting batch evaluation")

    instance = PlaywrightCdpEngine()
    monkeypatch.setattr(instance, "_locate", lambda _target: LocatorProbe())

    assert instance.element_fingerprint(NAME) == expected


def test_network_response_wait_yields_in_ten_millisecond_quanta():
    record = NetRecord(
        method="POST",
        url="https://example.test/api/widgets",
        status=None,
        started_ms=0.0,
        duration_ms=None,
    )

    class PageProbe:
        def __init__(self) -> None:
            self.delays = []

        def wait_for_timeout(self, milliseconds):
            self.delays.append(milliseconds)
            record.status = 201

    instance = PlaywrightCdpEngine()
    page = PageProbe()
    instance._page = page
    instance._net = [record]

    found = instance.wait_for_response("/api/widgets", method="POST", since=0, timeout_ms=1_000)

    assert found is record
    assert page.delays == [10]


def test_network_response_predicate_skips_unrelated_same_endpoint_traffic():
    unrelated = NetRecord(
        "POST", "https://example.test/api/widgets", 201, 0.0, 1.0, request_body='{"id":1}'
    )
    wanted = NetRecord(
        "POST", "https://example.test/api/widgets", 201, 0.0, 1.0, request_body='{"id":2}'
    )
    instance = PlaywrightCdpEngine()
    instance._page = SimpleNamespace(wait_for_timeout=lambda _ms: None)
    instance._net = [unrelated, wanted]

    found = instance.wait_for_response(
        "/api/widgets",
        method="POST",
        timeout_ms=10,
        predicate=lambda record: record.request_body == '{"id":2}',
    )

    assert found is wanted


def test_attached_engine_does_not_close_the_launchers_context():
    class CloseProbe:
        def __init__(self) -> None:
            self.closed = 0

        def close(self) -> None:
            self.closed += 1

    class PlaywrightProbe:
        def __init__(self) -> None:
            self.stopped = 0

        def stop(self) -> None:
            self.stopped += 1

    instance = PlaywrightCdpEngine(cdp_url="http://127.0.0.1:9333")
    context = CloseProbe()
    playwright = PlaywrightProbe()
    instance._context = context
    instance._pw = playwright
    instance._owns_context = False

    instance.stop()

    assert context.closed == 0
    assert playwright.stopped == 1


def test_engine_closes_a_context_it_created():
    class CloseProbe:
        def __init__(self) -> None:
            self.closed = 0

        def close(self) -> None:
            self.closed += 1

    instance = PlaywrightCdpEngine()
    context = CloseProbe()
    instance._context = context
    instance._owns_context = True

    instance.stop()

    assert context.closed == 1


def test_engine_cleanup_continues_after_a_closed_context_transport():
    class ContextProbe:
        def close(self) -> None:
            raise RuntimeError("connection already closed")

    class CloseProbe:
        def __init__(self) -> None:
            self.closed = 0

        def close(self) -> None:
            self.closed += 1

        def stop(self) -> None:
            self.closed += 1

    instance = PlaywrightCdpEngine()
    browser = CloseProbe()
    playwright = CloseProbe()
    instance._context = ContextProbe()
    instance._browser = browser
    instance._pw = playwright
    instance._owns_context = True
    instance._launched_here = True

    instance.stop()

    assert browser.closed == 1
    assert playwright.closed == 1


@dataclass
class OracleEngineProbe:
    response: object | None = field(default_factory=object)
    request_seen: bool = True
    response_calls: list[tuple[str, int, int]] = field(default_factory=list)
    request_calls: list[tuple[str, int, int]] = field(default_factory=list)
    predicate_calls: list[tuple[str, int]] = field(default_factory=list)

    def net_mark(self) -> int:
        return 7

    def wait_for_response(self, fragment, *, since, timeout_ms):
        self.response_calls.append((fragment, since, timeout_ms))
        return self.response

    def wait_for_request(self, fragment, *, since, timeout_ms):
        self.request_calls.append((fragment, since, timeout_ms))
        return self.request_seen

    def wait_for_predicate_js(self, expression, *, timeout_ms):
        self.predicate_calls.append((expression, timeout_ms))
        return True


class WriterProbe:
    def __init__(self) -> None:
        self.events = []

    def emit(self, kind, **document) -> None:
        self.events.append((kind, document))


def test_default_fill_keeps_legacy_engine_adapter_compatibility():
    class LegacyFillEngine:
        def __init__(self) -> None:
            self.values = []

        def fill(self, target, value) -> None:
            self.values.append((target, value))

        def element_fingerprint(self, _target):
            return {}

    legacy = LegacyFillEngine()
    actions = Actions(legacy, WriterProbe(), "legacy-fill")

    actions.fill(NAME, "alice")

    assert legacy.values == [(NAME, "alice")]


class ActionsProbe:
    def __init__(self, engine: OracleEngineProbe) -> None:
        self.engine = engine
        self.writer = WriterProbe()
        self.test_id = "test-save"
        self.clicks = []
        self.settle_calls = []

    def click(self, target, intent) -> None:
        self.clicks.append((target, intent))

    def settle(self, timeout_ms) -> bool:
        self.settle_calls.append(timeout_ms)
        return True


def test_oracle_uses_scoped_response_instead_of_network_idle():
    engine = OracleEngineProbe()
    actions = ActionsProbe(engine)

    assert (
        save_and_verify(
            actions,
            SimpleNamespace(),
            name="widget",
            ui_view=lambda: {"name": "alpha"},
            api_view=lambda: {"name": "alpha"},
            expect_request="/api/widgets",
            settle_ms=3_000,
        )
        == []
    )

    assert engine.response_calls == [("/api/widgets", 7, 3_000)]
    assert engine.request_calls == []
    assert len(engine.predicate_calls) == 1
    assert "requestAnimationFrame" in engine.predicate_calls[0][0]
    assert engine.predicate_calls[0][1] == 250
    assert actions.settle_calls == []


def test_oracle_reports_when_the_scoped_click_sent_no_request():
    engine = OracleEngineProbe(response=None, request_seen=False)
    actions = ActionsProbe(engine)

    with pytest.raises(AssertionError, match="nothing reached the server"):
        save_and_verify(
            actions,
            SimpleNamespace(),
            name="widget",
            ui_view=dict,
            api_view=dict,
            expect_request="/api/widgets",
            settle_ms=200,
        )

    assert engine.response_calls == [("/api/widgets", 7, 200)]
    assert engine.request_calls == [("/api/widgets", 7, 1)]
    assert engine.predicate_calls == []
    assert actions.settle_calls == []
