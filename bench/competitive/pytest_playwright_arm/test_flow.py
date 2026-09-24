"""pytest-playwright arm: the same six steps, idiomatic Playwright for Python."""

from playwright.sync_api import Page, expect


def test_add_a_named_row(page: Page) -> None:
    page.goto("/index.html")
    page.get_by_role("button", name="inc", exact=True).click()
    expect(page.locator("#count")).to_have_text("1")
    page.get_by_placeholder("name", exact=True).fill("alice")
    page.get_by_role("button", name="add", exact=True).click()
    expect(page.locator("#list li").last).to_have_text("row-alice")
