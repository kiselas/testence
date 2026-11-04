"""A test that talks to the API only starts no browser.

``testence_api`` used to pull in ``testence_engine``: a fresh browser context and a
login through it, even for a test with no ``ex``, which made an API check several
times slower than its HTTP calls. With a scheme that logs in over HTTP the test now
runs browserless; its calls stay evidence, its failure still gets a pack, and its
calls are its wait ledger.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from testence.engine.browserless import BrowserlessSession, BrowserRequired
from testence.evidence import RUN_ID_ENV
from tests.mock_app import PASSWORD, USER, MockApp
from tests.owned_pytest import run_pytest

ROOT = Path(__file__).parents[1]

SUITE = """
from testence.engine import Target

WHOAMI = Target("css", "#whoami")


def test_reads_widget(testence_api):
    for _ in range(3):
        assert testence_api.get("/api/v1/widgets/7").status == 200


def test_fails_after_a_seed(testence_api):
    created = testence_api.post("/api/v1/widgets", {"name": "seed", "cidr": "10.0.0.0/24"})
    assert created.status == 201
    assert testence_api.get("/api/v1/no-such-thing").status == 200, "lookup failed"


def test_browser_and_api(ex, testence_api):
    ex.goto("/app")
    ex.expect_text(WHOAMI, "{user}", intent="the page greets the signed-in user", exact=False)
    assert testence_api.get("/api/v1/auth/me").json["email"] == "{user}"


def test_engine_asked_for_later(request, testence_api):
    assert testence_api.get("/api/v1/auth/me").status == 200
    engine = request.getfixturevalue("testence_engine")
    engine.goto("/app")
    assert "{user}" in engine.read_text(WHOAMI)


def test_browser_asked_for_later(request, testence_api):
    assert testence_api.get("/api/v1/auth/me").status == 200
    ex = request.getfixturevalue("ex")
    ex.goto("/app")
    ex.expect_text(WHOAMI, "{user}", intent="the browser carries the HTTP login", exact=False)
"""


def _run(project: Path, config: dict[str, Any], suite: str) -> tuple[Any, list[dict[str, Any]]]:
    project.mkdir()
    (project / "test_api.py").write_text(suite.replace("{user}", USER), encoding="utf-8")
    (project / "testence.json").write_text(json.dumps(config), encoding="utf-8")
    with MockApp() as app:
        env = os.environ.copy()
        env.pop(RUN_ID_ENV, None)
        env.update(
            PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
            PYTHONPATH=str(ROOT / "src"),
            TESTENCE_BASE_URL=app.base_url,
            TESTENCE_USER=USER,
            TESTENCE_PASSWORD=PASSWORD,
            TESTENCE_DEBUG_PORT="0",
        )
        result = run_pytest(
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
                "-p",
                "no:randomly",
                "--testence-headless",
                "-q",
            ],
            cwd=project,
            env=env,
            timeout=300,
        )
    run_dir = next((project / "runs").glob("*/run.jsonl")).parent
    ledger = "".join(path.read_text(encoding="utf-8") for path in run_dir.glob("run*.jsonl"))
    return result, [json.loads(line) for line in ledger.splitlines()]


def _of(events: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    return [e for e in events if str(e.get("test", "")).endswith(name)]


def test_api_only_tests_start_no_browser(tmp_path):
    result, events = _run(tmp_path / "api", {"auth": "api-session"}, SUITE)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "1 failed, 4 passed" in result.stdout

    browser_phases = {"browser.start", "context.fresh", "browser.worker_start"}
    for name in ("test_reads_widget", "test_fails_after_a_seed"):
        own = _of(events, name)
        started = [e for e in own if e.get("lifecycle_phase") in browser_phases]
        assert started == [], started
        (auth,) = [e for e in own if e.get("lifecycle_phase") == "auth"]
        assert auth["ok"] is True

    # The calls are the API-only test's wait ledger.
    (waits,) = [e for e in _of(events, "test_reads_widget") if e["kind"] == "test.waits"]
    assert waits["by_op"]["api.request"]["n"] == 3
    assert waits["top"][0]["detail"] == "GET /api/v1/widgets/7"

    # A failed API-only test keeps its calls and a failure pack holding them.
    failed = _of(events, "test_fails_after_a_seed")
    calls = [(e["method"], e["status"]) for e in failed if e["kind"] == "api.request"]
    assert calls == [("POST", 201), ("GET", 404)]
    (end,) = [e for e in failed if e["kind"] == "test.end"]
    assert end["status"] == "failed" and end["pack"]
    pack = next((tmp_path / "api" / "runs").glob("*/run.jsonl")).parent / end["pack"]
    history = json.loads((pack / "events.json").read_text(encoding="utf-8"))
    assert [item["event"]["kind"] for item in history["events"]].count("api.request") == 2
    assert json.loads((pack / "browser.json").read_text(encoding="utf-8"))["mode"] == (
        "browserless"
    )

    # A test that also drives the browser logs in through it, as before.
    for name in (
        "test_browser_and_api",
        "test_browser_asked_for_later",
        "test_engine_asked_for_later",
    ):
        own = _of(events, name)
        assert [e for e in own if e.get("lifecycle_phase") == "browser.start"], name


def test_api_only_overhead_is_the_http_calls(tmp_path):
    """An API-only test costs its HTTP calls plus under 100 ms of the framework."""
    suite = """
def test_reads(testence_api):
    for _ in range(5):
        assert testence_api.get("/api/v1/widgets/7").status == 200
"""
    result, events = _run(tmp_path / "speed", {"auth": "api-session"}, suite)
    assert result.returncode == 0, result.stdout + result.stderr
    (end,) = [e for e in events if e["kind"] == "test.end"]
    (auth,) = [e for e in events if e.get("lifecycle_phase") == "auth" and e.get("test")]
    http_ms = auth["duration_ms"] + sum(
        e["duration_ms"] for e in events if e["kind"] == "api.request"
    )
    assert end["duration_ms"] - http_ms < 100, (end["duration_ms"], http_ms)


def test_form_login_still_uses_the_browser(tmp_path):
    suite = """
def test_reads(testence_api):
    assert testence_api.get("/api/v1/auth/me").status == 200
"""
    config = {"auth": "form", "login_path": "/login", "success_url_contains": "/app"}
    result, events = _run(tmp_path / "form", config, suite)
    assert result.returncode == 0, result.stdout + result.stderr
    assert [e for e in events if e.get("lifecycle_phase") == "browser.start"]


def test_browserless_session_names_the_fix_for_a_browser_call():
    session = BrowserlessSession()
    session.add_cookies([{"name": "sid", "value": "v", "domain": "h", "path": "/"}])
    session.set_storage_item("token", "t")
    assert session.cookies()[0]["name"] == "sid"
    assert session.storage_item("token") == "t"
    assert getattr(session, "finish_recording", None) is None
    with pytest.raises(BrowserRequired, match="Request `ex`"):
        session.goto("/app")
