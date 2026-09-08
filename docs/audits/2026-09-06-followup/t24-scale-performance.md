# T24 scale, resource and flake budgets

Status: **local acceptance passed on Windows**.

`bench/scale_profile.py` runs warm and fresh-process arms with raw samples and p50/p95,
measures peak Python allocations with `tracemalloc`, records artifact bytes, and requires
identical SHA-256 output across repeats. It also exports a 1,000-result failure storm
with a bounded 4,096-byte error for every failed result. Missing metrics or exceeded
limits fail the budget.

On Windows 11 / Python 3.13.11, three repeated 10,000-result CTRF exports produced one
digest in both arms. Warm p95 was 814.26 ms with about 17.82 MB peak allocation and a
4,463,458-byte artifact; cold p95 was 790.32 ms with the same size bounds. Failure-storm
p95 was 143.8 ms, peak allocation about 10.01 MB and artifact size 4,560,750 bytes. All
limits in `bench/budgets/scale_profile.json` passed. Raw samples are in
`outputs/audit-2026-09-06-followup/scale-profile.json`.

The real Chromium warm/fresh protocol also passed its checked-in budget over five
iterations. Fresh-process run p95 was 3,170.10 ms; warm steady p95 was 1,134.79 ms,
a 63.28% reduction. The retained resource is only the Playwright/CDP engine; test
sessions, project modules, fixtures, identities and writers are renewed. Raw output is
`outputs/audit-2026-09-06-followup/warm-fresh-profile.json`.
