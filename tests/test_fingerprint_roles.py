"""Role candidates must address the control their fingerprint came from."""

import urllib.parse

import pytest

from testence.engine import Target
from testence.engine.playwright_cdp import PlaywrightCdpEngine

CHECKBOX_HTML = '<label for="agree">Agree</label><input id="agree" type="checkbox">'

CASES = [
    ("checkbox", 'type="checkbox"', "checkbox"),
    ("radio", 'type="radio"', "radio"),
    ("text", 'type="text"', "textbox"),
    ("missing-type", "", "textbox"),
    ("invalid-type", 'type="not-an-input-type"', "textbox"),
    ("email", 'type="email"', "textbox"),
    ("tel", 'type="tel"', "textbox"),
    ("url", 'type="url"', "textbox"),
    ("search", 'type="search"', "searchbox"),
    ("text-list", 'type="text" list="choices"', "combobox"),
    ("search-list", 'type="search" list="choices"', "combobox"),
    ("missing-list", 'type="text" list="not-present"', "textbox"),
    ("empty-list", 'type="text" list=""', "textbox"),
    ("wrong-list-element", 'type="search" list="agree"', "searchbox"),
    ("search-missing-list", 'type="search" list="not-present"', "searchbox"),
    ("search-empty-list", 'type="search" list=""', "searchbox"),
    ("search:escaped", 'type="search" list=""', "searchbox"),
    ("search-explicit", 'type="search" list="" role="searchbox"', "searchbox"),
    ("number", 'type="number"', "spinbutton"),
    ("range", 'type="range"', "slider"),
    ("button", 'type="button" value="Button"', "button"),
    ("submit", 'type="submit" value="Submit"', "button"),
    ("reset", 'type="reset" value="Reset"', "button"),
    ("image", 'type="image" alt="Image"', "button"),
    ("password", 'type="password" value="synthetic-only"', None),
    ("file", 'type="file"', None),
    ("color", 'type="color"', None),
    ("date", 'type="date"', None),
    ("datetime", 'type="datetime-local"', None),
    ("month", 'type="month"', None),
    ("week", 'type="week"', None),
    ("time", 'type="time"', None),
    ("switch", 'type="checkbox" role="switch"', "switch"),
    ("explicit-combo", 'type="text" role="combobox" aria-expanded="false"', "combobox"),
]


@pytest.fixture(scope="module")
def role_engine():
    html = (
        CHECKBOX_HTML
        + '<datalist id="choices"><option value="blue"></datalist>'
        + "".join(
            f'<p><input id="{name}" aria-label="{name}" {attributes}></p>'
            for name, attributes, _ in CASES
        )
        + '<input id="hidden" type="hidden">'
        + '<input type="search" list="" aria-label="unaddressed-search">'
        + '<input type="search" list="" aria-label="testid-search" data-testid="search-hint">'
    )
    engine = PlaywrightCdpEngine(headed=False)
    try:
        engine.start()
        engine.goto("data:text/html," + urllib.parse.quote(html))
        yield engine
    finally:
        engine.stop()


@pytest.mark.parametrize(("name", "attributes", "role"), CASES, ids=[case[0] for case in CASES])
def test_input_roles_generate_a_unique_address_for_the_same_control(
    role_engine, name, attributes, role
):
    css_id = name.replace(":", r"\:")
    original = role_engine.element_fingerprint(Target("css", f"#{css_id}"))
    assert original["role"] == role
    candidate = next(
        row for row in role_engine.candidate_elements() if row["fingerprint"]["id"] == name
    )
    proposed = Target(**candidate["target"])
    role_engine.expect_count(proposed, 1)
    actual = role_engine.element_fingerprint(proposed)
    assert actual["id"] == name
    assert candidate["fingerprint"] == original
    if role is None:
        assert candidate["target"] == {"kind": "css", "value": f"#{name}", "name": None}
    if name in {"wrong-list-element", "search-missing-list", "search-empty-list", "search:escaped"}:
        assert candidate["target"] == {"kind": "css", "value": f"#{css_id}", "name": None}
    assert "synthetic-only" not in str(original)


def test_invalid_search_list_requires_a_stable_address(role_engine):
    candidates = role_engine.candidate_elements()
    assert not any(row["fingerprint"]["ariaLabel"] == "unaddressed-search" for row in candidates)
    candidate = next(
        row for row in candidates if row["fingerprint"]["ariaLabel"] == "testid-search"
    )
    assert candidate["target"] == {"kind": "testid", "value": "search-hint", "name": None}
    target = Target(**candidate["target"])
    role_engine.expect_count(target, 1)
    assert role_engine.element_fingerprint(target) == candidate["fingerprint"]


def test_hidden_input_has_no_fabricated_role_or_visible_candidate(role_engine):
    fingerprint = role_engine.element_fingerprint(Target("css", "#hidden"))
    assert fingerprint["role"] is None
    assert not any(row["fingerprint"]["id"] == "hidden" for row in role_engine.candidate_elements())


def test_checkbox_candidate_locates_the_original_control(role_engine):
    original = Target("role", "checkbox", name="Agree")
    fingerprint = role_engine.element_fingerprint(original)
    candidate = next(
        row for row in role_engine.candidate_elements() if row["fingerprint"]["id"] == "agree"
    )
    proposed = Target(**candidate["target"])
    actual = role_engine.element_fingerprint(proposed)
    assert actual.get("id") == "agree", candidate
    assert fingerprint["role"] == "checkbox"
    assert candidate["fingerprint"] == fingerprint
