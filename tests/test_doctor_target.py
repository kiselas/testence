"""``testence doctor --target``: one line with the fix per common misconfiguration.

The app not running, a wrong URL, a missing variable and a wrong password surfaced as
a timeout inside the first test; a wrong password was a raw Playwright wait after
15 s (product review 2026-09-28, P0-8).
"""

from __future__ import annotations

import socket

import pytest

from testence.application import _target_checks
from testence.auth import LoginFailed
from testence.auth.strategies import FormLoginAuth
from testence.config import Settings
from tests.mock_app import PASSWORD, USER, MockApp


@pytest.fixture
def credentials(monkeypatch):
    monkeypatch.setenv("TESTENCE_USER", USER)
    monkeypatch.setenv("TESTENCE_PASSWORD", PASSWORD)


def _checks(tmp_path, **overrides) -> dict[str, dict]:
    settings = Settings.load(tmp_path, timeout_ms=2_000, **overrides)
    return {check["name"]: check for check in _target_checks(settings, lambda _m: None)}


def _unused_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def test_an_app_that_is_not_running_is_named(tmp_path, credentials):
    checks = _checks(tmp_path, base_url=f"http://127.0.0.1:{_unused_port()}", auth="form")
    assert not checks["target"]["ok"]
    assert "cannot reach" in checks["target"]["detail"]
    assert "start the app or correct base_url" in checks["target"]["detail"]
    assert "login" not in checks


def test_a_missing_variable_is_named(tmp_path, monkeypatch):
    monkeypatch.delenv("TESTENCE_USER", raising=False)
    monkeypatch.delenv("TESTENCE_PASSWORD", raising=False)
    with MockApp() as app:
        checks = _checks(tmp_path, base_url=app.base_url, auth="form")
    assert checks["target"]["ok"]
    assert not checks["credentials"]["ok"]
    assert "TESTENCE_USER" in checks["credentials"]["detail"]


def test_a_wrong_password_is_a_named_login_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("TESTENCE_USER", USER)
    monkeypatch.setenv("TESTENCE_PASSWORD", "wrong-password")
    with MockApp() as app:
        checks = _checks(tmp_path, base_url=app.base_url, auth="form")
    assert not checks["login"]["ok"]
    detail = checks["login"]["detail"]
    assert detail.startswith("LoginFailed: login at /login did not complete")
    assert "password field is still visible" in detail
    assert "wrong-password" not in detail


def test_a_working_login_says_what_it_obtained(tmp_path, credentials):
    with MockApp() as app:
        checks = _checks(tmp_path, base_url=app.base_url, auth="form")
    assert checks["login"]["ok"], checks["login"]["detail"]
    assert "session_id" in checks["login"]["detail"]


def test_login_failed_carries_no_password():
    from testence.auth import Credentials

    class _Stuck:
        def goto(self, _path):
            pass

        def fill(self, _target, _value):
            pass

        def click(self, _target):
            pass

        def wait_while_visible(self, _target, timeout_ms):
            raise TimeoutError("Timeout 10ms exceeded")

    auth = FormLoginAuth(Credentials(USER, "s3cret-pw"), timeout_ms=10)
    with pytest.raises(LoginFailed) as caught:
        auth.authenticate(_Stuck())  # type: ignore[arg-type]
    assert "s3cret-pw" not in str(caught.value)
