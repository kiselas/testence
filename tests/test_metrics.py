from testence.evidence import EvidenceWriter
from testence.metrics import aggregate, percentile


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
    assert doc["flaky_tests"] == ["case_a"]


def test_stable_outcomes_not_flaky(tmp_path):
    runs = [_make_run(tmp_path, f"r-{i}", "pass") for i in range(3)]
    doc = aggregate(runs)
    assert doc["interaction_flake_rate"] == 0.0
