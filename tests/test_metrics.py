import json

import pytest

from testence.evidence import EvidenceWriter, ledger_paths
from testence.identity import source_case_id
from testence.metrics import aggregate, load_run, percentile


def _make_run(tmp_path, name, test_status):
    writer = EvidenceWriter(tmp_path, run_id=name, worker="")
    writer.emit("run.start")
    writer.emit("test.start", test="case_a")
    for i, ms in enumerate([100.0, 200.0, 300.0], start=1):
        writer.emit("step.end", test="case_a", step=f"s{i}", status="ok", duration_ms=ms)
    writer.emit("test.end", test="case_a", status=test_status, duration_ms=1500.0)
    writer.emit("run.end", duration_ms=2000.0, passed=1, failed=0)
    writer.close()
    return writer.run_dir


def test_percentile_bounds():
    assert percentile([], 50) is None
    assert percentile([10.0], 95) == 10.0
    assert percentile([100.0, 200.0, 300.0], 50) == 200.0


def test_aggregate_and_flake_detection(tmp_path):
    run1 = _make_run(tmp_path, "r-1", "pass")
    run2 = _make_run(tmp_path, "r-2", "fail")
    doc = aggregate([run1, run2])
    assert doc["runs"] == 2
    assert doc["step_latency_ms"]["n"] == 6
    assert doc["step_latency_ms"]["p50"] == 200.0
    assert doc["interaction_flake_rate"] == 1.0
    assert doc["flaky_tests"] == [f"unconfigured/{source_case_id('case_a')}/default"]
    assert doc["assurance"]["unverified"] == 1
    assert doc["assurance"]["inconclusive"] == 1


def test_stable_outcomes_not_flaky(tmp_path):
    runs = [_make_run(tmp_path, f"r-{i}", "pass") for i in range(3)]
    doc = aggregate(runs)
    assert doc["interaction_flake_rate"] == 0.0


def test_legacy_and_current_status_spellings_are_the_same_outcome(tmp_path):
    legacy = _make_run(tmp_path, "r-legacy", "pass")
    current = _make_run(tmp_path, "r-current", "passed")

    doc = aggregate([legacy, current])

    assert doc["interaction_flake_rate"] == 0.0
    assert doc["flaky_tests"] == []


def test_ledger_reader_rejects_a_file_link_that_escapes_the_run(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    external = tmp_path / "external.jsonl"
    external.write_text('{"secret":"canary"}\n', encoding="utf-8")
    link = run_dir / "run-worker.jsonl"
    try:
        link.symlink_to(external)
    except OSError as exc:
        pytest.skip(f"file links are unavailable: {exc}")

    assert ledger_paths(run_dir) == []


def _final(events):
    return next(event for event in reversed(events) if event["kind"] == "run.end")


def test_reader_recovers_complete_records_from_a_torn_tail_and_fails_closed(tmp_path):
    run_dir = _make_run(tmp_path, "r-torn", "pass")
    ledger = run_dir / "run.jsonl"
    ledger.write_bytes(ledger.read_bytes() + b'{"v":"testence/2"')

    events = load_run(run_dir)

    assert any(event["kind"] == "test.end" for event in events)
    assert _final(events)["run_status"] == "incomplete"
    assert {item["code"] for item in _final(events)["integrity_errors"]} >= {
        "torn_tail",
        "manifest_digest",
    }


def test_reader_rejects_corruption_in_a_complete_record(tmp_path):
    run_dir = _make_run(tmp_path, "r-corrupt", "pass")
    ledger = run_dir / "run.jsonl"
    ledger.write_bytes(ledger.read_bytes() + b"{not-json}\n")

    with pytest.raises(ValueError, match="corrupt complete JSONL record"):
        load_run(run_dir)


def test_reader_marks_empty_or_missing_ledgers_incomplete(tmp_path):
    empty = tmp_path / "r-empty"
    empty.mkdir()
    (empty / "run.jsonl").write_bytes(b"")
    missing = tmp_path / "r-missing"
    missing.mkdir()

    assert _final(load_run(empty))["run_status"] == "incomplete"
    assert _final(load_run(missing))["run_status"] == "incomplete"


def test_reader_marks_duplicate_event_and_terminal_identity_incomplete(tmp_path):
    run_dir = _make_run(tmp_path, "r-duplicate", "pass")
    ledger = run_dir / "run.jsonl"
    documents = [json.loads(line) for line in ledger.read_text("utf-8").splitlines()]
    terminal = next(document for document in documents if document["kind"] == "test.end")
    documents.insert(-1, dict(terminal))
    ledger.write_text(
        "\n".join(json.dumps(document) for document in documents) + "\n", encoding="utf-8"
    )

    final = _final(load_run(run_dir))

    assert final["run_status"] == "incomplete"
    assert {item["code"] for item in final["integrity_errors"]} >= {
        "duplicate_event_id",
        "duplicate_terminal",
    }


def test_reader_marks_a_running_manifest_incomplete(tmp_path):
    writer = EvidenceWriter(tmp_path, run_id="r-running", worker="")
    writer.emit("run.start")
    writer.emit("test.start", test="case_a")
    writer.close()

    final = _final(load_run(writer.run_dir))

    assert final["run_status"] == "incomplete"
    assert any(item["code"] == "run_not_complete" for item in final["integrity_errors"])


def test_reader_rejects_an_unknown_event_major(tmp_path):
    run_dir = tmp_path / "r-foreign"
    run_dir.mkdir()
    (run_dir / "run.jsonl").write_text(
        '{"v":"testence/99","run_id":"r-foreign","kind":"run.start"}\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unsupported schema version"):
        load_run(run_dir)
