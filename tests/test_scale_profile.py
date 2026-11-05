import json

from bench.scale_profile import DEFAULT_BUDGET, aggregate, evaluate_budget


def test_scale_aggregate_keeps_raw_samples_and_detects_output_drift():
    samples = [
        {
            "elapsed_ms": 1,
            "cpu_ms": 1,
            "peak_memory_bytes": 10,
            "artifact_bytes": 20,
            "sha256": "a",
        },
        {
            "elapsed_ms": 2,
            "cpu_ms": 2,
            "peak_memory_bytes": 11,
            "artifact_bytes": 20,
            "sha256": "b",
        },
        {
            "elapsed_ms": 3,
            "cpu_ms": 3,
            "peak_memory_bytes": 12,
            "artifact_bytes": 20,
            "sha256": "a",
        },
    ]
    result = aggregate(samples)
    assert result["elapsed_ms"]["p95"] == 3
    assert result["cpu_ms"]["p95"] == 3
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


def _profile(wall_ms: float, cpu_ms: float) -> dict:
    def block(wall: float, cpu: float) -> dict:
        return {
            "elapsed_ms": {"p95": wall},
            "cpu_ms": {"p95": cpu},
            "peak_memory_bytes": {"p95": 1.0},
            "artifact_bytes": {"p95": 1.0},
            "unique_output_digests": 1,
        }

    return {
        "ten_thousand": {"warm": block(wall_ms, cpu_ms), "cold": block(wall_ms, cpu_ms)},
        "failure_storm": block(wall_ms, cpu_ms),
    }


def test_the_checked_in_budget_gates_cpu_time_not_wall_time():
    """A loaded runner stretches wall time; it must not fail the gate, CPU time must."""
    budget = json.loads(DEFAULT_BUDGET.read_text(encoding="utf-8"))
    assert not any(metric.endswith("elapsed_ms.p95") for metric in budget["limits"])
    # Same numeric limits as when they were gated on wall time: nothing was loosened.
    limits = budget["limits"]
    assert limits["ten_thousand.warm.cpu_ms.p95"] == {"max": 10000}
    assert limits["ten_thousand.cold.cpu_ms.p95"] == {"max": 10000}
    assert limits["failure_storm.cpu_ms.p95"] == {"max": 5000}

    assert evaluate_budget(_profile(wall_ms=600_000, cpu_ms=2_000), budget) == []
    exceeded = {item["metric"] for item in evaluate_budget(_profile(10, 20_000), budget)}
    assert exceeded == {
        "ten_thousand.warm.cpu_ms.p95",
        "ten_thousand.cold.cpu_ms.p95",
        "failure_storm.cpu_ms.p95",
    }
