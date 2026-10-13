# PROD-06 test instrumentation isolation follow-up

CI38437189570 has11 successes/4 failures/3 wheel skips. Three Ubuntu jobs fail
all4 synthetic host probes because their child-wide platform.uname replacement
intercepts uuid's normal platform.system during pytest import. Windows3.12
separately fails debug-cycle setup Page.goto at2000ms (969 passed/1 error).
Merge9f8630f tree equals cbcb625 head tree. Raw logs/hashes and exact failed tests
are retained in this window and ignored outputs; no old result is overwritten.

Before edit, a forced foreign platform call reproduced the bad probe's assertion.
The test now returns a synthetic platform namespace only to testence.host import;
all other modules use real stdlib. The child hook is restored immediately. Zero
host calls at import, exact values, single first-error call and concurrency
assertions remain. Negative control invokes host.system prematurely and still
fails the no-query assertion. Real platform identity/foreign call are checked.

Only test instrumentation changes; every runtime src byte equals cbcb625. Current
targeted22/ruff/mypy pass. Full: 1 failed, 967 passed, 2 skipped in 307.77s (0:05:07); exit1.
Examples pass. Prior live lifecycle evidence applies to identical runtime source;
no unchanged browser gate repeated. Exact check receipts are in the adjacent wiki window host-ci-20261013-15.
Seven frozen files unchanged. Actual new Linux/floor CI still pending.

Previous wiki probes also used child-wide platform replacement. Their measured
Windows counts remain archived; they do not establish module-isolated behavior
on every OS. This correction adds narrower evidence without editing those records.
The production lazy-host fix is unchanged. Explicit first-use metadata remains
unbounded/native-fault exposed. Separate Windows navigation timeout, old native
exits and missing oracle UI result are unresolved. No timeout increase, test
deletion, global QA patch, dependency change, independent/model or release claim.


Changed tests/test_host_metadata.py and this engineering audit; runtime source
unchanged. Test SHA256 52b49af74e963b5fa71172204844de3bdd51e9d3bde0c2d9c50c712c76c519f1.
Host SHA256 2e5bfc33331bb7bb92942058017b58c9477e534fa1288795e76ce0d3eda0075c.
Last full run uses outputs/host-ci-20261013-15/tmp-full; precise hosted failed
step: tests/test_debug_cycle.py:92 engine.goto('/') during setup of
test_xhr_upload_and_context_reset_leave_no_adapter, timeout2000ms. No cause proved.

Required checks ran via outputs/quality-venv31214/Scripts/python.exe: ruff format
--check src tests bench scripts examples; ruff check same scope; mypy src scripts;
pytest -q -n4 --basetemp=outputs/host-ci-20261013-15/tmp-full; pytest examples -q
--testence-headless with fresh tmp-examples. Targeted host/startup/plugin-opt-in
checks use a distinct tmp-targeted. Prior unchanged live gate run IDs:
r-20261013-171331-3ba6ed and r-20261013-171347-80e0a5, retained under
outputs/host-diagnostic-20261013-14/lifecycle/consumer. No benchmark gain claim.

Next proving command after publishing current candidate:

```powershell
gh pr view 39 --json headRefOid,baseRefOid,statusCheckRollup
```

New Linux/floor replay and Windows timeout diagnosis remain pending; do not retry
the prior job for green or increase the navigation deadline without a mechanism.
