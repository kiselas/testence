"""Synthetic suite for the live Allure TestOps check (stage 4, L04).

Every behaviour of the TestOps integration has one test here. Metadata uses the raw
marks that ``@allure.*`` decorators produce, so the same file runs under allure-pytest
(to create the "before migration" cases) and under Testence.
"""

import os

import pytest

from testence.engine import Target

allure_label = pytest.mark.allure_label
allure_link = pytest.mark.allure_link


def test_plain():
    assert True


def test_documented():
    """Paying with a saved card charges it once."""
    assert True


def test_assertion_fails():
    total = 9
    assert total == 10, "the basket total is wrong"


def test_code_error_is_broken():
    None.upper()  # type: ignore[attr-defined]


def test_skipped():
    pytest.skip("not applicable to this environment")


@pytest.mark.smoke
@pytest.mark.slow(reason="has an argument, so it is not a tag")
@allure_label("Cart", label_type="feature")
@allure_label("Pay by card", label_type="story")
@allure_label("critical", label_type="severity")
@allure_link("https://tracker.example.test/PAY-7", name="PAY-7", link_type="issue")
@pytest.mark.allure_description("Explicit description wins over the docstring.")
def test_decorated():
    """Docstring that the explicit description replaces."""
    assert True


@pytest.mark.parametrize(
    ("role", "password"),
    [("admin", "sandbox-secret-1"), ("viewer", "sandbox-secret-2")],
    ids=["admin", "viewer"],
)
def test_login(role, password):
    assert role and password


class TestCart:
    def test_add(self):
        assert True

    @pytest.mark.parametrize("amount", [0, 10.5])
    def test_amount(self, amount):
        assert amount >= 0


def test_ui_failure_has_a_pack(ex):
    ex.goto("data:text/html,<h1>Pending</h1>")
    ex.expect_text(Target("css", "h1"), "Paid", intent="the order shows as paid")


def test_killed_job():
    # SANDBOX_KILL=1 imitates a CI job killed by its timeout in the middle of a run.
    if os.environ.get("SANDBOX_KILL") == "1":
        os._exit(1)
    assert True
