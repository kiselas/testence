"""Distinguish actual engine calls from successful generic intent wrappers."""

import json

import pytest

from testence.contracts import DocumentError, validate_document
from testence.dsl import Actions
from testence.dsl.steps import StepFailed
from testence.engine import Capability, Target, UnsupportedCapability
from testence.evidence import EvidenceWriter


class RecordingEngine:
    def capabilities(self):
        return {Capability.DOM}

    def __init__(self):
        self.calls = []

    def click(self, target, *, fast=False):
        self.calls.append(("click", target, fast))

    def element_fingerprint(self, target):
        return None

    def fill(self, target, value, *, fast=False):
        self.calls.append(("fill", target, value, fast))


def test_primitive_completion_is_distinct_from_a_generic_click_intent(tmp_path):
    writer = EvidenceWriter(tmp_path, worker="")
    engine = RecordingEngine()
    actions = Actions(engine, writer, "test_click")
    target = Target("css", "#save")
    with actions.step("Click Save", target):
        pass
    actions.click(target, intent="Click Save")
    events = [json.loads(line) for line in writer.path.read_text(encoding="utf-8").splitlines()]
    assert all("operation" not in event for event in events[:2])
    assert events[2]["operation"]["method"] == "click"
    assert events[2]["operation"]["dispatch"] == "not_called"
    assert events[3]["operation"]["dispatch"] == "returned"
    assert events[3]["operation"]["producer"] == "testence.dsl.steps.Actions.click"
    assert events[3]["operation"]["engine_type"].endswith(".RecordingEngine")
    assert engine.calls == [("click", target, False)]
    for event in events:
        validate_document(event, "evidence.schema.json")
    events[3]["operation"]["dispatch"] = "native_dispatched"
    with pytest.raises(DocumentError):
        validate_document(events[3], "evidence.schema.json")


def _events(writer):
    return [json.loads(line) for line in writer.path.read_text(encoding="utf-8").splitlines()]


@pytest.mark.parametrize("action", ["click", "fill"])
@pytest.mark.parametrize("fast", [False, True])
def test_default_fast_and_input_privacy(tmp_path, action, fast):
    writer = EvidenceWriter(tmp_path, worker="")
    engine = RecordingEngine()
    actions = Actions(engine, writer, "test_operation")
    target = Target("css", "#control")
    if action == "click":
        actions.click(target, fast=fast)
        assert engine.calls == [("click", target, fast)]
    else:
        actions.fill(target, "synthetic-input-value", fast=fast)
        assert engine.calls == [("fill", target, "synthetic-input-value", fast)]
    events = _events(writer)
    assert events[-1]["operation"]["dispatch"] == "returned"
    assert events[0]["weakenings"] == (["fast-actionability"] if fast else [])
    assert "synthetic-input-value" not in writer.path.read_text(encoding="utf-8")


@pytest.mark.parametrize("action", ["click", "fill"])
@pytest.mark.parametrize("failure", ["capability", "lookup", "method"])
def test_failure_distinguishes_no_dispatch_and_a_raised_method(tmp_path, action, failure):
    class FailedEngine(RecordingEngine):
        def __getattribute__(self, name):
            if failure == "lookup" and name in {"click", "fill"}:
                raise RuntimeError("synthetic method lookup failure")
            return super().__getattribute__(name)

        def capabilities(self):
            return set() if failure == "capability" else {Capability.DOM}

        def click(self, *args, **kwargs):
            self.calls.append("invoked")
            raise RuntimeError("synthetic dispatch failure")

        def fill(self, *args, **kwargs):
            self.calls.append("invoked")
            raise RuntimeError("synthetic dispatch failure")

    writer = EvidenceWriter(tmp_path, worker="")
    engine = FailedEngine()
    actions = Actions(engine, writer, "test_operation")
    target = Target("css", "#control")
    with pytest.raises(UnsupportedCapability if failure == "capability" else StepFailed):
        if action == "click":
            actions.click(target)
        else:
            actions.fill(target, "input")
    assert _events(writer)[-1]["operation"]["dispatch"] == (
        "raised" if failure == "method" else "not_called"
    )
    assert engine.calls == (["invoked"] if failure == "method" else [])


def test_legacy_fill_and_nested_generic_wrapper(tmp_path):
    class LegacyEngine(RecordingEngine):
        def fill(self, target, value):
            self.calls.append((target, value))

    writer = EvidenceWriter(tmp_path, worker="")
    engine = LegacyEngine()
    actions = Actions(engine, writer, "test_operation")
    target = Target("css", "#control")
    with actions.step("Composite"):
        actions.fill(target, "legacy-input")
    events = _events(writer)
    assert "operation" not in events[0] and "operation" not in events[-1]
    assert events[2]["operation"]["dispatch"] == "returned"
    assert events[2]["depth"] == 1
    assert engine.calls == [(target, "legacy-input")]


def test_descriptor_survives_pack_projection_and_manifest(tmp_path):
    from testence.triage import assemble_pack
    from tests.test_pack import FakeEngine

    class PackEngine(FakeEngine, RecordingEngine):
        pass

    writer = EvidenceWriter(tmp_path, worker="")
    engine = PackEngine()
    engine.calls = []
    actions = Actions(engine, writer, "test_operation")
    actions.click(Target("css", "#save"))
    pack = assemble_pack(engine, writer, "test_operation", error="synthetic failed assertion")
    history = json.loads((pack / "events.json").read_text(encoding="utf-8"))
    operation = history["events"][1]["event"]["operation"]
    assert operation["dispatch"] == "returned"
    assert operation["engine_type"].endswith(".PackEngine")
    assert "native_dispatch" not in operation and "trusted_event" not in operation
    manifest = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
    assert "events.json" in {item["path"] for item in manifest["artifacts"]}


def test_native_escape_hatch_is_distinct_from_recorded_primitives(tmp_path):
    class NativeEngine(RecordingEngine):
        def capabilities(self):
            return {Capability.DOM, Capability.NATIVE}

        def native_page(self):
            return self

    writer = EvidenceWriter(tmp_path, worker="")
    engine = NativeEngine()
    actions = Actions(engine, writer, "test_operation")
    with actions.native("Unrecorded click") as page:
        page.click(Target("css", "#save"))
    events = _events(writer)
    assert [event["kind"] for event in events] == ["step.start", "native.used", "step.end"]
    assert all("operation" not in event for event in events)
    assert len(engine.calls) == 1


def test_interrupted_call_has_no_completion_claim(tmp_path):
    class InterruptedEngine(RecordingEngine):
        def click(self, *args, **kwargs):
            self.calls.append("invoked")
            raise KeyboardInterrupt

    writer = EvidenceWriter(tmp_path, worker="")
    engine = InterruptedEngine()
    actions = Actions(engine, writer, "test_operation")
    with pytest.raises(KeyboardInterrupt):
        actions.click(Target("css", "#save"))
    events = _events(writer)
    assert [event["kind"] for event in events] == ["step.start"]
    assert events[0]["operation"]["dispatch"] == "not_called"
    assert engine.calls == ["invoked"]  # start alone cannot describe subsequent dispatch
