"""Conformance for the kit gaps a daily suite hit (stage 7, T06), on the real stand.

- a Koobiq dialog whose product draws its own title, and one whose header holds the
  title and a caption;
- a required Koobiq select, without the author saying it is required;
- a react-select whose label is text next to it, not associated with the input;
- a CodeMirror 6 editor: the whole document, a replacement and typing at the caret.
"""

from __future__ import annotations

import json

import pytest

from testence.dsl.steps import StepFailed
from testence.engine import Target
from testence.kits import codemirror, koobiq, react_select, xyflow

from .kit_stand import logged, open_stand, stand, stand_engine  # noqa: F401


@pytest.fixture
def ex(stand_engine, tmp_path):  # noqa: F811
    return open_stand(stand_engine, tmp_path)


def test_a_dialog_titled_by_the_product_is_found_with_header_any(ex):
    ex.click(Target("role", "button", name="Create token"), intent="open the token dialog")
    created = koobiq.dialog(ex, "Agent token created", header="any")
    created.wait_open()
    with pytest.raises(StepFailed):
        # Without header="any" the kit looks only at Koobiq's header, which is absent.
        ex.engine.timeout_ms = 1_000
        ex.expect_visible(koobiq.dialog(ex, "Agent token created").target)
    ex.engine.timeout_ms = 5_000
    created.press("Done")
    logged(ex, "token: done")


def test_a_header_with_a_caption_is_found_by_its_start(ex):
    ex.click(Target("role", "button", name="Publish template"), intent="open publish")
    confirm = koobiq.confirm(ex, "Publish «tpl-one»?", exact=False)
    confirm.accept("Publish")
    logged(ex, "publish: yes")


def test_a_required_select_needs_no_required_argument(ex):
    color = koobiq.select(ex, "Color")
    assert color.name == "Color *"
    color.choose("Green")
    logged(ex, "color: green")
    # The plain select stays plain, and saying it explicitly still works.
    assert koobiq.select(ex, "Mode").name == "Mode"
    assert koobiq.select(ex, "Color", required=True).name == "Color *"


def test_a_select_that_is_not_on_the_page_says_so(ex):
    with pytest.raises(AssertionError, match="no Koobiq select is labelled 'Colour'"):
        koobiq.select(ex, "Colour").name  # noqa: B018 - reading the name is the check


def test_react_select_by_the_text_next_to_it(ex):
    owner = react_select.single(ex, "Owner", nearby=True)
    owner.pick("Development")
    owner.expect_value("Development")
    logged(ex, "owner: dev")
    with pytest.raises(ValueError):
        react_select.single(ex, "Owner", nearby=True, input_id="x")


def test_codemirror_reads_replaces_and_types(ex):
    schema = codemirror.editor(ex, within=Target("css", "#schema"), name="the schema editor")
    assert schema.text() == '{\n  "name": "router"\n}'
    schema.set_text('{\n  "name": "switch"\n}')
    logged(ex, "schema: " + json.dumps('{\n  "name": "switch"\n}'))
    assert schema.text() == '{\n  "name": "switch"\n}'
    ex.press("ControlOrMeta+End", schema.content, intent="go to the end")
    schema.type("[")
    # Typing goes through the editor: an opening bracket gets its closing one.
    schema.expect_text('{\n  "name": "switch"\n}[]')
    with pytest.raises(StepFailed, match="never became the expected text"):
        schema.expect_text("something else", timeout_ms=300)


def test_a_react_flow_node_opens_without_raw_access(ex):
    node = xyflow.node(ex, "h1", kind="host")
    node.open()
    logged(ex, "opened: h1")
    assert "native" not in ex.engine.reuse_blockers()  # type: ignore[attr-defined]
