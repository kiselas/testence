"""``page_reuse: module``: the tests of a module share one tab and context.

A fresh context and a login per test is the default and stays the default. A
project whose tests of one module run against the same signed-in screen opts into
handing the page on: the next test of the module with the same login takes the tab
over, its buffers cleared and other tabs closed, and the evidence of each test stays
its own.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from testence.evidence import RUN_ID_ENV
from tests.mock_app import PASSWORD, USER, MockApp
from tests.owned_pytest import run_pytest

ROOT = Path(__file__).parents[1]

SUITE = f"""
import pytest

from testence.engine import Target

WHOAMI = Target("css", "#whoami")


def test_a_first(ex, testence_engine):
    ex.goto("/app")
    ex.expect_text(WHOAMI, "signed in as {USER}")
    testence_engine.eval_js("localStorage.setItem('draft', 'x'); window.__mark = 'kept'; 1")
    testence_engine.eval_js("window.open('/app') && 1")


def test_b_takes_the_page_over(ex, testence_engine):
    assert testence_engine.eval_js("window.__mark") == "kept"
    assert testence_engine.page_count() == 1
    assert ex.reset_storage(["draft", "never-set"]) == 1
    assert testence_engine.eval_js("localStorage.getItem('draft')") is None
    ex.expect_text(WHOAMI, "signed in as {USER}")


@pytest.mark.testence(fresh_page=True)
def test_c_opts_out(ex, testence_engine):
    ex.goto("/app")
    assert testence_engine.eval_js("window.__mark || 'none'") == "none"


def test_d_fails(ex, testence_engine):
    ex.goto("/app")
    testence_engine.eval_js("window.__mark = 'failed'; 1")
    assert False, "deliberate"


def test_e_after_a_failure(ex, testence_engine):
    ex.goto("/app")
    assert testence_engine.eval_js("window.__mark || 'none'") == "none"


def test_f_routes(ex, testence_engine):
    ex.route("**/api/v1/nothing", status=204)
    ex.goto("/app")


def test_g_after_a_route(ex, testence_engine):
    ex.goto("/app")
    assert testence_engine.eval_js("window.__mark || 'none'") == "none"
"""

FORM = {"auth": "form", "login_path": "/login", "success_url_contains": "/app"}


def _run(project: Path, config: dict[str, Any], suite: str = SUITE) -> tuple[Any, list[Any]]:
    project.mkdir()
    (project / "test_reuse.py").write_text(suite.lstrip(), encoding="utf-8")
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
    ledgers = sorted((project / "runs").glob("*/run.jsonl"))
    events = (
        [json.loads(line) for line in ledgers[0].read_text(encoding="utf-8").splitlines()]
        if ledgers
        else []
    )
    return result, events


def _phases(events: list[dict[str, Any]], name: str) -> list[str]:
    return [
        e["lifecycle_phase"]
        for e in events
        if str(e.get("test", "")).endswith(name) and e.get("lifecycle_phase")
    ]


def test_module_tests_share_one_page_and_keep_their_own_evidence(tmp_path):
    result, events = _run(tmp_path / "reuse", {**FORM, "page_reuse": "module"})
    assert result.returncode == 1, result.stdout + result.stderr
    assert "1 failed, 6 passed" in result.stdout, result.stdout

    # b takes a's page over: no browser start and no login of its own.
    assert "browser.start" in _phases(events, "test_a_first")
    b = _phases(events, "test_b_takes_the_page_over")
    assert "page.reuse" in b and "browser.start" not in b
    (auth,) = [
        e
        for e in events
        if str(e.get("test", "")).endswith("test_b_takes_the_page_over")
        and e.get("lifecycle_phase") == "auth"
    ]
    assert auth["reused"] is True and auth["duration_ms"] == 0
    # fresh_page, a failed test and a route each end the sharing.
    for name in ("test_c_opts_out", "test_e_after_a_failure", "test_g_after_a_route"):
        assert "browser.start" in _phases(events, name), name
    reasons = [e["reason"] for e in events if e.get("text") == "page not kept"]
    assert "the test failed" in reasons and "the test left route" in reasons

    # Each test's waits are its own: b's ledger has no goto, a's does.
    waits = {e["test"].rsplit("::", 1)[-1]: e["by_op"] for e in events if e["kind"] == "test.waits"}
    assert "goto" in waits["test_a_first"]
    assert "goto" not in waits["test_b_takes_the_page_over"]
    assert "reset_storage" in waits["test_b_takes_the_page_over"]


def test_the_default_is_a_page_per_test(tmp_path):
    suite = """
def test_one(ex):
    ex.goto("/app")


def test_two(ex):
    ex.goto("/app")
"""
    result, events = _run(tmp_path / "default", FORM, suite)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not [e for e in events if e.get("lifecycle_phase") == "page.reuse"]
    assert len([e for e in events if e.get("lifecycle_phase") == "browser.start"]) == 2


def test_an_unknown_page_reuse_value_stops_the_session(tmp_path):
    result, _ = _run(tmp_path / "typo", {"page_reuse": "suite"}, "def test_x():\n    pass\n")
    assert result.returncode != 0
    assert 'page_reuse must be "test" or "module"' in result.stdout + result.stderr
