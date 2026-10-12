"""Secrets that reached evidence or exports in 0.1.0a2 (security re-audit, 2026-10-12).

Every case was reproduced with a synthetic secret before the fix; each test here fails
on 0.1.0a2.
"""

from __future__ import annotations

from urllib.parse import quote

import pytest

from testence.auth.base import AuthContext, session_secrets
from testence.config import Settings
from testence.engine.playwright_cdp import PlaywrightCdpEngine
from testence.evidence.sanitize import sanitize_text

SECRET = "SYNTH-SECRET-7f3a9"


@pytest.mark.parametrize(
    "text",
    [
        f"base http://svcuser:{SECRET}@127.0.0.1:8766/app",
        f"Authorization: Token {SECRET}",
        f"Authorization: ApiKey {SECRET}",
        f'Authorization: Digest username="u", response="{SECRET}"',
        f"password = 'correct horse {SECRET} staple'",
        # repr() of a multi-line string: the escaped `\n` used to fuse with the name.
        rf"data='{{\npin: {SECRET}\notp: {SECRET}'",
        rf"headers='X-Trace: 1\nsession: {SECRET}'",
        "-----BEGIN RSA PRIVATE KEY-----\nMIIBOgIBAAJBAK"
        + SECRET
        + "\n-----END RSA PRIVATE KEY-----",
        "stripe sk_live_" + SECRET.replace("-", "") + "abc",
        "google AIza" + "A" * 35,
    ],
)
def test_credential_forms_are_redacted(text):
    safe = sanitize_text(text)
    assert SECRET not in safe and "AIza" + "A" * 35 not in safe, safe
    assert "<redacted>" in safe


def test_a_known_secret_is_redacted_in_encoded_forms_too():
    secret = 'SYNTH-S&Y#N@TH "q" \\ x/y+z'
    text = (
        f"q={quote(secret, safe='')} raw={secret!r} json=" + '"SYNTH-S&Y#N@TH \\"q\\" \\\\ x/y+z"'
    )
    safe = sanitize_text(text, secrets=[secret])
    assert "SYNTH" not in safe, safe


def test_ordinary_text_is_left_alone():
    text = "name: Ivan, role: admin, url http://127.0.0.1:8000/app?page=2"
    assert sanitize_text(text) == text


def test_settings_describe_drops_the_password_of_base_url():
    settings = Settings(base_url=f"http://svcuser:{SECRET}@127.0.0.1:8766/app")
    assert settings.describe()["base_url"] == "http://127.0.0.1:8766/app"


def test_session_cookies_and_stored_tokens_are_secrets_of_the_run():
    context = AuthContext(
        cookies=[{"name": "sid", "value": "sess-abc123456"}, {"name": "lang", "value": "en"}],
        headers={"Authorization": f"Bearer {SECRET}"},
        storage={"access_token": "tok-" + SECRET, "theme": "dark"},
    )
    found = set(session_secrets(context))
    assert {"sess-abc123456", f"Bearer {SECRET}", SECRET, "tok-" + SECRET} <= found
    assert "en" not in found and "dark" not in found


_FORM = """<!doctype html><meta charset="utf-8"><form>
<label>Passwort <input type="password" id="p1"></label>
<label>Пароль <input type="password" id="p2"></label>
<label>Password confirmation <input type="password" id="p3"></label>
<label>Recovery code <input autocomplete="one-time-code" id="otp"></label>
<label>City <input id="city"></label>
</form>"""


def test_aria_evidence_never_shows_a_password_or_one_time_code_field_value():
    """Label-based redaction missed `Passwort`, `Пароль` and `Password confirmation`, so
    the value reached aria.txt, the MCP snapshot and every export."""
    engine = PlaywrightCdpEngine(headed=False)
    engine.start()
    try:
        engine.goto("data:text/html;charset=utf-8," + quote(_FORM))
        page = engine.native_page()
        for selector, value in (
            ("#p1", "SYNTH-PW-ONE"),
            ("#p2", "SYNTH-PW-TWO"),
            ("#p3", "SYNTH-PW-THREE"),
            ("#otp", "SYNTH-OTP-77"),
            ("#city", "Lisbon"),
        ):
            page.fill(selector, value)
        tree = engine.aria_snapshot()
    finally:
        engine.stop()
    assert "SYNTH" not in tree, tree
    assert "Lisbon" in tree
