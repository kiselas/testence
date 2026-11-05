"""Conformance: testence.kits.xyflow against @xyflow/react 12 on the stand."""

from __future__ import annotations

import pytest

from testence.kits import xyflow

from .kit_stand import logged, not_logged, open_stand, stand, stand_engine  # noqa: F401


@pytest.fixture
def ex(stand_engine, tmp_path):  # noqa: F811
    return open_stand(stand_engine, tmp_path)


def test_nodes_are_found_by_id_and_type(ex):
    ex.expect_count(xyflow.nodes("host"), 2, intent="two host nodes")
    xyflow.node(ex, "h1", kind="host").wait_drawn()


def test_single_click_selects_and_double_click_opens(ex):
    web = xyflow.node(ex, "h1", kind="host")
    web.click()
    web.expect_selected()
    not_logged(ex, "opened: h1")
    web.open()
    logged(ex, "opened: h1")


def test_node_menu_action_by_aria_haspopup_and_by_name(ex):
    xyflow.node(ex, "h2", kind="host").action("Copy")
    logged(ex, "node h2: copy")
    xyflow.node(ex, "h1").action("Delete", trigger_name="Menu of web-1")
    logged(ex, "node h1: delete")
