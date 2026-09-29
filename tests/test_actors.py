"""More than one user in a test: ``testence_actor(role)`` (product review 2026-09-28, P1-4).

Permissions and "another user sees my change" cannot be tested with one session; the
configured user was the only account a Testence test could be.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from testence.actors import ActorError, Actors, actor_specs
from testence.config import Settings
from testence.evidence import RUN_ID_ENV
from tests.mock_app import PASSWORD, USER, VIEWER, VIEWER_PASSWORD, MockApp

ROOT = Path(__file__).parents[1]

USERS = {
    "admin": {"user_var": "ADMIN_USER", "password_var": "ADMIN_PASSWORD"},
    "viewer": {"user_var": "VIEWER_USER", "password_var": "VIEWER_PASSWORD"},
}


def _settings(tmp_path: Path, **extra: Any) -> Settings:
    settings = Settings.load(tmp_path, auth="form")
    settings.extra.update(extra)
    return settings


def test_the_users_table_is_validated(tmp_path):
    assert actor_specs(_settings(tmp_path, users=USERS)) == USERS
    assert actor_specs(_settings(tmp_path)) == {}
    for bad, fragment in (
        ({"viewer": "someone"}, "must be an object"),
        ({"viewer": {"user_var": "V"}}, "set password_var"),
        ({"viewer": {"user_var": "V", "password_var": "P", "role": "x"}}, "unknown field"),
        ({"two words": {"user_var": "V", "password_var": "P"}}, "short name"),
    ):
        with pytest.raises(ValueError, match=fragment):
            actor_specs(_settings(tmp_path, users=bad))


def test_the_credentials_of_every_role_are_redacted(tmp_path, monkeypatch):
    monkeypatch.setenv("VIEWER_PASSWORD", "hunter2-viewer")
    monkeypatch.setenv("ADMIN_PASSWORD", "hunter2-admin")
    values = _settings(tmp_path, users=USERS).redaction_values()
    assert {"hunter2-viewer", "hunter2-admin"} <= set(values)


def _actors(settings: Settings) -> Actors:
    return Actors(
        settings,
        spawn_browser=lambda: pytest.fail("no browser expected"),
        make_actions=lambda _e: pytest.fail("no actions expected"),
        remember=lambda _v: None,
        note=lambda **_f: None,
    )


def test_an_undeclared_role_lists_the_declared_ones(tmp_path):
    with pytest.raises(ActorError) as caught:
        _actors(_settings(tmp_path, users=USERS))("guest")
    assert "no user 'guest'" in str(caught.value)
    assert "declared: admin, viewer" in str(caught.value)


def test_without_a_login_there_is_no_role_to_repeat(tmp_path):
    settings = Settings.load(tmp_path, auth="none")
    settings.extra["users"] = USERS
    with pytest.raises(ActorError, match="no login to repeat"):
        _actors(settings)("viewer")


SUITE = f"""
import pytest

from testence.engine import Target


def test_each_actor_is_signed_in_as_itself(testence_api, testence_actor):
    viewer = testence_actor("viewer")
    assert testence_api.get("/api/v1/auth/me").raise_for_status().json["email"] == "{USER}"
    assert viewer.api.get("/api/v1/auth/me").raise_for_status().json["email"] == "{VIEWER}"


def test_a_viewer_cannot_do_what_the_admin_can(testence_api, testence_actor):
    viewer = testence_actor("viewer")
    assert testence_api.post("/api/v1/widgets", {{"name": "n", "cidr": "10.0.0.0/8"}}).status == 201
    assert viewer.api.post("/api/v1/widgets", {{"name": "n", "cidr": "10.0.0.0/8"}}).status == 403


def test_the_second_actor_has_a_browser_of_its_own(ex, testence_actor):
    viewer = testence_actor("viewer")
    ex.goto("/app")
    viewer.ex.goto("/app")
    ex.expect_text(Target("css", "#whoami"), "signed in as {USER}")
    viewer.ex.expect_text(Target("css", "#whoami"), "signed in as {VIEWER}")
"""


def _run(project: Path, settings: dict[str, Any]) -> subprocess.CompletedProcess[str]:
    (project / "test_actors.py").write_text(SUITE.lstrip(), encoding="utf-8")
    (project / "testence.json").write_text(
        json.dumps({**settings, "users": USERS}), encoding="utf-8"
    )
    with MockApp() as app:
        env = os.environ.copy()
        env.pop(RUN_ID_ENV, None)
        env.update(
            PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
            PYTHONPATH=str(ROOT / "src"),
            TESTENCE_BASE_URL=app.base_url,
            TESTENCE_USER=USER,
            TESTENCE_PASSWORD=PASSWORD,
            ADMIN_USER=USER,
            ADMIN_PASSWORD=PASSWORD,
            VIEWER_USER=VIEWER,
            VIEWER_PASSWORD=VIEWER_PASSWORD,
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


@pytest.mark.parametrize(
    "settings",
    [
        {"auth": "form", "login_path": "/login", "success_url_contains": "/app"},
        {"auth": "api-session", "api_login_path": "/api/v1/auth/login"},
    ],
    ids=["form", "api-session"],
)
def test_roles_are_separate_sessions(tmp_path: Path, settings: dict[str, Any]):
    project = tmp_path / "actors"
    project.mkdir()
    result = _run(project, settings)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "3 passed" in result.stdout
    ledger = next((project / "runs").glob("*/run.jsonl")).read_text(encoding="utf-8")
    assert VIEWER_PASSWORD not in ledger and PASSWORD not in ledger
    assert '"actor":"viewer"' in ledger
