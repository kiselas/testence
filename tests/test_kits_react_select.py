"""Conformance: testence.kits.react_select against react-select 5 on the stand."""

from __future__ import annotations

import pytest

from testence.dsl.steps import StepFailed
from testence.kits import react_select

from .kit_stand import logged, open_stand, stand, stand_engine  # noqa: F401


@pytest.fixture
def ex(stand_engine, tmp_path):  # noqa: F811
    return open_stand(stand_engine, tmp_path)


def test_multi_reads_groups_disabled_and_an_unoffered_chip_in_one_read(ex):
    targets = react_select.multi(ex, "Targets")
    targets.expect_chips(["retired.example.test"])
    targets.open()
    state = targets.state()
    assert state["groups"] == ["Internal", "External"]
    by_label = {option["label"]: option for option in state["options"]}
    assert by_label["delta.example.test"]["group"] == "External"
    assert by_label["gamma.example.test"]["disabled"] is True
    # A saved value the list no longer offers still renders a chip.
    assert state["unoffered"] == ["retired.example.test"]


def test_multi_pick_remove_and_close_without_escape(ex):
    targets = react_select.multi(ex, "Targets")
    targets.pick("alpha.example.test", "delta.example.test")
    targets.expect_chips(["retired.example.test", "alpha.example.test", "delta.example.test"])
    logged(ex, "targets: retired,alpha,delta")
    assert targets.state()["open"] is False
    targets.remove("retired.example.test")
    targets.expect_chips(["alpha.example.test", "delta.example.test"])
    logged(ex, "targets: alpha,delta")


def test_multi_search_filters_the_menu(ex):
    targets = react_select.multi(ex, "Targets")
    targets.open()
    targets.search("eps")
    state = targets.state()
    assert [option["label"] for option in state["options"]] == ["epsilon.example.test"]
    targets.pick("epsilon.example.test")
    logged(ex, "targets: retired,epsilon")


def test_disabled_option_cannot_be_picked(ex):
    targets = react_select.multi(ex, "Targets")
    targets.open()
    gamma = targets.option("gamma.example.test")
    ex.expect_attribute(gamma, "aria-disabled", "true", intent="the option is there, disabled")
    # The click itself is refused: the option is found and is not enabled.
    with pytest.raises(
        StepFailed, match=r"(?s)pick \W*gamma\.example\.test.*element is not enabled"
    ):
        targets.pick("gamma.example.test", keep_open=True)
    targets.expect_chips(["retired.example.test"])


def test_single_choose_notice_and_clear(ex):
    zone = react_select.single(ex, "Zone")
    zone.expect_value(None)
    assert zone.state()["placeholder"] == "Select a value"
    zone.open()
    zone.search("nothing-like-this")
    assert targets_notice(zone) == "No values available"
    zone.search("")
    zone.pick("LAN")
    logged(ex, "zone: lan")
    zone.clear()
    logged(ex, "zone: -")


def targets_notice(field: react_select.ReactSelect) -> str | None:
    return field.state()["notice"]


def test_field_by_input_id_is_the_same_field(ex):
    by_label = react_select.single(ex, "Zone")
    by_id = react_select.single(ex, "Zone", input_id="zone-input")
    by_id.pick("WAN")
    by_label.expect_value("WAN")


def test_unknown_field_fails_with_the_count(ex):
    with pytest.raises(AssertionError, match="0 fields match"):
        react_select.multi(ex, "Nope").state()
