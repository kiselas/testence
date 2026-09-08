from __future__ import annotations

from dataclasses import replace

import pytest

from testence.config import Settings
from testence.engine.playwright_cdp import PlaywrightCdpEngine
from testence.isolation import SeedLifecycle
from testence.isolation import TestNamespace as Namespace
from testence.pytest_plugin import testence_api, testence_auth, testence_engine


def _namespace(**changes: str) -> Namespace:
    base = Namespace(
        project_id="catalog",
        run_id="r-isolation",
        worker_id="gw0",
        case_id="create-widget",
        role="editor",
    )
    return replace(base, **changes)


def test_namespace_separates_project_worker_case_role_and_attempt():
    baseline = _namespace().marker
    dimensions = {
        _namespace(project_id="billing").marker,
        _namespace(run_id="r-next").marker,
        _namespace(worker_id="gw1").marker,
        _namespace(case_id="delete-widget").marker,
        _namespace(role="viewer").marker,
        _namespace(attempt_id="attempt-2").marker,
    }

    assert len(dimensions) == 6
    assert baseline not in dimensions
    assert baseline.startswith("testence-catalog-create-widget-")


def test_seed_lifecycle_has_owner_and_always_cleans_the_exact_marker():
    calls: list[tuple[str, str]] = []

    class Adapter:
        def seed(self, marker, **kwargs):
            calls.append(("seed", marker))
            return {"marker": marker, **kwargs}

        def cleanup(self, marker):
            calls.append(("cleanup", marker))

    with SeedLifecycle(Adapter(), _namespace(), owner="catalog QA") as lifecycle:
        values = lifecycle.seed(name="alpha")
        assert values["name"] == "alpha"

    assert calls == [("seed", _namespace().marker), ("cleanup", _namespace().marker)]
    with pytest.raises(ValueError, match="owner"):
        SeedLifecycle(Adapter(), _namespace(), owner="")


def test_reverse_order_namespaces_never_alias():
    forward = [_namespace(case_id=name).marker for name in ("create", "update", "delete")]
    reverse = [_namespace(case_id=name).marker for name in ("delete", "update", "create")]

    assert reverse == list(reversed(forward))
    assert len(set(forward)) == 3


def test_runtime_modes_are_explicit_and_attach_wins(tmp_path):
    assert Settings.load(tmp_path).execution_mode == "isolated"
    assert Settings.load(tmp_path, execution_mode="warm").execution_mode == "warm"
    assert (
        Settings.load(
            tmp_path, execution_mode="isolated", cdp_url="http://127.0.0.1:9333"
        ).execution_mode
        == "attached"
    )
    with pytest.raises(ValueError, match="execution_mode"):
        Settings.load(tmp_path, execution_mode="shared")


def test_stateful_fixtures_are_function_scoped():
    for fixture in (testence_engine, testence_auth, testence_api):
        marker = getattr(fixture, "_fixture_function_marker", None) or getattr(
            fixture, "_pytestfixturefunction"
        )
        assert marker.scope == "function"


def test_warm_context_reset_has_fresh_state_and_owns_cleanup():
    engine = PlaywrightCdpEngine(headed=False)
    engine.start()
    try:
        engine.add_cookies([{"name": "probe", "value": "one", "url": "https://example.test"}])
        before = engine.browser_manifest()
        assert [cookie["name"] for cookie in engine.cookies()] == ["probe"]

        engine.reset_session()

        after = engine.browser_manifest()
        assert engine.cookies() == []
        assert before["owns_browser"] is after["owns_browser"] is True
        assert before["owns_context"] is after["owns_context"] is True
    finally:
        engine.stop()


def test_attached_reset_never_closes_or_replaces_foreign_context():
    class Context:
        def __init__(self):
            self.closed = 0

        def close(self):
            self.closed += 1

    context = Context()
    engine = PlaywrightCdpEngine(cdp_url="http://127.0.0.1:9333")
    engine._context = context
    engine._owns_context = False

    engine.reset_session()

    assert engine._context is context
    assert context.closed == 0
