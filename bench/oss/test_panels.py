"""UI-only claims against pinned upstream pages; no authentication/backend claim."""

import os
from pathlib import Path

import pytest

from testence.engine import Target

PLAN = str(Path(__file__).with_name("plan.md"))


@pytest.mark.testence(plan=PLAN, case_id="admin-checkbox", claims=["admin.checkbox"])
def test_admin_checkbox(ex):
    ex.goto(os.environ["OSS_ADMINLTE"] + "/forms/elements.html", intent="Open form elements")
    checkbox = Target("role", "checkbox", name="Check me out")
    ex.click(checkbox, intent="Enable the checkbox once")
    ex.expect_visible(
        Target("css", "#exampleCheck1:checked"),
        intent="Selection is visibly checked",
        assertion_id="a.checkbox.on",
        claim_id="admin.checkbox",
    )
    ex.click(checkbox, intent="Disable the checkbox once")
    ex.expect_visible(
        Target("css", "#exampleCheck1:not(:checked)"),
        intent="Selection is cleared",
        assertion_id="a.checkbox.off",
        claim_id="admin.checkbox",
    )


@pytest.mark.testence(plan=PLAN, case_id="admin-radio", claims=["admin.radio"])
def test_admin_radio(ex):
    ex.goto(os.environ["OSS_ADMINLTE"] + "/forms/elements.html", intent="Open radio controls")
    ex.click(Target("role", "radio", name="Option two"), intent="Choose the second option")
    ex.expect_visible(
        Target("css", "#radio-2:checked"),
        intent="Second option is selected",
        assertion_id="a.radio.on",
        claim_id="admin.radio",
    )
    ex.expect_visible(
        Target("css", "#radio-1:not(:checked)"),
        intent="First option is cleared",
        assertion_id="a.radio.off",
        claim_id="admin.radio",
    )


@pytest.mark.testence(plan=PLAN, case_id="tabler-password", claims=["tabler.password"])
def test_tabler_password(ex):
    ex.goto(os.environ["OSS_TABLER"] + "/sign-in.html", intent="Open sign-in form")
    ex.fill(
        Target("placeholder", "Your password"), "synthetic-only", intent="Enter synthetic password"
    )
    ex.click(Target("role", "button", name="Show password"), intent="Reveal password once")
    ex.expect_visible(
        Target("css", "#signin-password[type=text]"),
        intent="Password is revealed",
        assertion_id="a.password.show",
        claim_id="tabler.password",
    )
    ex.click(Target("role", "button", name="Hide password"), intent="Hide password once")
    ex.expect_visible(
        Target("css", "#signin-password[type=password]"),
        intent="Password is masked",
        assertion_id="a.password.hide",
        claim_id="tabler.password",
    )


@pytest.mark.testence(plan=PLAN, case_id="tabler-recovery", claims=["tabler.recovery"])
def test_tabler_recovery(ex):
    ex.goto(os.environ["OSS_TABLER"] + "/sign-in.html", intent="Open account entry")
    ex.click(Target("role", "link", name="I forgot password"), intent="Navigate to recovery")
    ex.expect_visible(
        Target("role", "heading", name="Forgot password"),
        intent="Recovery form is visible",
        assertion_id="a.recovery",
        claim_id="tabler.recovery",
    )
