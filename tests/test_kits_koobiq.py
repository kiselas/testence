"""Conformance: testence.kits.koobiq and react_aria against the real Koobiq stand."""

from __future__ import annotations

import pytest

from testence.dsl.steps import StepFailed
from testence.engine import Target
from testence.kits import koobiq, react_aria

from .kit_stand import logged, not_logged, open_stand, stand, stand_engine  # noqa: F401


@pytest.fixture
def ex(stand_engine, tmp_path):  # noqa: F811
    return open_stand(stand_engine, tmp_path)


@pytest.fixture(params=["en-US", "ru-RU"])
def ex_any_locale(request, stand_engine, tmp_path):  # noqa: F811
    """The stand in English and in Russian: Koobiq translates its own labels."""
    return open_stand(stand_engine, tmp_path, request.param)


def test_select_choose_names_the_trigger_label_and_value(ex):
    mode = koobiq.select(ex, "Mode")
    mode.expect_value("Choose a mode")
    mode.choose("Safe")
    logged(ex, "mode: safe")
    # The label also names the open list: the trigger is reached through the field.
    mode.open()
    mode.list.expect_selected("Safe")
    ex.click(mode.option("Off"), intent="choose Off")
    mode.expect_value("Off")
    logged(ex, "mode: off")


def test_checkbox_and_switch_click_the_label_not_the_hidden_input(ex):
    terms = koobiq.checkbox(ex, "Accept terms")
    terms.check()
    logged(ex, "terms: true")
    with pytest.raises(StepFailed, match="is not checked yet"):
        terms.check()  # already checked: refuses instead of toggling it off
    terms.uncheck()
    logged(ex, "terms: false")
    notifications = koobiq.switch(ex, "Notifications")
    notifications.check()
    logged(ex, "notifications: true")


def test_tabs_select_shows_the_named_panel(ex):
    views = koobiq.tabs(ex, "Router views")
    views.select("Routes")
    ex.expect_text(views.panel("Routes"), "Static routes")
    logged(ex, "tab: routes")


def test_tooltip_opens_on_hover_without_sleeping(ex):
    koobiq.tooltip(ex, react_aria.button("Help")).expect_text("Opens the user guide")


def test_a_first_hover_on_an_untouched_page_opens_no_tooltip(ex):
    """The trap Tooltip.open avoids: react-aria has seen no pointer yet."""
    ex.engine.timeout_ms = 1_000
    ex.hover(react_aria.button("Help"), intent="hover the trigger straight away")
    with pytest.raises(StepFailed):
        ex.expect_visible(Target("role", "tooltip"))


def test_search_submits_on_enter_only(ex):
    search = koobiq.search(ex, "Search routers")
    ex.fill(search.target, "edge", intent="type without submitting")
    not_logged(ex, "search: edge")
    search.submit("edge-2")
    logged(ex, "search: edge-2")


def test_badge_reports_variant_and_inline_colour(ex):
    health = koobiq.badge(ex, "degraded")
    health.expect_variant("fade-error")
    health.expect_color("rgb(200, 30, 30)")
    assert health.read() == {
        "text": "degraded",
        "variant": "fade-error",
        "color": "rgb(200, 30, 30)",
        "shown": "rgb(200, 30, 30)",
    }


def test_badge_colour_mismatch_reports_what_was_shown(ex):
    ex.engine.timeout_ms = 300
    with pytest.raises(StepFailed, match=r"rgb\(200, 30, 30\)"):
        koobiq.badge(ex, "degraded").expect_color("rgb(0, 0, 0)")


def test_tag_group_is_a_grid_of_rows_and_removes_in_any_locale(ex_any_locale):
    ex = ex_any_locale
    labels = koobiq.tag_group(ex, "Labels")
    labels.expect_tags(2)
    labels.remove("lab")
    labels.expect_tags(1)
    logged(ex, "tags removed: lab")


def test_table_rows_selection_and_row_menu_in_any_locale(ex_any_locale):
    ex = ex_any_locale
    routers = koobiq.table(ex, "Routers")
    routers.expect_rows(3)
    ex.expect_visible(routers.row_checkbox("router-two"), intent="the row's selection box")
    routers.select_row("router-two")
    logged(ex, "selected: r2")
    routers.select_row("router-one")
    logged(ex, "selected: r1,r2")
    routers.unselect_row("router-two")
    logged(ex, "selected: r1")
    routers.row_menu("router-three", "Actions of router-three").choose("Duplicate")
    logged(ex, "row r3: duplicate")
    ex.expect_text(routers.cell("router-two", "paused"), "paused")


def test_checking_the_hidden_row_input_is_the_trap_the_kit_avoids(ex):
    """ex.check on the visually hidden input waits for a hit test the label wins."""
    ex.engine.timeout_ms = 600
    row_input = Target(
        "css", 'input[type="checkbox"]', within=koobiq.table(ex, "Routers").row("router-one")
    )
    with pytest.raises(StepFailed):
        ex.check(row_input)
    not_logged(ex, "selected: r1")


def test_side_panel_waits_for_the_slide_then_edits_and_closes(ex):
    ex.click(react_aria.button("Open panel"), intent="open the side panel")
    panel = koobiq.side_panel(ex, "Edit router")
    panel.wait_open()
    name = panel.field("Name", required=True)
    name.fill("edge-7")
    name.expect_value("edge-7")
    vlan = panel.number_field("VLAN", hint="from 1 to 4094")
    vlan.set(42)
    logged(ex, "vlan: 42")
    panel.press("Save")
    logged(ex, "saved: name=edge-7, vlan=42")


def test_number_field_without_commit_keeps_the_old_value(ex):
    """Typing alone changes the text only; the field's onChange fires on blur."""
    ex.click(react_aria.button("Open panel"), intent="open the side panel")
    panel = koobiq.side_panel(ex, "Edit router")
    panel.wait_open()
    vlan = panel.number_field("VLAN", hint="from 1 to 4094")
    ex.fill(vlan.target, "77", intent="type without leaving the field")
    not_logged(ex, "vlan: 77")
    ex.press("Tab", intent="leave the field")
    logged(ex, "vlan: 77")


def test_side_panel_close_button_is_found_in_any_locale(ex_any_locale):
    ex = ex_any_locale
    ex.click(react_aria.button("Open panel"), intent="open the side panel")
    panel = koobiq.side_panel(ex, "Edit router")
    panel.wait_open()
    panel.close()
    logged(ex, "panel: closed")


def test_required_field_name_carries_the_asterisk(ex):
    ex.click(react_aria.button("Open panel"), intent="open the side panel")
    panel = koobiq.side_panel(ex, "Edit router")
    panel.wait_open()
    ex.expect_count(panel.field("Name").target, 0, intent="the bare label names nothing")
    ex.expect_visible(panel.field("Name", required=True).target)


def test_confirm_by_title_accepts_and_cancels(ex):
    ex.click(react_aria.button("Delete item"), intent="ask to delete")
    koobiq.confirm(ex, "Delete «router-two»").accept("Delete")
    logged(ex, "confirm: delete")
    ex.click(react_aria.button("Delete item"), intent="ask again")
    koobiq.confirm(ex, "Delete «router-two»").cancel("Cancel")
    logged(ex, "confirm: cancel")


def test_confirm_with_another_title_is_not_found(ex):
    ex.engine.timeout_ms = 400
    ex.click(react_aria.button("Delete item"), intent="ask to delete")
    with pytest.raises(StepFailed):
        koobiq.confirm(ex, "Delete «router-one»").accept("Delete")
    not_logged(ex, "confirm: delete")


def test_new_toast_after_a_mark_and_dismiss_in_any_locale(ex_any_locale):
    ex = ex_any_locale
    toasts = koobiq.toasts(ex)
    before = toasts.mark()
    ex.click(react_aria.button("Show toast"), intent="save")
    first = toasts.expect_new(before, "Router saved", status="success")
    first.expect_caption("router-one")
    # The same title again: only the toast after the second mark is new.
    again = toasts.mark()
    ex.click(react_aria.button("Show toast"), intent="save again")
    second = toasts.expect_new(again, "Router saved")
    assert second.target != first.target
    second.dismiss()
    ex.expect_visible(first.target, intent="the first toast stays")
    first.dismiss()
    assert toasts.read() == []


def test_toast_with_the_wrong_status_is_not_taken(ex):
    ex.engine.timeout_ms = 400
    toasts = koobiq.toasts(ex)
    before = toasts.mark()
    ex.click(react_aria.button("Show error"), intent="fail a save")
    with pytest.raises(StepFailed, match="Save failed"):
        toasts.expect_new(before, "Save failed", status="success")
    toasts.expect_new(before, "Save failed", status="error").expect_caption("Request timed out")


def test_no_new_toast_is_a_bounded_negative(ex):
    toasts = koobiq.toasts(ex)
    before = toasts.mark()
    toasts.expect_no_new(before, within_ms=200)
    ex.click(react_aria.button("Show toast"), intent="save")
    with pytest.raises(StepFailed, match="condition held.*Router saved"):
        toasts.expect_no_new(before, within_ms=2_000)


def test_a_zero_window_is_refused_not_turned_into_the_step_budget(ex):
    toasts = koobiq.toasts(ex)
    with pytest.raises(ValueError, match="within_ms"):
        toasts.expect_no_new(toasts.mark(), within_ms=0)
