# Warm runner latency snapshot

Snapshot captured on 2026-09-02 with:

```bash
.venv/Scripts/python bench/warm_runner_latency.py --repeats 5 --check
```

Both arms used the same persistent CDP browser: five fresh pytest processes and five
pytest sessions in one warm interpreter. The warm process retained its Playwright/CDP
engine connection; the first cold warm call is excluded from steady state.

| Metric | Fresh attached p50 / p95 | Warm steady p50 / p95 | Change |
|---|---:|---:|---:|
| Runner bootstrap | 2,807.64 / 12,469.66 ms | 447.18 / 622.78 ms | −84.1% p50 |
| Whole run | 3,446.94 / 13,362.26 ms | 1,132.93 / 1,496.58 ms | −67.1% p50 |

The fixture boundary identified repeated Playwright/CDP attachment as the largest
remaining runner-owned bootstrap component. Warm sessions still recreate pytest state,
fixtures, auth, run ids and evidence writers; only the engine connection survives.

The budget passed. It gates warm bootstrap p50 at 1,200 ms and requires at least 20%
reduction for both bootstrap and whole-run p50. P95 remains diagnostic: with five
samples it equals one maximum, and ambient host load produced a 13-second fresh outlier.

Engine retention is an authoring optimization. Release and CI validation continue to
use fresh processes.
