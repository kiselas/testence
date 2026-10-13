"""Recorded network mocking: ``ex.route`` (product review 2026-09-28, P1-5).

A test that answers requests itself is legitimate for the UI's behaviour on an error or
an empty list, and dangerous for persistence: a mocked "created" response looks exactly
like the server's, so a check bound to the mutation would prove nothing. The mock is
recorded and refused as proof.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from testence.engine import NetRecord
from testence.engine.protocol import dump_net
from testence.evidence import RUN_ID_ENV
from tests.mock_app import PASSWORD, USER, MockApp
from tests.owned_pytest import run_pytest

ROOT = Path(__file__).parents[1]
FORM = {
    "auth": "form",
    "login_path": "/login",
    "success_url_contains": "/app",
    # save_and_verify_state binds the mutation's response body.
    "extra": {"capture_policy": {"network_bodies": True}},
}

SUITE = """
import pytest

from testence.api import ApiClient
from testence.engine import Target
from testence.oracle import (
    ExpectedState,
    OracleFailed,
    RequestExpectation,
    save_and_verify_state,
)

FAKE = {"id": "w-fake", "name": "edge", "cidr": "10.0.0.0/8"}


def _fill(ex):
    ex.goto("/widgets/new")
    ex.fill(Target("css", "#name"), "edge")
    ex.fill(Target("css", "#cidr"), "10.0.0.0/8")


def _created_id(ex):
    # The mock app numbers widgets per process, so the id is whatever the server said.
    posts = [r for r in ex.engine.network_log() if r.method == "POST"]
    return posts[-1].json_body()["id"]


def test_the_ui_shows_what_the_mock_says(ex):
    ex.route("**/api/v1/widgets", status=201, json=FAKE)
    _fill(ex)
    ex.click(Target("css", "#save-widget"))
    ex.expect_visible(Target("css", "#saved[data-id='w-fake']"))
    records = [r for r in ex.engine.network_log() if r.method == "POST"]
    assert records and all(r.mocked for r in records)


def test_a_mocked_save_cannot_prove_persistence(ex, testence_api):
    ex.route("**/api/v1/widgets", status=201, json=FAKE)
    _fill(ex)
    with pytest.raises(OracleFailed, match="answered by ex.route"):
        save_and_verify_state(
            ex,
            Target("css", "#save-widget"),
            name="widget",
            request=RequestExpectation("/api/v1/widgets", "POST"),
            read=lambda: testence_api.get_fresh("/api/v1/widgets/w-fake"),
            expected=ExpectedState.fields("the widget is stored", {"name": "edge"}),
            deadline_ms=300,
        )


def test_an_unmocked_save_is_still_proved(ex, testence_api):
    _fill(ex)
    save_and_verify_state(
        ex,
        Target("css", "#save-widget"),
        name="widget",
        request=RequestExpectation("/api/v1/widgets", "POST"),
        read=lambda: testence_api.get_fresh(f"/api/v1/widgets/{_created_id(ex)}"),
        expected=ExpectedState.fields("the widget is stored", {"name": "edge"}),
    )


def test_an_aborted_request_is_recorded_as_failed(ex):
    ex.route("**/api/v1/widgets", abort=True)
    _fill(ex)
    ex.click(Target("css", "#save-widget"))
    assert not ex.engine.wait_for_response("/api/v1/widgets", method="POST", timeout_ms=500)
"""


def test_a_mocked_record_says_so_in_the_pack():
    record = NetRecord("POST", "http://x/api/w", 201, 0, 1, mocked=True)
    plain = NetRecord("GET", "http://x/api/w", 200, 0, 1)
    lines = [json.loads(line) for line in dump_net([record, plain]).splitlines()]
    assert lines[0]["mocked"] is True and "mocked" not in lines[1]


def test_route_arguments_are_checked(tmp_path):
    from types import SimpleNamespace

    from testence.dsl import Actions

    engine = SimpleNamespace(capabilities=lambda: frozenset({"browser.network_mock"}))
    actions = Actions(engine, SimpleNamespace(emit=lambda *a, **k: None), "t")
    with pytest.raises(ValueError, match="json or body"):
        actions.route("**/x", json={}, body="{}")
    with pytest.raises(ValueError, match="abort has no response body"):
        actions.route("**/x", abort=True, body="x")


NATIVE_SUITE = """
import os
import time
from playwright.sync_api import Page


@pytest.mark.parametrize('scope', ['page', 'context'])
def test_native_fake_save_cannot_prove_persistence(ex, testence_api, monkeypatch, scope):
    # A healthy state existed before Save: a fresh read alone could wrongly prove
    # the mocked mutation. The provenance guard must reject it even in this case.
    stored = testence_api.post('/api/v1/widgets', {'name': 'edge', 'cidr': '10.0.0.0/8'}).json
    assert stored['id']
    if os.environ.get('TESTENCE_SYNTHETIC_PROVENANCE_MUTANT') == '1':
        monkeypatch.setattr(ex.engine, '_record_native_mock', lambda *args: None)

    def fake(route):
        if route.request.method == 'POST':
            route.fulfill(status=201, json=stored)
        else:
            # A browser GET on this path would return a different fake entity.
            route.fulfill(json=FAKE)

    with ex.native('register a native fabricated save') as page:
        assert isinstance(page, Page)
        owner = page if scope == 'page' else page.context
        owner.route('**/api/v1/widgets**', fake)
    _fill(ex)
    with pytest.raises(OracleFailed, match='answered by'):
        save_and_verify_state(
            ex, Target('css', '#save-widget'), name='native widget',
            request=RequestExpectation('/api/v1/widgets', 'POST'),
            read=lambda: testence_api.get_fresh('/api/v1/widgets/' + stored['id']),
            expected=ExpectedState.fields('stored', {'name': 'edge'}, entity_id=stored['id']),
            deadline_ms=300,
        )
    ex.expect_visible(Target('css', "#saved[data-id='" + stored['id'] + "']"))
    fresh = testence_api.get_fresh('/api/v1/widgets/' + stored['id'])
    assert fresh.status == 200
    assert fresh.json == stored
    assert fresh.json != FAKE
    records = [r for r in ex.engine.network_log() if r.method == 'POST']
    assert records and records[-1].mocked


@pytest.mark.parametrize('scope', ['page', 'context'])
def test_native_abort_is_marked_even_without_a_response(ex, scope):
    with ex.native('abort a native save') as page:
        owner = page if scope == 'page' else page.context
        owner.route('**/api/v1/widgets', lambda route: route.abort())
    _fill(ex)
    ex.click(Target('css', '#save-widget'))
    assert ex.engine.wait_for_request('/api/v1/widgets', method='POST', timeout_ms=500)
    # The abort is marked mocked before dispatch; Playwright's requestfailed event that
    # fills failure can land after a fixed pause on a slow runner, so wait for it.
    deadline = time.monotonic() + 10
    while True:
        records = [r for r in ex.engine.network_log() if r.method == 'POST']
        if (records and records[-1].failure) or time.monotonic() > deadline:
            break
        ex.engine.settle(100)
    assert records and records[-1].mocked and records[-1].failure


@pytest.mark.parametrize('scope', ['page', 'context'])
@pytest.mark.parametrize('method', ['continue_', 'fallback'])
def test_native_passthrough_is_real_backend_evidence(ex, testence_api, scope, method):
    with ex.native('observe without replacing the response') as page:
        owner = page if scope == 'page' else page.context
        owner.route('**/api/v1/widgets', lambda route: getattr(route, method)())
    test_an_unmocked_save_is_still_proved(ex, testence_api)
    assert not any(r.mocked for r in ex.engine.network_log())


@pytest.mark.parametrize('scope', ['page', 'context'])
def test_native_unroute_keeps_the_original_handler_identity(ex, testence_api, scope):
    def fake(route, request):
        route.fulfill(status=201, json=FAKE)

    with ex.native('register and remove the same handler') as page:
        owner = page if scope == 'page' else page.context
        owner.route('**/api/v1/widgets', fake, times=1)
        owner.unroute('**/api/v1/widgets', fake)
    test_an_unmocked_save_is_still_proved(ex, testence_api)
    assert not any(r.mocked for r in ex.engine.network_log())
"""


def _run(
    project: Path, *, native: bool = False, mutant: bool = False
) -> subprocess.CompletedProcess[str]:
    suite = SUITE + NATIVE_SUITE if native else SUITE
    (project / "test_route.py").write_text(suite.lstrip(), encoding="utf-8")
    (project / "testence.json").write_text(json.dumps(FORM), encoding="utf-8")
    with MockApp() as app:
        env = os.environ.copy()
        env.pop(RUN_ID_ENV, None)
        env.update(
            PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
            PYTHONPATH=str(ROOT / "src"),
            TESTENCE_BASE_URL=app.base_url,
            TESTENCE_USER=USER,
            TESTENCE_PASSWORD=PASSWORD,
        )
        # This switch belongs only to the generated synthetic test, never to the
        # package: deliberately disable the instance's provenance tracker.
        env["TESTENCE_SYNTHETIC_PROVENANCE_MUTANT"] = "1" if mutant else "0"
        return run_pytest(
            [
                sys.executable,
                "-m",
                "pytest",
                "-p",
                "testence.pytest_plugin",
                "--rootdir",
                str(project),
                "-p",
                "no:cacheprovider",
                "--testence-headless",
                "-q",
                *(["-k", "test_native_fake_save_cannot_prove_persistence"] if mutant else []),
            ],
            cwd=project,
            env=env,
            timeout=300,
        )


def test_mocking_in_a_real_browser(tmp_path: Path):
    project = tmp_path / "mocked"
    project.mkdir()
    result = _run(project)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "4 passed" in result.stdout
    ledger = next((project / "runs").glob("*/run.jsonl")).read_text(encoding="utf-8")
    events: list[dict[str, Any]] = [json.loads(line) for line in ledger.splitlines() if line]
    mocked = [event for event in events if event["kind"] == "network.mocked"]
    assert len(mocked) == 3
    assert {event["outcome"] for event in mocked} == {"201", "abort"}
    assert all(event["pattern"] == "**/api/v1/widgets" for event in mocked)


def test_native_mocking_in_a_real_browser(tmp_path: Path):
    project = tmp_path / "native-mocked"
    project.mkdir()
    result = _run(project, native=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "14 passed" in result.stdout
    ledger = next((project / "runs").glob("*/run.jsonl")).read_text(encoding="utf-8")
    events = [json.loads(line) for line in ledger.splitlines() if line]
    mocked = [
        event
        for event in events
        if event["kind"] == "network.mocked" and event.get("source") == "native"
    ]
    assert len(mocked) == 4
    assert {event["outcome"] for event in mocked} == {"201", "abort"}
    assert all(event["source"] == "native" for event in mocked)


def test_native_provenance_controls_detect_a_disabled_tracker(tmp_path: Path):
    project = tmp_path / "mutation-control"
    project.mkdir()
    result = _run(project, native=True, mutant=True)
    assert result.returncode == 1, result.stdout + result.stderr
    # Count the tracebacks, not the short summary: pytest truncates summary lines to the
    # terminal width locally and prints them whole under CI, which doubled the count there.
    raised = re.findall(r"^E\s+Failed: DID NOT RAISE", result.stdout, re.MULTILINE)
    assert "2 failed" in result.stdout and len(raised) == 2, result.stdout
