"""What has to hold before a suite may run on more than one worker.

Each of these pins a failure that was measured rather than imagined: a shared
ledger losing a quarter of its events, a shared debug port killing every worker
but one, nested steps double-counted into the latency metric, and authoring
churn reported as flakiness.
"""

import pytest

from testence.engine import worker_port_offset
from testence.engine.playwright_cdp import PlaywrightCdpEngine
from testence.evidence import RUN_ID_ENV, WORKER_ENV, EvidenceWriter, ledger_paths
from testence.fingerprints import FingerprintStore
from testence.identity import source_case_id
from testence.metrics import aggregate, load_run

FP = {
    "tag": "tr",
    "role": "row",
    "ariaLabel": None,
    "testid": "k1",
    "text": "row",
    "id": None,
    "classes": [],
}


# -- one ledger per process, merged on read ----------------------------------


def test_worker_writes_its_own_ledger_into_the_shared_run_dir(tmp_path, monkeypatch):
    monkeypatch.setenv(WORKER_ENV, "gw2")
    writer = EvidenceWriter(tmp_path, run_id="r-shared")
    writer.emit("note", text="from gw2")
    writer.close()

    assert writer.path.name == "run-gw2.jsonl"
    assert writer.run_dir.name == "r-shared"


def test_load_run_merges_controller_and_worker_ledgers_in_time_order(tmp_path):
    controller = EvidenceWriter(tmp_path, run_id="r-merge", worker="")
    controller.emit("run.start")
    gw0 = EvidenceWriter(tmp_path, run_id="r-merge", worker="gw0")
    gw1 = EvidenceWriter(tmp_path, run_id="r-merge", worker="gw1")
    for writer, test in ((gw0, "case_a"), (gw1, "case_b")):
        writer.emit("test.start", test=test)
        writer.emit("test.end", test=test, status="pass", duration_ms=100.0)
    controller.emit("run.end", duration_ms=200.0, passed=2, failed=0)
    for writer in (controller, gw0, gw1):
        writer.close()

    assert [p.name for p in ledger_paths(controller.run_dir)] == [
        "run.jsonl",
        "run-gw0.jsonl",
        "run-gw1.jsonl",
    ]
    events = load_run(controller.run_dir)
    # Nothing lost, and readable as one story: `seq` restarts per process, so a
    # reader that trusted it would interleave three ledgers wrongly.
    assert [e["kind"] for e in events].count("test.end") == 2
    assert [e["ts"] for e in events] == sorted(e["ts"] for e in events)


def test_run_id_comes_from_the_environment_so_workers_share_a_directory(tmp_path, monkeypatch):
    monkeypatch.setenv(RUN_ID_ENV, "r-from-env")
    monkeypatch.delenv(WORKER_ENV, raising=False)
    writer = EvidenceWriter(tmp_path)
    writer.close()
    assert writer.run_dir.name == "r-from-env"


# -- the metrics those ledgers feed ------------------------------------------


def _emit_case(writer, test, code, *, status="pass", leaf_ms=(40.0, 60.0), composite_ms=500.0):
    writer.emit("test.start", test=test, code=code)
    writer.emit(
        "step.end",
        test=test,
        step="s1",
        status="ok",
        duration_ms=composite_ms,
        depth=0,
        children=len(leaf_ms),
    )
    for i, ms in enumerate(leaf_ms, start=2):
        writer.emit(
            "step.end", test=test, step=f"s{i}", status="ok", duration_ms=ms, depth=1, children=0
        )
    writer.emit("test.end", test=test, status=status, duration_ms=900.0)


def test_step_latency_counts_leaves_only(tmp_path):
    writer = EvidenceWriter(tmp_path, run_id="r-leaves")
    writer.emit("run.start")
    _emit_case(writer, "case_a", "code1")
    writer.emit("run.end", duration_ms=1000.0, passed=1, failed=0)
    writer.close()

    doc = aggregate([writer.run_dir])
    # Three step.end events, two of them leaves: the composite's 500 ms already
    # contains its children and counting it again inflated p95.
    assert doc["step_latency_ms"]["n"] == 2
    assert doc["step_latency_ms"]["p50"] == 50.0


def test_a_step_end_without_the_children_field_is_still_counted(tmp_path):
    """Ledgers written before the field exist; they must not silently vanish."""
    writer = EvidenceWriter(tmp_path, run_id="r-old")
    writer.emit("run.start")
    writer.emit("test.start", test="case_a")
    writer.emit("step.end", test="case_a", step="s1", status="ok", duration_ms=100.0)
    writer.emit("test.end", test="case_a", status="pass", duration_ms=100.0)
    writer.emit("run.end", duration_ms=100.0, passed=1, failed=0)
    writer.close()

    assert aggregate([writer.run_dir])["step_latency_ms"]["n"] == 1


def test_a_case_that_changed_between_runs_is_not_a_flake(tmp_path):
    """fail -> pass while being written is authoring, not instability. Reporting it
    as flake made a nine-case suite read 44.4 % with nothing having ever flapped,
    and the playbook gates on that number being zero."""
    runs = []
    for run_id, code, status in (("r-a", "code1", "fail"), ("r-b", "code2", "pass")):
        writer = EvidenceWriter(tmp_path, run_id=run_id)
        writer.emit("run.start")
        _emit_case(writer, "case_a", code, status=status)
        writer.emit("run.end", duration_ms=100.0, passed=1, failed=0)
        writer.close()
        runs.append(writer.run_dir)

    doc = aggregate(runs)
    assert doc["flaky_tests"] == []
    assert doc["interaction_flake_rate"] == 0.0


def test_the_same_code_flapping_is_still_a_flake(tmp_path):
    runs = []
    for run_id, status in (("r-c", "fail"), ("r-d", "pass")):
        writer = EvidenceWriter(tmp_path, run_id=run_id)
        writer.emit("run.start")
        _emit_case(writer, "case_a", "same-code", status=status)
        writer.emit("run.end", duration_ms=100.0, passed=1, failed=0)
        writer.close()
        runs.append(writer.run_dir)

    doc = aggregate(runs)
    assert doc["flaky_tests"] == [f"unconfigured/{source_case_id('case_a')}/default"]
    assert doc["interaction_flake_rate"] == 1.0


# -- heal memory and machine-wide resources ----------------------------------


def test_worker_fingerprints_land_in_shards_and_are_read_back_together(tmp_path):
    base = tmp_path / "fp.json"
    for worker, test in (("gw0", "case_a"), ("gw1", "case_b")):
        store = FingerprintStore(base, worker=worker)
        store.record(test, "click the row", "testid='k1'", FP)
        store.flush()

    assert (tmp_path / "fp.gw0.json").exists()
    assert (tmp_path / "fp.gw1.json").exists()
    # A later reader sees both halves: a shared file would have been
    # last-writer-wins, silently discarding N-1 workers' memory.
    merged = FingerprintStore(base, worker="")
    assert merged.get("case_a", "click the row") == FP
    assert merged.get("case_b", "click the row") == FP


def test_a_serial_run_folds_the_shards_back_into_one_reviewable_file(tmp_path):
    base = tmp_path / "fp.json"
    shard = FingerprintStore(base, worker="gw0")
    shard.record("case_a", "click the row", "testid='k1'", FP)
    shard.flush()

    serial = FingerprintStore(base, worker="")
    serial.record("case_b", "click the row", "testid='k1'", FP)
    serial.flush()

    assert base.exists()
    assert not (tmp_path / "fp.gw0.json").exists()
    assert set(FingerprintStore(base, worker="")._data) == {
        "case_a::click the row",
        "case_b::click the row",
    }


@pytest.mark.parametrize(
    "worker,expected",
    [
        ("", 0),
        ("gw0", 0),
        ("gw1", 1),
        ("gw11", 11),
        ("master", 0),
    ],
)
def test_debug_port_offset_follows_the_worker_id(monkeypatch, worker, expected):
    """The debug port is machine-wide. Four workers asking for 9222 meant one
    bound it and the rest died on "Cannot start http server for devtools" —
    a 30 s Playwright timeout per case and six errored tests."""
    monkeypatch.setenv(WORKER_ENV, worker)
    assert worker_port_offset() == expected


# -- the API that made a verb look like a URL --------------------------------


@pytest.mark.parametrize("verb", ["POST", "post", "DELETE", "patch"])
def test_wait_for_request_refuses_a_verb_as_the_url_fragment(verb):
    """``wait_for_request("POST")`` searched the URL for the string "POST", never
    matched, burned the whole budget, and made ``assert not sent`` pass for the
    wrong reason at four call sites."""
    engine = PlaywrightCdpEngine(base_url="https://example.test")
    with pytest.raises(ValueError, match="matches the URL, never the method"):
        engine.wait_for_request(verb, timeout_ms=10)


def test_wait_for_request_accepts_a_url_fragment_with_a_method():
    """The guard must not reject the correct call shape."""
    engine = PlaywrightCdpEngine(base_url="https://example.test")
    with pytest.raises(RuntimeError, match="engine not started"):
        engine.wait_for_request("/api/", method="POST", timeout_ms=10)
