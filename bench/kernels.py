"""Kernel cost benchmark: where would a native (Rust) backend actually pay?

Each kernel is exercised at a realistic volume for its role, with the workload
scale printed alongside the timing so the number can be reasoned about instead of
quoted. Run: ``python bench/kernels.py``.

Volumes model the analysis plane at fleet scale, not a single happy-path run:
- ledger parse: aggregating a month of CI runs
- aria diff: per-step page diffs across a suite (experiment E3's cost driver)
- fingerprint scoring: heal candidate ranking against a full page of elements
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from testence import kernels  # noqa: E402

REPEATS = 5


def _timed(fn, repeats: int = REPEATS) -> dict[str, float]:
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000)
    return {"ms_median": round(statistics.median(samples), 2), "ms_min": round(min(samples), 2)}


def _synth_ledger(runs: int, events_per_run: int) -> bytes:
    lines = []
    for r in range(runs):
        for seq in range(events_per_run):
            lines.append(
                json.dumps(
                    {
                        "v": "testence/1",
                        "run": f"r-{r}",
                        "seq": seq,
                        "ts": "2026-08-25T10:00:00.000Z",
                        "kind": "step.end",
                        "test": f"test_case_{seq % 20}",
                        "step": f"s{seq}",
                        "status": "ok",
                        "duration_ms": 12.5 + seq % 40,
                        "fingerprint": {
                            "tag": "button",
                            "role": None,
                            "ariaLabel": "add",
                            "testid": None,
                            "text": "add",
                            "id": "add",
                            "classes": ["btn", "btn-primary"],
                        },
                    },
                    separators=(",", ":"),
                )
            )
    return "\n".join(lines).encode("utf-8")


def _synth_aria(nodes: int, *, mutate: bool = False) -> str:
    lines = []
    for i in range(nodes):
        depth = "  " * (i % 4)
        label = f"item {i}" if not (mutate and i % 37 == 0) else f"item {i} renamed"
        lines.append(f'{depth}- button "{label}"')
    return "\n".join(lines)


def _synth_fingerprints(count: int) -> list[dict]:
    return [
        {
            "tag": "button",
            "role": "button",
            "ariaLabel": f"label {i}",
            "testid": None,
            "text": f"caption {i}",
            "id": f"el-{i}",
            "classes": ["btn", f"variant-{i % 5}"],
        }
        for i in range(count)
    ]


def main() -> None:
    results = {"backend": kernels.active_backend(), "python": sys.version.split()[0], "kernels": {}}

    # 1. Ledger parse — 200 runs x 400 events = 80k events (~a month of CI).
    ledger = _synth_ledger(runs=200, events_per_run=400)
    events = ledger.count(b"\n") + 1
    timing = _timed(lambda: kernels.parse_ledger(ledger))
    results["kernels"]["parse_ledger"] = {
        **timing,
        "workload": f"{events} events / {len(ledger) // 1024} KiB",
        "per_unit_us": round(timing["ms_median"] * 1000 / events, 2),
    }

    # 2. ARIA diff — 500-node page, 200 step-to-step diffs (one suite's worth).
    before, after = _synth_aria(500), _synth_aria(500, mutate=True)
    timing = _timed(lambda: [kernels.diff_aria(before, after) for _ in range(200)])
    results["kernels"]["diff_aria"] = {
        **timing,
        "workload": "200 diffs of 500-node snapshots",
        "per_unit_us": round(timing["ms_median"] * 1000 / 200, 2),
    }

    # 3. Fingerprint scoring — rank 300 candidates, 100 drifted locators.
    target = {
        "tag": "button",
        "role": "button",
        "ariaLabel": "label 42",
        "testid": None,
        "text": "caption 42",
        "id": "el-42",
        "classes": ["btn", "variant-2"],
    }
    candidates = _synth_fingerprints(300)
    timing = _timed(lambda: [kernels.score_candidates(target, candidates) for _ in range(100)])
    results["kernels"]["score_candidates"] = {
        **timing,
        "workload": "100 rankings x 300 candidates",
        "per_unit_us": round(timing["ms_median"] * 1000 / 100, 2),
    }

    # 4. Percentiles — 80k samples (metrics over the same month).
    values = [float(i % 500) for i in range(80_000)]
    timing = _timed(lambda: kernels.percentiles(values, [50, 95]))
    results["kernels"]["percentiles"] = {**timing, "workload": "80k samples, 2 pcts"}

    # 5. Token estimation — 5 MiB of evidence text.
    blob = "aria node with a moderately long accessible name\n" * 100_000
    timing = _timed(lambda: kernels.estimate_tokens(blob))
    results["kernels"]["estimate_tokens"] = {
        **timing,
        "workload": f"{len(blob) // 1024 // 1024} MiB text",
    }

    out = Path(__file__).parent / "results" / "kernels.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
