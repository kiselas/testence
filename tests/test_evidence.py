import json

import pytest

from testence import SCHEMA_VERSION
from testence.evidence import EvidenceWriter, estimate_tokens
from testence.evidence.events import Event


def test_writer_produces_valid_jsonl(tmp_path):
    with EvidenceWriter(tmp_path, worker="") as writer:
        writer.emit("run.start", fingerprint={"os": "test"})
        writer.emit("test.start", test="t1")
        writer.emit("step.end", test="t1", step="s1", status="ok", duration_ms=12.5)
        writer.emit("run.end", duration_ms=100.0, passed=1, failed=0)

    lines = (writer.run_dir / "run.jsonl").read_text(encoding="utf-8").splitlines()
    docs = [Event.parse(line) for line in lines]
    assert len(docs) == 4
    assert all(d["v"] == SCHEMA_VERSION for d in docs)
    assert [d["seq"] for d in docs] == [1, 2, 3, 4]
    assert docs[2]["test"] == "t1"
    assert docs[2]["duration_ms"] == 12.5


def test_unknown_kind_rejected():
    with pytest.raises(ValueError):
        Event(kind="bogus", run="r")


def test_parse_rejects_foreign_schema():
    with pytest.raises(ValueError):
        Event.parse(json.dumps({"v": "other/9", "kind": "note"}))


def test_utf8_and_lf_line_endings(tmp_path):
    with EvidenceWriter(tmp_path, worker="") as writer:
        writer.emit("note", text="кириллица и → стрелки")
    raw = (writer.run_dir / "run.jsonl").read_bytes()
    assert b"\r\n" not in raw
    assert "кириллица".encode() in raw


def test_token_estimate_monotonic():
    assert estimate_tokens("word " * 100) > estimate_tokens("word")
