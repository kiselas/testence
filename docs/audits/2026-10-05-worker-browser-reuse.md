# Worker browser reuse, 2026-10-05

Plan AUD-LC26. Base 5063876, fetched origin/main: local ahead 11, behind 0;
working tree was clean. No previous incomplete edits were present.

Acceptance: LC26-01 stop is idempotent and records shutdown phases, preserving
borrowed browsers/drivers; LC26-02 explicit worker browser reuse gives every
case a new context and retains isolation/provenance/recordings after failures;
LC26-03 authentication failures retain timing; LC26-04 synthetic comparable
serial/parallel lifecycle measurements and complete required checks.

Baseline: exact historical slow test passed 1 in 5.29s (call 5.17s). Command:
& outputs/quality-venv31214/Scripts/python.exe -m pytest
 tests/test_failure_diagnostics.py::test_a_default_browser_starts_while_another_run_holds_9222
 -q --basetemp=.tmp-pytest-lifecycle-baseline --durations=10 -o faulthandler_timeout=20
Log: outputs/lifecycle-baseline.log. Same Python 3.12.14, msedge and debug port 0.

Ignored diagnostic outputs/lifecycle-probe.py (one action/session per child, owned
processes, 120s limit) distinguished context.close/browser.close/driver.stop.
Serial wall 4936.2ms; browser.close 1625.6ms. Four workers: wall 21591.7..21635.6ms,
browser.close 15523.4..15780.3ms. With DEBUG=pw:browser: close 17199.8..17742.9ms,
exit code 0, no force kill, temp cleanup ~100ms. All sessions retained original
port/data-page assertions. Faulthandler snapshots show the SDK message loop waiting.

A further four-worker probe monitored the public-CDP browser PID with a pinned
Windows process handle: OS exit ~2205..2319ms, SDK close ~2336..2367ms. It did not
reproduce the long shutdown; it does not prove delayed inherited stdio as the cause.
Upstream #41210/#41330 discuss this mechanism, but the locked Playwright 1.62.0
already supplies --disable-updater-scheduler. No SDK patch, global updater change,
forced browser kill, automatic channel fallback or hidden retry is introduced.

Diagnostic commands: same interpreter, outputs/lifecycle-probe.py 1 / 4;
TESTENCE_BROWSER_CHANNEL=msedge, TESTENCE_DEBUG_PORT=0. DEBUG=pw:browser on the
browser-log/os-exit probes. Logs: outputs/lifecycle-probe-serial.json,
outputs/lifecycle-probe-parallel.json, outputs/lifecycle-probe-browser-log.json,
outputs/lifecycle-probe-os-exit.json. This is local synthetic evidence only.

Implementation and final proof/handoff follow below.

Development controls:
- lifecycle-focus-1: 3 failed, 34 passed, 91.53s. One failure exposed redaction of the
  numeric browser.session_close key (reserved secret shape); rename known metric to
  browser.worker_close/start, keeping privacy policy intact. Two refusal checks saw
  existing kernel INTERNALERROR before our fixture guard; validate reuse at lifecycle
  initialization, before collection/kernel selection, rather than widening the test.
- lifecycle-focus-2: 18 passed, 49.87s; tests/test_browser_reuse.py,
  tests/test_trace_video.py and tests/test_warm_runner.py. Trace/failure recovery,
  exact per-worker lifecycle, mode/type refusal, idempotency and auth failure timing.
- lifecycle-focus-3: 66 passed, 159.60s; tests/test_browser_reuse.py,
  tests/test_auth.py, tests/test_save_and_verify.py and tests/test_failure_diagnostics.py.
  Added retained video proof, warm refusal, config/MCP opt-in and corrected namespace
  absence glob. The control bodies already asserted each exact marker's absence.
  Some Edge teardown still took 15.25..15.39s in the default fresh-browser path.

All focus commands: same isolated interpreter, -m pytest <listed files> -q
--basetemp=.tmp-pytest-lifecycle-focus-N --durations=8;
logs outputs/lifecycle-focus-N.log. Fresh basetemp for every run. These development
runs are not the final frozen-source release checks; source refinements continued.

First comparison at d6a631a74a6a0bcdb3116fc6c1a2b3d75a71d866:
bench/browser_lifecycle_latency.py --cases 4 --workers 1 --check,
outputs/lifecycle-benchmark-serial.json. Both arms passed identical assertions;
fresh 10516.0ms, 4 launches/closes; reuse 4343.0ms, 1 launch/close, observed wall
reduction 58.7%. This includes preflight and final shutdown and is one paired
sample, not a statistical or private-target speedup. Benchmark raw directories
were temporary; the structured result is retained, not a hosted/raw-run receipt.
A final refinement binds the actual reuse choice in run.start fingerprint metadata.

## Final proof and handoff

Frozen source **60eae0598b36806ccef9dc7a1a4eea85c2805055** (implementation d6a631a,
then runtime fingerprint binding). No source/test edits during final required checks.
Environment: Windows 11 10.0.26100, Python 3.12.14, isolated environment
outputs/quality-venv31214; locked dependencies; TESTENCE_BROWSER_CHANNEL=msedge,
TESTENCE_DEBUG_PORT=0. Edge executable ProductVersion observed after checks:
154.0.4258.53. Neither dependencies nor the default 3.12.4 interpreter were replaced.

All commands use & 'outputs/quality-venv31214/Scripts/python.exe':
- `-m ruff format --check src tests bench scripts examples`: 232 files formatted,
  exit 0, outputs/lifecycle-format.log.
- `-m ruff check src tests bench scripts examples`: clean, exit 0,
  outputs/lifecycle-ruff.log.
- `-m mypy src scripts`: 86 files clean, exit 0, outputs/lifecycle-mypy.log.
- `-m pytest -q -n 4 --basetemp=.tmp-pytest-lifecycle-final --durations=12
  --junitxml=outputs/lifecycle-final.xml`: **892 passed, 2 skipped, 364.05s**,
  exit 0, outputs/lifecycle-final.log/XML. The skips remain the Windows symlink
  privilege controls; those scenarios are not locally verified.
- `-m pytest examples -q --testence-headless --basetemp=.tmp-pytest-lifecycle-examples`:
  **5 passed, 1 intentionally skipped demo_failure, 15.17s**, exit 0,
  outputs/lifecycle-examples.log; run r-20261005-133741-4c5c2b.
- `-m pytest examples -q --testence-headless --testence-browser-reuse
  --basetemp=.tmp-pytest-lifecycle-examples-reuse`: **5 passed, 1 intentional skip,
  7.59s**, exit 0, outputs/lifecycle-examples-reuse.log;
  run r-20261005-133854-5df935. Its ledger has one worker start/close, 3593.3/602.4ms.
  These two example runs are functional proof, not a statistical speedup comparison.

Narrow benchmark on final candidate:
`bench/browser_lifecycle_latency.py --cases 8 --workers 4 --check`, exit 0,
outputs/lifecycle-benchmark-parallel.json. Same assertions in both arms:
fresh 30812.0ms and 8 launches/closes; reuse 12875.0ms and 4 launches/closes;
observed wall reduction 58.2%. Both include collection and final shutdown.
One paired sample, no fixed host-independent latency threshold. Serial comparison
and its earlier source revision are recorded above. Raw benchmark projects were
removed by TemporaryDirectory; retained structured results are diagnostic receipts.

Full run **r-20261005-132933-14f194**, evidence runs/r-20261005-132933-14f194/;
controller and all four worker run.end events exited 0. Last functional run is
r-20261005-133854-5df935 at runs/r-20261005-133854-5df935/.
[Compact receipt](2026-10-05-worker-browser-reuse-receipt.json) binds changed source
blobs, environment/lock, JUnit, run ends and log/benchmark hashes. Development
failures remain recorded; there was no hidden interaction retry or weakened assertion.

LC26-01..04: implemented and locally verified in synthetic scope. Changed files:
playwright_cdp.py, pytest_plugin.py, debug.py, cli.py, mcp.py; auth/oracle fixtures
use ephemeral ports; new tests/test_browser_reuse.py (13 controls), lifecycle benchmark,
ADR and authoring/MCP documentation. Normal stop drops stale transport references;
sibling creation failures release their new context without closing the owner;
cleanup/interruption status and failed auth timings remain observable. Reuse is explicit,
keeps new contexts/auth/recordings per case and closes one owned browser per worker.
Full source diff: git diff 5063876..60eae05; later edits only update audit/receipts.

Exact failing step in final checks: **none**. Expected wrong-heading/auth failures in
nested consumers are negative controls, with passed outer checks. Full suite used default
fresh-browser mode; reuse has separate live serial/parallel/trace/video/example controls.

Remaining uncertainty: the 111.93s historical outlier's root cause is not established.
This full run still has 64.06s native-route corpus call, 38.80s rerun setup and 19.79s
soft-check teardown. Do not claim the full mixed suite or private hour-long pilot is
fixed. Reuse reduces repeated lifecycle work; final Edge shutdown can still be slow.
It assumes a stable browser configuration per worker and provides context isolation,
not browser-process/crash isolation. Use the default for process-level/crash coverage.
Attached/persistent/warm configurations are rejected at preflight. Other OS/Python floors,
service workers/OOPIF and private target account isolation/cleanup are not proved here.
No independent review, cloud/client trial, remote push or public release is claimed.

Next proving command, new unused basetemp and same environment/interpreter:
`-m pytest tests/test_browser_reuse.py tests/test_trace_video.py -q
--basetemp=.tmp-pytest-worker-reuse-next --durations=10`.
For consumer acceptance: `testence debug <consumer-test-file> --project <consumer-root>
--profile <declared-profile> --allow-multiple --reuse-browser --json` on a pinned build
with synthetic seed and authoritative cleanup. Compare to its default mode with
identical cases and include final worker shutdown in wall time.
