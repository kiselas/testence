# PROD-07 ready-reader adoption

Adopted only the already-merged PR37 process hunk from
d6ec3b7703da7de0d53153e003e4dea3745e4b48. Added/removed source lines match the
pinned GitHub patch exactly: source-bound adoption receipt in adjacent wiki window process-ready-20261013-16. No branch/PR merge,
retarget or unrelated security-warning change. PID readiness now observes only
missing/sharing-denied reads within the original deadline; invalid PID is not
swallowed. Verified ownership still precedes release. Project command runs once.

Before edit,2 transient controls failed at the original read. First harness attempt
had2 setup errors because output parent was missing; retained separately, then a
new prepared run supplied the actual counterexamples. Six new real Windows gate
controls cover transient missing/denial, permanent denial under original budget,
empty/malformed PID and early gate exit with no project marker. Existing assignment,
redirector and descendant controls remain. Targeted26/ruff/mypy pass.
Full: 974 passed, 2 skipped in 331.40s (0:05:31); exit0. Examples and new8-case/2-worker
fresh/reuse lifecycle gate pass. Seven frozen files unchanged. Exact check receipts and source hashes are in that wiki window. No latency claim.

Prior head5c6edb6 CI38445139464 has18 successes; merge6e7dc86 tree equals that head.
This qualifies repaired host test isolation, not new process source. New exact-head
CI/review pending. Previous full PID failure is preserved; the controls prove a
transient-read remedy, not the external origin of sharing denial. Prior WMI/native
exits,2s Windows navigation and missing oracle UI result remain separate unknowns.
Internal methodology and probes stay in wiki; no model/independent or release claim.


Changed src/testence/_process.py, tests/test_process_ready.py and this audit.
Process SHA256 c7ca0aeab792db7f4347511e65067c4498a87efc9546f35d95e09a28608fded1.
Test SHA256 d77a79c06bf9828babec5e168a043f11cbfcbcf690c6e27af1acd5758105315e.
Full command: outputs/quality-venv31214/Scripts/python.exe -B -m pytest -q -n4
--basetemp=outputs/process-ready-20261013-16/tmp-full. Also ran ruff format/check
src/tests/bench/scripts/examples, mypy src/scripts, headless examples with new
tmp-examples and stock lifecycle8 cases/2 workers with retained synthetic consumer
under outputs/process-ready-20261013-16/lifecycle/consumer. All commands use patched
Python3.12.14, msedge browser for live runs, debug port0 and faulthandler1.
Prior exact failed step: test_allure_compat.py::test_invalid_allure_naming_stops_the_session,
_process.py ready.read_text PermissionError before expected settings error.

Next proving command after publishing candidate:

```powershell
gh pr view 39 --json headRefOid,baseRefOid,statusCheckRollup
```

No unchanged full replay. Future navigation/oracle fixes need discriminating
request/response/browser-event evidence; do not raise deadlines for green.
Revert this one hunk to roll back; old evidence and stores remain unchanged.
