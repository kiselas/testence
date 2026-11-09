"""Discovery recognizes kit components and prints the kit line that addresses them."""

from __future__ import annotations

from urllib.parse import quote

import pytest

from testence.config import Settings
from testence.discovery import snapshot
from testence.engine import Target
from testence.engine.playwright_cdp import PlaywrightCdpEngine
from testence.kits import codemirror, koobiq, react_aria, react_select, recognize, xyflow

from .kit_stand import open_stand, stand, stand_engine  # noqa: F401

# A synthetic page with the signs each recognizer looks for, and nothing else.
PAGE = "data:text/html," + quote(
    """<!doctype html><meta charset=utf-8>
<label id=l-hosts>Hosts</label>
<div class="rs"><div class="rs__control"><div class="rs__value-container rs__value-container--is-multi">
  <div class="rs__multi-value"><div class="rs__multi-value__label">h1</div>
  <div role=button aria-label="Remove h1">x</div></div>
  <input role=combobox aria-labelledby=l-hosts></div></div></div>
<div data-slot=form-field><label data-slot=form-field-label>Router <sup>*</sup></label>
  <div role=button data-slot=select-value aria-haspopup=listbox>R1</div></div>
<div data-slot=form-field><label data-slot=form-field-label for=n>VLAN
  <span role=img aria-label="from 1 to 4094">i</span> <sup>*</sup></label>
  <input id=n inputmode=numeric><button aria-controls=n>+</button></div>
<div data-transition=entered class="kbq-sidepanel-x1"><section role=dialog>
  <div class="kbq-dialog-header-ab12">Edit host</div></section></div>
<section role=dialog aria-label="Plain dialog"></section>
<div role=alertdialog class="kbq-toast-z9" aria-labelledby=t1><span id=t1>Saved</span></div>
<table role=grid aria-label=Hosts class="kbq-table-q1"><tr role=row><th role=rowheader>h1</th></tr></table>
<div role=grid aria-label=Labels class="kbq-taggroup-77"><div role=row aria-label=prod>prod</div></div>
<ul role=menu aria-label="Actions of h1" data-collection=c1><li role=menuitem>Edit</li></ul>
<div class="react-flow__node react-flow__node-host" data-id="n-7">web</div>
<div role=grid data-collection=c2><div role=row><span role=rowheader>r1</span></div></div>
<div class="rs"><div class="rs__control"><input role=combobox></div></div>
<table aria-label=Plain><tr><th>not a react-aria grid</th></tr></table>
<div role=tablist aria-label=Bare><button role=tab>A</button></div>
<label><span style="position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)">
  <input type=checkbox></span>Bare box</label>
"""
    + "".join(
        f"""<label data-react-aria-pressable=true><span style="position:absolute;width:1px;height:1px;
    overflow:hidden;clip:rect(0,0,0,0)"><input type=checkbox></span>Opt {i}</label>"""
        for i in range(12)
    )
)


@pytest.fixture
def engine():
    engine = PlaywrightCdpEngine(headed=False, timeout_ms=3_000)
    engine.start()
    try:
        engine.goto(PAGE)
        yield engine
    finally:
        engine.stop()


def test_synthetic_page_components_and_their_kit_lines(engine):
    result = snapshot(engine, Settings())
    lines = {item["python"] for item in result["components"]}
    assert {
        'react_select.multi(ex, "Hosts", prefix="rs")',
        'koobiq.select(ex, "Router", required=True)',
        'koobiq.number_field(ex, "VLAN", hint="from 1 to 4094", required=True)',
        'koobiq.side_panel(ex, "Edit host")',
        "Target('role', 'dialog', name=\"Plain dialog\")",
        "koobiq.toasts(ex)",
        'koobiq.table(ex, "Hosts")',
        'koobiq.tag_group(ex, "Labels")',
        'react_aria.menu(ex, "Actions of h1")',
        'xyflow.node(ex, "n-7", kind="host")',
        # Unnamed: addressed by position, never a kit call without its name.
        'Target(\'css\', "[role=\\"grid\\"]", nth=2)',
        "Target('css', \".rs__control\", nth=1)",
    } <= lines
    # No helper is suggested for markup it cannot address.
    assert not any(name in line for line in lines for name in ('"Plain"', '"Bare"', '"Bare box"'))
    assert not any("react_aria.table" in line for line in lines)
    # One kind cannot crowd out the rest.
    kinds = [item["kind"] for item in result["components"]]
    assert kinds.count("react_aria.checkbox") == recognize.PER_KIND
    by_kind = {item["kind"]: item for item in result["components"]}
    assert by_kind["koobiq.toasts"]["titles"] == ["Saved"]
    assert by_kind["koobiq.side_panel"]["transition"] == "entered"
    assert by_kind["koobiq.select"]["import"] == "from testence.kits import koobiq"
    # The elements list is unchanged: components sit next to the Targets.
    assert result["elements"]


def test_every_synthetic_line_runs(engine, tmp_path):
    """Each printed line evaluates; the positional ones address exactly one element."""
    from testence.dsl import Actions
    from testence.evidence import EvidenceWriter

    ex = Actions(engine, EvidenceWriter(tmp_path / "evidence"), "synthetic")
    namespace = {
        "ex": ex,
        "koobiq": koobiq,
        "react_aria": react_aria,
        "react_select": react_select,
        "xyflow": xyflow,
        "Target": Target,
    }
    for item in snapshot(engine, Settings())["components"]:
        value = eval(item["python"], namespace)  # noqa: S307 - our own printed line
        if isinstance(value, Target) and value.nth is not None:
            assert engine.count(Target(value.kind, value.value)) > value.nth, item
            assert item["note"].startswith("no accessible name")


def test_component_names_are_redacted_like_the_rest(engine, monkeypatch):
    monkeypatch.setenv("TESTENCE_SYNTHETIC_SECRET", "Edit host")
    settings = Settings(extra={"evidence": {"redact": {"env": ["TESTENCE_SYNTHETIC_SECRET"]}}})
    result = snapshot(engine, settings)
    assert "Edit host" not in str(result["components"])


def test_malformed_recognizer_output_is_dropped():
    assert recognize.clean([{"key": "x"}, {"kind": "nope", "name": "a"}, "s", None]) == []
    assert recognize.clean({"kind": "koobiq.select"}) == []
    assert recognize.clean([{"kind": "koobiq.select", "name": "Mode"}]) == [
        {"kind": "koobiq.select", "name": "Mode"}
    ]
    # An unnamed entry without a position gets no line rather than one that raises.
    assert recognize.describe([{"kind": "react_aria.table", "name": ""}]) == []
    with pytest.raises(ValueError):
        recognize.python({"kind": "koobiq.tag_group", "name": ""})


def test_every_line_on_the_stand_addresses_a_real_component(stand_engine, tmp_path):  # noqa: F811
    """Round trip: run each printed line and use what it returns on the live stand."""
    ex = open_stand(stand_engine, tmp_path)
    found = snapshot(stand_engine, Settings())["components"]
    lines = {item["python"] for item in found}
    assert {
        'koobiq.select(ex, "Mode")',
        'koobiq.search(ex, "Search routers")',
        'koobiq.checkbox(ex, "Accept terms")',
        'koobiq.switch(ex, "Notifications")',
        'koobiq.tabs(ex, "Router views")',
        'koobiq.tag_group(ex, "Labels")',
        'koobiq.table(ex, "Routers")',
        'react_select.multi(ex, "Targets")',
        'react_select.single(ex, "Zone")',
        'xyflow.node(ex, "h1", kind="host")',
        'koobiq.select(ex, "Color", required=True)',
        "codemirror.editor(ex)",
    } <= lines
    namespace = {
        "ex": ex,
        "koobiq": koobiq,
        "react_aria": react_aria,
        "react_select": react_select,
        "xyflow": xyflow,
        "codemirror": codemirror,
        "Target": Target,
    }
    for item in found:
        component = eval(item["python"], namespace)  # noqa: S307 - our own printed line
        target = getattr(component, "target", None) or getattr(component, "trigger", None)
        if target is None:
            target = getattr(component, "control")
        ex.expect_visible(target, intent=f"{item['python']} is on the page")


def test_open_overlays_are_recognized_on_the_stand(stand_engine, tmp_path):  # noqa: F811
    ex = open_stand(stand_engine, tmp_path)
    ex.click(react_aria.button("Open panel"), intent="open the side panel")
    koobiq.side_panel(ex, "Edit router").wait_open()
    lines = {item["python"] for item in snapshot(stand_engine, Settings())["components"]}
    assert 'koobiq.side_panel(ex, "Edit router")' in lines
    assert 'koobiq.text_field(ex, "Name", required=True)' in lines
    assert 'koobiq.number_field(ex, "VLAN", hint="from 1 to 4094")' in lines
