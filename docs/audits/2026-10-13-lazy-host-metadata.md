# Lazy host metadata candidate

PROD-06 base6db716cfd344373e7e127f5a75311d0c8166b1ec. Plugin loading started a
platform.uname query in a daemon even without a metadata consumer. Its error path
retried the provider at first use. Isolated before/after provider controls establish
these side effects, independently of previous native WMI crash classification.

Host metadata now loads lazily under a cache lock; it retains exact platform
system/release values and propagates the first provider error without automatic
retry. Imports start no metadata daemon. Four isolated child regressions exercise
no-use, values, exception and concurrent access. Targeted22, ruff/mypy pass.
Current full: 968 passed, 2 skipped in 296.45s (0:04:56); exit0. Examples and fresh/reuse
8-case/2-worker lifecycle controls pass. Exact commands/hashes/timings:
[receipt](2026-10-13-lazy-host-metadata.json). Seven frozen files unchanged.

Native platform faults and unbounded first-use metadata remain possible. No global
platform patch or Windows description remapping. Earlier native exits, oracle
missing UI result and hosted ERR_NO_BUFFER_SPACE remain unexplained; a current
green run would not retroactively repair their receipts. Previous head's18 hosted
successes do not qualify this new change. New exact-head CI/review still required.
No latency, complete native safety, main integration or release claim.

Changed host.py, tests/test_host_metadata.py, en/ru changelogs and this MD/JSON
audit. Last live gate: outputs/host-diagnostic-20261013-14/lifecycle/consumer, fresh
then reuse, identical context/namespace assertions and exact browser counts.
Methodology/diagnostic probes remain in adjacent wiki. Next proving command:

```powershell
gh pr view 39 --json headRefOid,baseRefOid,statusCheckRollup
```

Inspect only new revision's CI. Further native fixes require a new discriminating
frame; no unchanged full replay, global platform monkeypatch or retry for green.
Reverting host.py restores prior collection behavior without evidence/store edits.
