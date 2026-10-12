# Debug cycle, 2026-10-05

Plan AUD-DC26; claims DC26-01..06 are defined in ADR-0031. Base b296efd.
User authorized implementation. Current branch main; preserve previous work.
No private application trial or release approval is claimed.

Implementation: debug.py/debug_worker.py and CLI/MCP exact selection/status;
response_rewrites.py with engine capability/DSL integration; declared UI outcome
observation; pytest lifecycle timing; synthetic controls and authoring documentation.

Environment: Windows, Python 3.12.14 at outputs/quality-venv31214/Scripts/python.exe,
locked dev/parallel/visual dependencies, msedge, TESTENCE_DEBUG_PORT=0. No default
3.12.4 runtime used (previous native WMI crash). All raw logs and basetemp ignored.

Development receipts (no failures hidden):
- debug-cycle-1: 1 failed, 9 passed, 19.44s: Windows relative pack separators rejected.
  Fixed portable separator normalization before managed-path validation.
- debug-cycle-2: 1 failed, 9 passed, 19.74s: auth-none lacked a phase entry.
  Record explicit skipped authentication with zero duration.
- debug-cycle-3: 1 failed, 26 passed, 42.48s: XHR harness expected compact JSON.
  Correct exact expected serialization; original XHR adapted payload was correct.
- debug-cycle-4: 28 passed, 41.39s. Added receiver authorization header control;
  one original multipart receipt and exact file bytes; XHR/reset proven.

Exact development command prefix: & outputs/quality-venv31214/Scripts/python.exe
-m pytest tests/test_debug_cycle.py; cycle 3/4 also tests/test_authoring_friction.py
and tests/test_native_routes.py. All use -q --basetemp=.tmp-pytest-debug-cycle-N,
logs outputs/debug-cycle-N.log. Cycle 1/2 additionally --durations=8.
Cycle 5 adds tests/test_mcp.py and uses the same unique-basetemp/log convention.

Final source revision, fresh checks, compact receipt, last run ID and handoff follow.

Cycle 5: 49 passed, 51.11s; MCP guarded debug/status integration included.

## Final verification and handoff

Candidate source: **2d51321e8a02a59dd9d83555322807d1c3f05613**. Source/tests stayed
frozen through all final checks; later edits only update documentation/receipts.
All commands below use `& 'outputs/quality-venv31214/Scripts/python.exe'` with
TESTENCE_BROWSER_CHANNEL=msedge and TESTENCE_DEBUG_PORT=0.

- `-m ruff format --check src tests bench scripts examples`: 230 files formatted,
  exit 0, outputs/debug-cycle-format.log.
- `-m ruff check src tests bench scripts examples`: clean, exit 0,
  outputs/debug-cycle-ruff.log.
- `-m mypy src scripts`: 86 files clean, exit 0, outputs/debug-cycle-mypy.log.
- `-m pytest -q -n 4 --basetemp=.tmp-pytest-debug-cycle-final --durations=12
  --junitxml=outputs/debug-cycle-final.xml`: **879 passed, 2 skipped, 305.70s**,
  exit 0; outputs/debug-cycle-final.log/XML. The skips are the pre-existing
  Windows symlink privilege cases; they are not locally verified.
- `-m pytest examples -q --testence-headless
  --basetemp=.tmp-pytest-debug-cycle-examples`: **5 passed, 1 intentional
  demo_failure skip, 11.32s**, exit 0; outputs/debug-cycle-examples.log.
- `bench/spa_latency.py > outputs/debug-cycle-spa.json`: exit 0, 20 iterations
  per fill mode, goto 89.54ms, Actions fill p50 10.33ms/p95 12.77ms. This is a
  single-host synthetic diagnostic with no acceptance threshold or pilot speedup claim.
- `-m testence.cli debug tests/test_debug_cycle.py::test_phase_timings_never_add_nested_totals
  --project . --json > outputs/debug-cycle-cli.json`: exit 0, exactly one passed
  test, assurance unverified (correct: no product claim/oracle), no integrity errors.

Full run **r-20261005-122059-53bd84**, evidence `runs/r-20261005-122059-53bd84/`;
controller and all four worker run.end events exited 0. Last CLI smoke run
**r-20261005-122715-7fbeff**, evidence `runs/r-20261005-122715-7fbeff/`.
[Compact receipt](2026-10-05-debug-cycle-receipt.json) pins source blob hashes,
lock/environment, full JUnit, run ends and raw artifact hashes.

DC26-01..06 are implemented and locally verified within the stated synthetic scope.
18 new controls cover original upload bytes/status/provenance, fetch/XHR and auth,
transform failure without resending, reset cleanup, delayed/stale/conflicting/missing
UI outcomes, exact selection/refusal/hash drift, timeout incomplete evidence,
parallel namespace cleanup, privacy, timings, status and MCP.
For an immediate UI failure example, cycle-5 artifact:
`.tmp-pytest-debug-cycle-5/test_debug_returns_aria_and_li0/runs/r-20261005-121919-bdd75e/`.
Its expected wrong-heading failure is a negative control, not an unresolved outer failure.
Browser start 882.8ms, driver start 312.0ms, browser launch 281.0ms,
context create 32.0ms/configure 250.0ms, close 262.4ms: child timings overlap
browser.start; never add all phases together.

Exact failing step in final required checks: **none**. Development failures remain above.
Changed files are discoverable via `git show --stat 2d51321`; receipts are added in the
following documentation commit. No independent agent review, private pilot replay,
publish or push is claimed.

Remaining uncertainty: full-run latency has an observed 111.93s call in
`tests/test_failure_diagnostics.py::test_a_default_browser_starts_while_another_run_holds_9222`.
Passing correctness does not solve that latency. Earlier long setup/teardown was
variable; no root cause or speedup is established. Actual consumer authoring duration,
parallel account safety, service workers/OOPIF/streaming, alternate OS/Python floors
remain unverified. Response provenance conservatively marks pending requests with the
same URL/method; concurrent identical requests have no request-ID correlation proof.
Auth timing is emitted on successful authentication (or explicit skip); failed auth
still has pytest setup duration, without a complete internal auth breakdown.

Next proving command (fresh unused basetemp, same interpreter/environment):
`-m pytest tests/test_failure_diagnostics.py::test_a_default_browser_starts_while_another_run_holds_9222
-q --basetemp=.tmp-pytest-debug-cycle-latency-next --durations=10`.
For the real authoring experience, run `testence debug <consumer-exact-node>
--project <consumer-root> --profile <declared-profile> --json` against a pinned build,
synthetic seed and authoritative cleanup; record wall time and phase evidence before
claiming the hour-long workflow is improved.
