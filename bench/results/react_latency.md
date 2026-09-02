# Real React latency snapshot

Snapshot: 2026-09-02. Environment: Windows 11 `10.0.26200`, Python `3.12.13`,
Playwright `1.62.0`, production-built React 19 SUT. Commands:

```bash
.venv/Scripts/python bench/react_latency.py --repeats 5 --check \
  --output bench/results/react_latency.json
.venv/Scripts/python bench/react_latency.py --shared-browser --repeats 5 --check \
  --output bench/results/react_latency_attached.json
```

## Launch versus shared browser

Each sample is a fresh pytest process. The attached arm keeps one persistent browser
context alive and borrows it over CDP; test data remains isolated by a unique SUT run id.

| Boundary | Launch p50 / p95 | Attached p50 / p95 | Change in p50 |
|---|---:|---:|---:|
| Fresh pytest process | 3,208.11 / 3,262.67 ms | 2,022.56 / 2,254.02 ms | −37.0% |
| Bootstrap and runner overhead | 2,584.47 / 2,635.03 ms | 1,475.00 / 1,658.62 ms | −42.9% |
| Real React test body | 608.30 / 672.40 ms | 519.30 / 604.20 ms | −14.6% |
| Mutation through visible React commit | 81.90 / 113.20 ms | 78.30 / 100.90 ms | −4.4% |

Starting the shared browser took 1,240.15 ms once. Therefore a one-off attached run is
not faster end to end; the accumulated loop breaks even on its second run. Both launch
and attached budget files passed.

## Interaction profile

| Boundary | Launch p50 / p95 | Attached p50 / p95 | Samples per arm |
|---|---:|---:|---:|
| Public controlled fill | 15.20 / 32.40 ms | 14.60 / 24.90 ms | 40 |
| Public controlled fill, `fast=True` | 14.00 / 21.00 ms | 14.80 / 23.50 ms | 40 |
| Exact POST response wait | 16.00 / 16.00 ms | 16.00 / 31.00 ms | 5 |

## Network-wait change

For a same-host before/after check, the previous 50 ms capture-buffer quantum was run
over three fresh processes. It produced 63 ms p95 for the exact POST response wait and
127.5 ms p50 for the mutation round trip. With the 10 ms quantum, the launch arm measured
16 ms and 81.9 ms respectively. This is a diagnostic comparison of implementation paths,
not a public cross-machine speed claim.

Machine-readable results, including min/max and every budget verdict, are in
`react_latency.json` and `react_latency_attached.json`.
