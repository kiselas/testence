"""The API-oracle primitive, tested where writing data is safe.

Three cases, one per failure mode it exists to catch: a save that agrees, a save
whose UI shows something the server never stored, and a save the front end refused
to send at all.
"""

from __future__ import annotations

import pytest

from testence.api import ApiClient
from testence.auth import ApiSessionAuth, Credentials
from testence.dsl import Actions
from testence.engine import Target, worker_port_offset
from testence.engine.playwright_cdp import PlaywrightCdpEngine
from testence.evidence import EvidenceWriter
from testence.oracle import OracleFailed, save_and_verify

from .mock_app import PASSWORD, USER, MockApp

NAME = Target("css", "#name")
CIDR = Target("css", "#cidr")
SAVE = Target("role", "button", name="Save")
SAVED = Target("css", "#saved")
ERROR = Target("css", "#error")

CREDS = Credentials(USER, PASSWORD, source="test-fixture")


@pytest.fixture(scope="module")
def app():
    with MockApp() as mock:
        yield mock


@pytest.fixture
def session(app, tmp_path):
    engine = PlaywrightCdpEngine(
        base_url=app.base_url,
        headed=False,
        api_prefix="/api/",
        debug_port=9222 + worker_port_offset(),
    )
    engine.start()
    context = ApiSessionAuth(
        CREDS, login_url=f"{app.base_url}/api/v1/auth/login"
    ).authenticate(engine)
    writer = EvidenceWriter(tmp_path, worker="")
    actions = Actions(engine, writer, "oracle_case")
    yield actions, ApiClient(app.base_url, context)
    writer.close()
    engine.stop()


def _saved_view(actions: Actions) -> dict:
    """What the page claims it saved."""
    element = actions.engine.eval_js(
        """() => {
            const el = document.getElementById('saved');
            return el ? {id: el.dataset.id || null, cidr: el.dataset.cidr || null} : {};
        }"""
    )
    return element


def test_consistent_save_passes(session):
    actions, api = session
    actions.goto("/widgets/new", intent="open the create form")
    actions.fill(NAME, "alpha", intent="name the widget")
    actions.fill(CIDR, "10.1.2.0/24", intent="enter a valid CIDR")

    def ui_view() -> dict:
        return {"cidr": _saved_view(actions)["cidr"]}

    def api_view() -> dict:
        widget_id = _saved_view(actions)["id"]
        return api.get(f"/api/v1/widgets/{widget_id}").raise_for_status().json

    diffs = save_and_verify(actions, SAVE, name="widget", ui_view=ui_view,
                            api_view=api_view, expect_request="/api/v1/widgets")
    assert diffs == []


def test_ui_showing_a_value_the_server_never_stored_is_caught(session):
    """The bug class UI tests exist for: the page displays one thing, the server
    holds another, and every API-only test passes."""
    actions, api = session
    actions.goto("/widgets/new?drift=1", intent="open the create form (drifting build)")
    actions.fill(NAME, "beta", intent="name the widget")
    actions.fill(CIDR, "10.3.4.0/24", intent="enter a valid CIDR")

    def ui_view() -> dict:
        return {"cidr": _saved_view(actions)["cidr"]}

    def api_view() -> dict:
        widget_id = _saved_view(actions)["id"]
        return api.get(f"/api/v1/widgets/{widget_id}").raise_for_status().json

    with pytest.raises(OracleFailed, match="cidr"):
        save_and_verify(actions, SAVE, name="widget", ui_view=ui_view,
                        api_view=api_view, expect_request="/api/v1/widgets")


def test_client_validation_blocking_the_request_is_reported(session):
    """When client-side validation rejects input, no request leaves the browser —
    and the oracle must say exactly that instead of timing out on a missing entity."""
    actions, api = session
    actions.goto("/widgets/new", intent="open the create form")
    actions.fill(NAME, "gamma", intent="name the widget")
    actions.fill(CIDR, "not-a-cidr", intent="enter an invalid CIDR")

    with pytest.raises(AssertionError, match="nothing reached the server"):
        save_and_verify(actions, SAVE, name="widget",
                        ui_view=lambda: {}, api_view=lambda: {},
                        expect_request="/api/v1/widgets")
    assert "CIDR looks wrong" in actions.engine.read_text(ERROR)


def test_oracle_event_lands_in_the_ledger(session):
    actions, api = session
    actions.goto("/widgets/new", intent="open the create form")
    actions.fill(NAME, "delta", intent="name the widget")
    actions.fill(CIDR, "10.5.6.0/24", intent="enter a valid CIDR")

    def ui_view() -> dict:
        return {"cidr": _saved_view(actions)["cidr"]}

    def api_view() -> dict:
        widget_id = _saved_view(actions)["id"]
        return api.get(f"/api/v1/widgets/{widget_id}").raise_for_status().json

    save_and_verify(actions, SAVE, name="widget", ui_view=ui_view, api_view=api_view)
    ledger = (actions.writer.run_dir / "run.jsonl").read_text(encoding="utf-8")
    assert '"kind":"oracle"' in ledger and '"ok":true' in ledger
