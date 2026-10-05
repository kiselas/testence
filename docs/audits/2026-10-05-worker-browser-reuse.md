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
