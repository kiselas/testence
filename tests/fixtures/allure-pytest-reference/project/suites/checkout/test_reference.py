"""Reference suite for allure-pytest identity compatibility.

Written with the raw marks that ``@allure.*`` decorators produce (allure_pytest.helper:
``allure_label(value, label_type=...)``, ``allure_link(url, name=..., link_type=...)``,
``allure_description(text)``, ``__allure_display_name__``), so it runs with or without
allure-pytest installed and both tools read exactly the same metadata.
"""

import pytest

allure_label = pytest.mark.allure_label
allure_link = pytest.mark.allure_link


def test_plain():
    assert True


def test_documented():
    """Paying with a saved card charges it once."""
    assert True


@pytest.mark.smoke
@pytest.mark.slow(reason="has an argument, so it is not a tag")
@allure_label("Cart", label_type="feature")
@allure_label("Pay by card", label_type="story")
@allure_label("critical", label_type="severity")
@allure_label("1042", label_type="as_id")
@allure_label("payments", label_type="layer")
@allure_link("https://tracker.example.test/PAY-7", name="PAY-7", link_type="issue")
@allure_link("https://tms.example.test/case/1042", name="TMS-1042", link_type="tms")
@pytest.mark.allure_description("Explicit description wins over the docstring.")
def test_decorated():
    """Docstring that the explicit description replaces."""
    assert True


@pytest.mark.parametrize(("role", "attempts"), [("admin", 1), ("viewer", 3)])
def test_parametrized(role, attempts):
    assert role and attempts


@pytest.mark.parametrize("role", ["admin", "guest"])
def test_titled(role):
    assert role


test_titled.__allure_display_name__ = "Signs in as {role}"


class TestBasket:
    def test_method(self):
        assert True

    class TestNested:
        @pytest.mark.parametrize("amount", [0, 10.5])
        def test_nested(self, amount):
            assert amount is not None
