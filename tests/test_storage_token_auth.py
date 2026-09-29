"""The same-session oracle on a SPA that keeps its token in browser storage.

The most common modern single-page app logs in through ``fetch``, keeps a JWT in
``localStorage`` and adds it to its own API calls; the browser holds no cookie. The
oracle sent cookies and API headers only, so it read as nobody and every check was
inconclusive on HTTP 401: the product's headline could not be reproduced there
(product review 2026-09-28, P0-5).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from testence.auth.strategies import api_headers_from_storage
from testence.evidence import RUN_ID_ENV
from tests.mock_app import PASSWORD, TOKEN_VALUE, USER, MockApp

ROOT = Path(__file__).parents[1]

SUITE = f"""
from testence.engine import Target
from testence.oracle import ExpectedState


def _knows_the_user(me):
    return me.get("email") == "{USER}"


def test_the_oracle_reads_as_the_signed_in_user(ex, testence_api):
    ex.goto("/spa")
    ex.expect_text(Target("css", "#whoami"), "signed in as {USER}")
    ex.verify_state(
        "current user",
        lambda: testence_api.get_fresh("/api/v1/auth/me"),
        ExpectedState("the API knows who is signed in", _knows_the_user),
        deadline_ms=1_000,
    )
"""


def _run(project: Path, settings: dict) -> subprocess.CompletedProcess[str]:
    (project / "test_spa.py").write_text(SUITE.lstrip(), encoding="utf-8")
    (project / "testence.json").write_text(json.dumps(settings), encoding="utf-8")
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
        return subprocess.run(
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
            ],
            cwd=project,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=300,
        )


SPA = {"auth": "form", "login_path": "/login-spa", "success_url_contains": "/spa"}


def test_the_token_in_local_storage_reaches_the_oracle(tmp_path: Path):
    project = tmp_path / "bridged"
    project.mkdir()
    bridge = {"api_auth_from_storage": {"key": "auth", "field": "access_token"}}
    result = _run(project, {**SPA, **bridge})
    assert result.returncode == 0, result.stdout + result.stderr
    ledger = next((project / "runs").glob("*/run.jsonl")).read_text(encoding="utf-8")
    assert TOKEN_VALUE not in ledger


def test_without_the_bridge_the_inconclusive_read_names_it(tmp_path: Path):
    project = tmp_path / "unbridged"
    project.mkdir()
    result = _run(project, SPA)
    assert result.returncode == 1
    assert "HTTP 401" in result.stdout and "api_auth_from_storage" in result.stdout


class _Storage:
    def __init__(self, items: dict[str, str]) -> None:
        self.items = items

    def storage_item(self, key: str, *, session: bool = False) -> str | None:
        return self.items.get(key)

    def storage_keys(self, *, session: bool = False) -> list[str]:
        return sorted(self.items)


def test_a_missing_key_or_field_says_what_is_there():
    engine = _Storage({"auth": json.dumps({"token": "t"}), "theme": "dark"})
    with pytest.raises(RuntimeError, match=r"no 'session'.*keys there: \['auth', 'theme'\]"):
        api_headers_from_storage({"key": "session"}, engine, timeout_ms=0)
    with pytest.raises(RuntimeError, match=r"no field 'access_token'; found: \['token'\]"):
        api_headers_from_storage({"key": "auth", "field": "access_token"}, engine, timeout_ms=0)
    assert api_headers_from_storage(
        {"key": "auth", "field": "token", "header": "X-Auth", "format": "{token}"},
        engine,
        timeout_ms=0,
    ) == {"X-Auth": "t"}


def test_a_bad_spec_is_a_configuration_error():
    engine = SimpleNamespace()
    with pytest.raises(ValueError, match="needs a key"):
        api_headers_from_storage({}, engine, timeout_ms=0)
    with pytest.raises(ValueError, match="unknown field"):
        api_headers_from_storage({"key": "a", "prefix": "x"}, engine, timeout_ms=0)
    with pytest.raises(ValueError, match="'local' or 'session'"):
        api_headers_from_storage({"key": "a", "storage": "cookie"}, engine, timeout_ms=0)
