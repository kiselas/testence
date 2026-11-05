"""When the ledger reaches the disk: ``evidence.durability``.

Every event is flushed, so a killed process keeps the ledger. ``fsync`` per event,
two a step, cost about ten seconds of a long run on Windows. By default the writer
syncs at the end of a test, on a failure and at close; ``step`` keeps the old rule.
"""

from __future__ import annotations

import json
import os

import pytest

from testence.config import Settings
from testence.evidence import EvidenceWriter


@pytest.fixture
def fsyncs(monkeypatch):
    calls: list[int] = []
    real = os.fsync

    def counting(descriptor: int) -> None:
        calls.append(descriptor)
        real(descriptor)

    monkeypatch.setattr(os, "fsync", counting)
    return calls


def test_test_durability_syncs_at_most_three_times_for_fifty_events(tmp_path, fsyncs):
    writer = EvidenceWriter(tmp_path, worker="w1")
    fsyncs.clear()  # the empty ledger's creation
    for index in range(50):
        writer.emit("step.end", test="t::a", status="pass", op="click", index=index)
    writer.close()
    assert len(fsyncs) <= 3
    # Flushed on every event all the same: the file holds them all.
    lines = writer.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 50


def test_step_durability_syncs_every_event(tmp_path, fsyncs):
    writer = EvidenceWriter(tmp_path, worker="w1", durability="step")
    fsyncs.clear()
    for index in range(50):
        writer.emit("step.end", test="t::a", status="pass", index=index)
    writer.close()
    assert len(fsyncs) >= 50


@pytest.mark.parametrize(
    ("kind", "payload"),
    [
        ("test.end", {"status": "passed"}),
        ("step.end", {"status": "fail", "error": "not found"}),
        ("test.phase", {"status": "failed", "phase": "call"}),
        ("oracle", {"ok": False}),
        ("oracle", {"outcome": "failed"}),
        ("note", {"text": "final screenshot failed", "error": "TimeoutError"}),
    ],
)
def test_a_failure_or_the_end_of_a_test_is_synced(tmp_path, fsyncs, kind, payload):
    writer = EvidenceWriter(tmp_path, worker="w1")
    writer.emit("step.end", test="t::a", status="pass")
    fsyncs.clear()
    writer.emit(kind, test="t::a", **payload)
    assert len(fsyncs) == 1
    writer.close()


def test_the_prefix_a_failure_pack_binds_is_on_disk(tmp_path, fsyncs):
    writer = EvidenceWriter(tmp_path, worker="w1")
    writer.emit("step.end", test="t::a", status="pass")
    fsyncs.clear()
    checkpoint = writer.ledger_checkpoint()
    assert len(fsyncs) == 1
    assert checkpoint["bytes"] == len(writer.path.read_bytes())
    writer.close()


def test_unknown_durability_is_refused(tmp_path):
    with pytest.raises(ValueError, match="durability"):
        EvidenceWriter(tmp_path, durability="never")


def test_durability_is_validated_in_settings(tmp_path):
    (tmp_path / "testence.json").write_text(
        json.dumps({"evidence": {"durability": "sometimes"}}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="evidence.durability must be test or step"):
        Settings.load(tmp_path).evidence_config()
    (tmp_path / "testence.json").write_text(
        json.dumps({"evidence": {"durability": "step"}}), encoding="utf-8"
    )
    assert Settings.load(tmp_path).evidence_config()["durability"] == "step"
