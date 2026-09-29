"""End-to-end shape of a real project's suite: config → form login → UI + oracle.

Runs against the bundled mock app, so it needs no external application:

    pytest examples/test_login_flow.py --testence-headless

It demonstrates the intended division of labour: the UI is driven through the DSL,
and the API is used only as an oracle — reading back what the UI claims.
"""

from __future__ import annotations

import pytest

from testence.api import ApiClient
from testence.auth import Credentials, FormLoginAuth
from testence.engine import Target
from testence.oracle import ExpectedState, OracleFailed
from tests.mock_app import PASSWORD, USER, MockApp

WHOAMI = Target("css", "#whoami")
EMAIL = Target("placeholder", "email")
PASSWORD_FIELD = Target("css", "input[type=password]")
SUBMIT = Target("role", "button", name="Sign in")


@pytest.fixture(scope="module")
def app():
    with MockApp() as mock:
        yield mock


@pytest.fixture
def signed_in(ex, testence_engine, app):
    """Log in through the real form — the default strategy — and hand back an API
    client on the very same session."""
    testence_engine.base_url = app.base_url
    with ex.step("sign in through the login form"):
        context = FormLoginAuth(
            Credentials(USER, PASSWORD, source="example"),
            login_path="/login",
            success_target=WHOAMI,
        ).authenticate(testence_engine)
    return ApiClient(app.base_url, context)


def test_login_form_grants_access(ex, signed_in):
    # The only substring assertion in the repository, and it says so: a greeting
    # legitimately wraps the name in other words.
    ex.expect_text(WHOAMI, USER, intent="dashboard greets the signed-in user", exact=False)


def test_ui_and_api_agree_on_the_user(ex, signed_in, testence_engine):
    """The API-oracle pattern: read the entity back and compare it with the UI."""
    ui_text = testence_engine.read_text(WHOAMI)
    shown = ui_text.replace("signed in as ", "").strip()
    ex.verify_state(
        "whoami",
        lambda: signed_in.get_fresh("/api/v1/auth/me"),
        ExpectedState.fields("the API knows the user the page shows", {"email": shown}),
    )


def test_widget_oracle_detects_divergence(ex, signed_in):
    """A deliberately wrong expectation, to show what an oracle failure looks like."""
    with pytest.raises(OracleFailed, match="cidr expected '10.0.99.0/24'"):
        ex.verify_state(
            "widget",
            lambda: signed_in.get_fresh("/api/v1/widgets/42"),
            ExpectedState.fields(
                "the widget has the CIDR the form showed", {"cidr": "10.0.99.0/24"}
            ),
            deadline_ms=300,
        )
