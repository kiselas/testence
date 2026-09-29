"""Logins Testence does not ship: ``auth: "module:factory"`` and ``storage-state``.

Writing a strategy meant editing Testence's own ``_KNOWN_SCHEMES`` and ``from_settings``;
an SSO, a second factor or a signed request had no home in a project (product review
2026-09-28, P1-8).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from testence.auth import AuthContext, from_settings
from testence.auth.strategies import StorageStateAuth, needs_credentials
from testence.config import Settings
from testence.evidence import RUN_ID_ENV
from tests.mock_app import PASSWORD, SESSION_COOKIE, SESSION_VALUE, USER, MockApp

ROOT = Path(__file__).parents[1]


class _Engine(SimpleNamespace):
    def __init__(self) -> None:
        super().__init__(cookies_added=[], storage_set={})

    def add_cookies(self, cookies: list[dict[str, Any]]) -> None:
        self.cookies_added.extend(cookies)

    def set_storage_item(self, key: str, value: str) -> None:
        self.storage_set[key] = value


def _settings(tmp_path: Path, **overrides: Any) -> Settings:
    return Settings.load(tmp_path, runs_root=str(tmp_path / "runs"), **overrides)


LOGIN_MODULE = """
from testence.auth import AuthContext


class CompanySso:
    scheme = "company-sso"

    def __init__(self, settings):
        self.settings = settings

    def authenticate(self, engine):
        return AuthContext(headers={"X-Company": "signed"}, scheme=self.scheme)


def build(settings):
    return CompanySso(settings)


class Namespace:
    @staticmethod
    def make(settings):
        return CompanySso(settings)


def not_an_adapter(settings):
    return object()
"""


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "company_login.py").write_text(textwrap.dedent(LOGIN_MODULE), encoding="utf-8")
    return tmp_path


def test_a_project_factory_is_the_login(project):
    adapter = from_settings(_settings(project, auth="company_login:build"))
    context = adapter.authenticate(_Engine())
    assert isinstance(context, AuthContext)
    assert context.scheme == "company-sso" and context.headers == {"X-Company": "signed"}


def test_the_factory_may_be_a_dotted_attribute(project):
    adapter = from_settings(_settings(project, auth="company_login:Namespace.make"))
    assert adapter.scheme == "company-sso"


@pytest.mark.parametrize(
    ("auth", "fragment"),
    [
        ("company_login", "unknown auth scheme"),
        (":build", "must be module:factory"),
        ("company_login:", "must be module:factory"),
        ("no_such_module_xyz:build", "cannot import 'no_such_module_xyz'"),
        ("company_login:missing", "has no 'missing'"),
        ("company_login:not_an_adapter", "must return an object with a `scheme: str`"),
    ],
)
def test_a_mistake_in_the_spec_names_itself(project, auth, fragment):
    with pytest.raises(ValueError, match=fragment):
        from_settings(_settings(project, auth=auth))


def test_only_the_schemes_that_read_a_login_ask_for_credentials():
    assert needs_credentials("form") and needs_credentials("BEARER")
    for scheme in ("none", "", None, "attached", "storage-state", "pkg.login:build"):
        assert not needs_credentials(scheme)


def _state(path: Path, origin: str) -> Path:
    path.write_text(
        json.dumps(
            {
                "cookies": [
                    {"name": "sid", "value": "abc", "domain": "127.0.0.1", "path": "/"},
                ],
                "origins": [
                    {"origin": origin, "localStorage": [{"name": "auth", "value": "tok"}]},
                    {
                        "origin": "https://elsewhere.test",
                        "localStorage": [{"name": "x", "value": "1"}],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_a_storage_state_brings_cookies_and_this_origins_storage(tmp_path):
    path = _state(tmp_path / "state.json", "http://app.test")
    engine = _Engine()
    context = StorageStateAuth(path, "http://app.test/").authenticate(engine)
    assert [c["name"] for c in engine.cookies_added] == ["sid"]
    assert engine.storage_set == {"auth": "tok"}
    assert context.scheme == "storage-state" and context.storage == {"auth": "tok"}


def test_the_scheme_is_configured_by_a_path(tmp_path):
    path = _state(tmp_path / "state.json", "http://app.test")
    settings = _settings(tmp_path, auth="storage-state", base_url="http://app.test")
    with pytest.raises(ValueError, match='needs "storage_state"'):
        from_settings(settings)
    settings.extra["storage_state"] = str(path)
    assert from_settings(settings).scheme == "storage-state"


@pytest.mark.parametrize(
    ("content", "fragment"),
    [(None, "does not exist"), ("{not json", "not readable JSON"), ("[1, 2]", "not a Playwright")],
)
def test_a_bad_storage_state_says_what_to_do(tmp_path, content, fragment):
    path = tmp_path / "state.json"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match=fragment):
        StorageStateAuth(path).authenticate(_Engine())


def test_a_session_exports_as_a_storage_state_that_imports_back(tmp_path):
    session = AuthContext(
        cookies=[{"name": "sid", "value": "abc", "domain": "app.test", "path": "/"}],
        storage={"auth": "tok"},
    )
    path = tmp_path / "state.json"
    path.write_text(json.dumps(session.storage_state("http://app.test/")), encoding="utf-8")
    engine = _Engine()
    restored = StorageStateAuth(path, "http://app.test").authenticate(engine)
    assert restored.cookies == session.cookies and restored.storage == session.storage
    assert AuthContext().storage_state("http://app.test") == {"cookies": [], "origins": []}


SUITE = f"""
from testence.engine import Target


def test_it_starts_signed_in(ex):
    ex.goto("/app")
    ex.expect_text(Target("css", "#whoami"), "signed in as {USER}")
"""

FACTORY = """
from testence.auth import FormLoginAuth


def build(settings):
    return FormLoginAuth(
        settings.credentials(), login_path="/login", success_url_contains="/app"
    )
"""


def _run(project: Path, settings: dict[str, Any]) -> subprocess.CompletedProcess[str]:
    (project / "test_signed_in.py").write_text(SUITE.lstrip(), encoding="utf-8")
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


def test_a_saved_session_signs_a_real_browser_in(tmp_path: Path):
    project = tmp_path / "state"
    project.mkdir()
    (project / "auth.json").write_text(
        json.dumps(
            {
                "cookies": [
                    {
                        "name": SESSION_COOKIE,
                        "value": SESSION_VALUE,
                        "domain": "127.0.0.1",
                        "path": "/",
                    }
                ],
                "origins": [],
            }
        ),
        encoding="utf-8",
    )
    result = _run(project, {"auth": "storage-state", "storage_state": "auth.json"})
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_project_factory_signs_a_real_browser_in(tmp_path: Path):
    project = tmp_path / "factory"
    project.mkdir()
    (project / "project_login.py").write_text(FACTORY.lstrip(), encoding="utf-8")
    result = _run(project, {"auth": "project_login:build"})
    assert result.returncode == 0, result.stdout + result.stderr
