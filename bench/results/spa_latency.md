# SPA latency probe

Scenario: asynchronously mounted SPA root, controlled input, and an API poll every
100 ms. Command: `python bench/spa_latency.py`.

Environment: Windows 11 `10.0.26200`, Python `3.12.13`, Playwright `1.62.0`, one local
Chromium session. Twenty fill iterations per arm. Snapshot date: 2026-09-02.

| measurement | before | after | reading |
|---|---:|---:|---|
| navigation to input-only SPA | 5,048.67 ms | 114.29 ms | 44× faster; no false text timeout |
| public `Actions.fill` p50 | 11.10 ms | 6.97 ms | 37% lower |
| public `Actions.fill` p95 | 13.00 ms | 9.34 ms | 28% lower |
| scoped mutation response | — | 116.39 ms | exact response after click |
| `networkidle` with polling, 750 ms budget | 740.42 ms | 737.62 ms | still expensive; removed from signalled save path |

The opt-in engine `fast=True` fill measured 3.46 ms p50 versus 4.76 ms with normal
actionability checks. At the public Actions layer the difference was only 0.56 ms because
evidence work dominates this tiny page. The checked default therefore remains the normal
path; fast fill is useful only after a readiness proof or in measured repetitive flows.

This is a before/after diagnostic on one host. It demonstrates the eliminated waits but
does not establish a suite-level speed claim.
