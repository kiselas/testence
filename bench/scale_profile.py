"""Profile deterministic 10k-result export and a bounded failure storm.

The command writes raw per-attempt samples plus p50/p95 distributions. Cold samples
run in fresh Python processes; warm samples reuse one interpreter. Output digests are
compared to make flake/nondeterminism visible instead of averaging it away.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc
from importlib.metadata import version
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from testence.export._model import LoadedRun, Test  # noqa: E402
from testence.export.ctrf import export as export_ctrf  # noqa: E402

DEFAULT_BUDGET = ROOT / "bench" / "budgets" / "scale_profile.json"


def distribution(values: list[float]) -> dict[str, float | int]:
    if not values:
        return {"p50": 0.0, "p95": 0.0, "min": 0.0, "max": 0.0, "n": 0}
    ordered = sorted(values)
    return {
        "p50": round(statistics.median(ordered), 2),
        "p95": round(ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)], 2),
        "min": round(ordered[0], 2),
        "max": round(ordered[-1], 2),
        "n": len(ordered),
    }


def sample(count: int, failure_every: int = 0, error_bytes: int = 0) -> dict[str, Any]:
    tests: list[Test] = []
    error = "bounded failure evidence " + "x" * max(0, error_bytes - 25)
    for index in range(count):
        failed = bool(failure_every and index % failure_every == 0)
        tests.append(
            Test(
                name=f"case-{index:05d}",
                nodeid=f"tests/test_scale.py::test_case[{index}]",
                project_id="scale-profile",
                case_id=f"case-{index:05d}",
                variant_id="default",
                attempt_id="attempt-controller-1",
                proof_id=f"proof-{index:05d}",
                status="failed" if failed else "passed",
                assurance="verified",
                duration_ms=float(index % 17),
                error=error if failed else None,
            )
        )
    run = LoadedRun(
        run_id="scale-profile-fixed",
        project_id="scale-profile",
        schema="testence/2",
        testence_version=version("testence"),
        run_status="failed" if failure_every else "passed",
        tests=tests,
    )
    with tempfile.TemporaryDirectory(prefix="testence-scale-profile-") as temporary:
        target = Path(temporary)
        tracemalloc.start()
        started = time.perf_counter()
        paths = export_ctrf(run, target)
        elapsed_ms = (time.perf_counter() - started) * 1000
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        raw = paths[0].read_bytes()
    return {
        "elapsed_ms": round(elapsed_ms, 2),
        "peak_memory_bytes": peak,
        "artifact_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "results": count,
        "failures": sum(test.failed for test in tests),
    }


def _cold(count: int, failure_every: int, error_bytes: int) -> dict[str, Any]:
    completed = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--sample",
            "--results",
            str(count),
            "--failure-every",
            str(failure_every),
            "--error-bytes",
            str(error_bytes),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return json.loads(completed.stdout)


def aggregate(samples: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "elapsed_ms": distribution([float(item["elapsed_ms"]) for item in samples]),
        "peak_memory_bytes": distribution([float(item["peak_memory_bytes"]) for item in samples]),
        "artifact_bytes": distribution([float(item["artifact_bytes"]) for item in samples]),
        "unique_output_digests": len({item["sha256"] for item in samples}),
        "raw": samples,
    }


def _value(document: dict[str, Any], path: str) -> float:
    value: Any = document
    for part in path.split("."):
        value = value[part]
    return float(value)


def evaluate_budget(result: dict[str, Any], budget: dict[str, Any]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for path, rule in budget.get("limits", {}).items():
        try:
            actual = _value(result, path)
        except (KeyError, TypeError, ValueError):
            violations.append({"metric": path, "error": "metric missing"})
            continue
        if "max" in rule and actual > float(rule["max"]):
            violations.append({"metric": path, "actual": actual, "maximum": rule["max"]})
        if "min" in rule and actual < float(rule["min"]):
            violations.append({"metric": path, "actual": actual, "minimum": rule["min"]})
    return violations


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", action="store_true")
    parser.add_argument("--results", type=int, default=10_000)
    parser.add_argument("--failure-every", type=int, default=0)
    parser.add_argument("--error-bytes", type=int, default=0)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--budget", type=Path, default=DEFAULT_BUDGET)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.sample:
        print(json.dumps(sample(args.results, args.failure_every, args.error_bytes)))
        return
    if args.repeats < 3:
        parser.error("--repeats must be at least 3 for p95/resource checks")

    ten_k_warm = [sample(10_000) for _ in range(args.repeats)]
    ten_k_cold = [_cold(10_000, 0, 0) for _ in range(args.repeats)]
    storm_warm = [sample(1_000, 1, 4096) for _ in range(args.repeats)]
    result = {
        "schema": "testence/scale-profile/1",
        "environment": {
            "os": platform.platform(),
            "python": platform.python_version(),
            "testence": version("testence"),
        },
        "repeats": args.repeats,
        "ten_thousand": {"warm": aggregate(ten_k_warm), "cold": aggregate(ten_k_cold)},
        "failure_storm": aggregate(storm_warm),
        "protocol": {
            "export": "CTRF from LoadedRun",
            "failure_storm": "1000 failed results with 4096-byte bounded errors",
            "memory": "Python allocations measured by tracemalloc",
            "flake": "all repeated output SHA-256 digests must be identical",
        },
    }
    budget = json.loads(args.budget.read_text(encoding="utf-8"))
    violations = evaluate_budget(result, budget) if args.check else []
    result["budget"] = {
        "checked": args.check,
        "source": args.budget.resolve().relative_to(ROOT).as_posix(),
        "passed": not violations if args.check else None,
        "violations": violations,
    }
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    if violations:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
