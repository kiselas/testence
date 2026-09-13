from types import SimpleNamespace

import pytest

from testence.assurance import assertion_errors
from testence.dsl.steps import Actions, StepFailed
from testence.engine import Target
from testence.engine.playwright_cdp import PlaywrightCdpEngine


@pytest.mark.parametrize("port,expected", [(0, 0), (9300, 9303)])
def test_engine_factory_preserves_ephemeral_port_with_parallel_workers(monkeypatch, port, expected):
    from testence.config import Settings
    from testence.engine import create_engine

    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw3")
    engine = create_engine(Settings(debug_port=port))
    assert engine.debug_port == expected


@pytest.fixture
def visible_actions():
    engine = PlaywrightCdpEngine(headed=False, timeout_ms=10_000, debug_port=0)
    events = []
    writer = SimpleNamespace(emit=lambda kind, **data: events.append({"kind": kind, **data}))
    try:
        engine.start()
        engine.goto("data:text/html,<button id=visible>Visible</button>")
        # The short budget belongs to the intentionally missing assertion, not
        # browser startup/navigation on a slower hosted Windows runner.
        engine.timeout_ms = 150
        yield Actions(engine, writer, "test-ui"), events
    finally:
        engine.stop()


@pytest.mark.parametrize("selector,expected", [("#visible", "passed"), ("#missing", "failed")])
def test_visibility_emits_bound_observation_and_preserves_failure(
    visible_actions, selector, expected
):
    actions, events = visible_actions
    if expected == "failed":
        with pytest.raises(StepFailed, match="target did not become visible"):
            actions.expect_visible(Target("css", selector), assertion_id="a.ui", claim_id="ui")
    else:
        actions.expect_visible(Target("css", selector), assertion_id="a.ui", claim_id="ui")
    observations = [event for event in events if event["kind"] == "assertion"]
    assert len(observations) == 1
    assert not assertion_errors(observations[0])
    assert observations[0]["outcome"] == expected
    assert observations[0]["oracle_kind"] == "ui"
    assert "test_ui_assertions.py:" in observations[0]["source"]


def test_transport_failure_is_inconclusive_not_a_product_violation(visible_actions, monkeypatch):
    actions, events = visible_actions

    def disconnected(_target):
        raise RuntimeError("browser transport disconnected")

    monkeypatch.setattr(actions.engine, "expect_visible", disconnected)
    with pytest.raises(StepFailed, match="transport disconnected"):
        actions.expect_visible(Target("css", "#visible"), assertion_id="a.ui", claim_id="ui")
    observation = next(event for event in events if event["kind"] == "assertion")
    assert observation["outcome"] == "inconclusive"


def test_partial_binding_is_rejected_and_unbound_calls_remain_unverified(visible_actions):
    actions, events = visible_actions
    with pytest.raises(ValueError, match="supplied together"):
        actions.expect_visible(Target("css", "#visible"), assertion_id="a.ui")
    assert not events
    actions.expect_visible(Target("css", "#visible"))
    assert not any(event["kind"] == "assertion" for event in events)
