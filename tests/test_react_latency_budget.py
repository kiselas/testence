from __future__ import annotations

from bench.react_latency import distribution, evaluate_budget


def test_distribution_uses_nearest_rank_p95():
    result = distribution([float(value) for value in range(1, 21)])

    assert result == {"p50": 10.5, "p95": 19.0, "min": 1.0, "max": 20.0, "n": 20}


def test_budget_accepts_a_sufficient_fast_run():
    result = {
        "repeats": 3,
        "engine": {"fill_ms": {"p95": 20.0, "n": 24}},
    }
    budget = {
        "minimum_repeats": 3,
        "limits": {"engine.fill_ms.p95": {"max": 100, "min_samples": 20}},
    }

    assert evaluate_budget(result, budget) == []


def test_budget_reports_speed_and_sample_regressions():
    result = {
        "repeats": 2,
        "engine": {"fill_ms": {"p95": 150.0, "n": 8}},
    }
    budget = {
        "minimum_repeats": 3,
        "limits": {"engine.fill_ms.p95": {"max": 100, "min_samples": 20}},
    }

    violations = evaluate_budget(result, budget)

    assert [violation["metric"] for violation in violations] == [
        "repeats",
        "engine.fill_ms.p95",
        "engine.fill_ms.p95",
    ]


def test_budget_supports_a_minimum_improvement_ratio():
    result = {"repeats": 5, "comparison": {"bootstrap_reduction_percent": 12.0}}
    budget = {
        "minimum_repeats": 5,
        "limits": {"comparison.bootstrap_reduction_percent": {"min": 15.0}},
    }

    assert evaluate_budget(result, budget) == [
        {
            "metric": "comparison.bootstrap_reduction_percent",
            "actual": 12.0,
            "minimum": 15.0,
        }
    ]
