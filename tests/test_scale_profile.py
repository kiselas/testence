from bench.scale_profile import aggregate, evaluate_budget


def test_scale_aggregate_keeps_raw_samples_and_detects_output_drift():
    samples = [
        {"elapsed_ms": 1, "peak_memory_bytes": 10, "artifact_bytes": 20, "sha256": "a"},
        {"elapsed_ms": 2, "peak_memory_bytes": 11, "artifact_bytes": 20, "sha256": "b"},
        {"elapsed_ms": 3, "peak_memory_bytes": 12, "artifact_bytes": 20, "sha256": "a"},
    ]
    result = aggregate(samples)
    assert result["elapsed_ms"]["p95"] == 3
    assert result["unique_output_digests"] == 2
    assert result["raw"] == samples


def test_scale_budget_fails_closed_for_missing_and_exceeded_metrics():
    result = {"profile": {"elapsed": {"p95": 101}, "digests": 2}}
    budget = {
        "limits": {
            "profile.elapsed.p95": {"max": 100},
            "profile.digests": {"max": 1},
            "profile.missing": {"max": 1},
        }
    }
    assert [item["metric"] for item in evaluate_budget(result, budget)] == [
        "profile.elapsed.p95",
        "profile.digests",
        "profile.missing",
    ]
