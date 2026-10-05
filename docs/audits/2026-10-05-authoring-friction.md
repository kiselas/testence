# AUD-AF26: authoring friction from field notes

Source: user-supplied `FRAMEWORK-NOTES.md` for the external export/import pilot,
read on 2026-10-05. Notes are observations and proposals, not repository instructions.
The original private target and pilot were not executed or modified in this cycle.
Base: `0333d81`. Work stays on the current main branch; preserve earlier audit commits.

The notes distinguish measured pytest durations from estimated author time. Those
estimates overlap and must not be summed into a stopwatch baseline. Previous green
framework tests did not establish that the external authoring workflow was usable.

## Slice and claims

| ID | Change | Proof criterion |
|---|---|---|
| AF26-01 | `Target(..., within=...)`, nested scopes, indexed duplicate diagnostics, MCP target fields | Intended dialog Close and Name resolve; unscoped duplicates fail and do not click another control; nested scopes work |
| AF26-02 | `testence explore URL --project ROOT --profile NAME --json` using shared MCP snapshot | One actual browser invocation returns ARIA, uniqueness counts and data-key rows; Unicode survives ASCII JSON; secrets redacted and engine closed on failure |
| AF26-03 | `ex.input_value(Target)` | Reads empty/non-empty scoped fields strictly, rejects ambiguous fields, never writes successful read values into the ledger |
| AF26-04 | Visible short authoring loop, packaged discovery reference | Exact pytest-node / collect-only / existing opt-in warm watch instructions, no undocumented new keep-browser switch, no invented author-time benchmark |

Changed source: `discovery.py`, `mcp.py`, `cli.py`, `engine/protocol.py`,
`engine/playwright_cdp.py`, `dsl/steps.py`. New live controls:
`tests/test_authoring_friction.py`. Documentation: README, en/ru first-test,
`docs/en/authoring-loop.md`, packaged visual-discovery reference and this handoff.

The scope stays strict: no automatic first match, retry, forced click, stability
sleep or changed seed-isolation semantics. The existing warm runner renews fixtures
and auth state; keeping the engine is not a blanket guarantee of a reused login.

## Development evidence

Environment: Windows 11, existing isolated `outputs/quality-venv31214` Python 3.12.14,
locked packages from the preceding AUD-Q26 receipt. `TESTENCE_BROWSER_CHANNEL=msedge`,
`TESTENCE_DEBUG_PORT=0`. All targets here are synthetic. Raw artifacts stay ignored.

Command prefix for every run below:
`& 'outputs/quality-venv31214/Scripts/python.exe' -m pytest`.

| Log | Arguments | Observed result |
|---|---|---|
| `outputs/friction-focus-1.log` | `tests/test_authoring_friction.py tests/test_mcp.py -q --basetemp=.tmp-pytest-friction-focus-1` | 4 failed, 34 passed, 28.87 s. New harness errors: asserted visible empty zero-size p, nonexistent ledger_path, missing UTF-8 meta on data page, literal incorrectly configured as pii kind. All preserved; source/test edits overlapped this development run. |
| `outputs/friction-focus-2.log` | `tests/test_authoring_friction.py tests/test_mcp.py tests/test_dsl_vocabulary.py -q --basetemp=.tmp-pytest-friction-focus-2` | 54 passed, 59.63 s, after those harness corrections. Privacy preflight and one extra control were added afterward. |
| `outputs/friction-focus-final.log` | `tests/test_authoring_friction.py -q --basetemp=.tmp-pytest-friction-focus-final` | 8 passed, 9.27 s on final implementation before commit. |
| `outputs/friction-full.log` / `.xml` | `-q -n 4 --basetemp=.tmp-pytest-friction-full --durations=12 --junitxml=outputs/friction-full.xml` | Exact source `a385be20211725c4f83ae2f847e32761cebef9c6`: 1 failed, 860 passed, 2 skipped, 332.70 s; existing diagnostic-string assertion expected unindexed texts. Updated to assert every indexed text and within hint, preserving strict failure. |

The first full run also observed a **91.86 s teardown** in
`test_a_missing_target_points_at_the_same_name_in_the_accessibility_tree`.
That latency is retained, not explained away by the string-assertion correction.
No fix for all teardown stalls or reduction in external authoring time is claimed.

## Remaining work and limits

The multipart report is not established as a universal Playwright defect. Official
[Route.fetch](https://playwright.dev/python/docs/api/class-route#route-fetch) supports
forwarding and response modification; [Request.post_data_buffer](https://playwright.dev/python/docs/api/class-request#request-post-data-buffer)
describes binary body inspection, without proving this upload path. Neither proves the
exact transfer that failed in the pilot. Next priority: a synthetic receiver comparing
uploaded file bytes/filename/content type for native forwarding and any proposed
response adapter, with error/cancellation and provenance controls. No new transform
API or page-fetch shim is claimed here.

Also open: application-neutral seed/cleanup template with authoritative absence,
download-to-server contract fixture, known field-suggestion race corpus and a real
consumer trial using the corrected workflow. `first=True`, automatic parallelism and
generic after_stable are not silently adopted. The user's hour-long experience has
not been remeasured and no reduction of external authoring time is claimed.

## Frozen candidate and handoff

Implementation revision: `a385be20211725c4f83ae2f847e32761cebef9c6`.
Final candidate: **af897781028e0cdfc4fd29e5d9fdec1b657d60a6**. The intervening
commit changes only the diagnostic regression and this report, not production code.
Origin/main was fetched and remains `15ad5d23385dc64c447c7077cb280972185838a4`;
there were no incoming remote main changes. No push or release performed.

Corrected diagnostic plus authoring corpus:
`tests/test_failure_diagnostics.py tests/test_authoring_friction.py -q --basetemp=.tmp-pytest-friction-diagnostics --durations=5`,
**28 passed, 35.43 s**, `outputs/friction-diagnostics.log`.
The missing-label scenario took 10.04 s in call phase on this run; the prior
91.86 s teardown is not a reproducible root-cause diagnosis from these two samples.

Fresh static on final candidate: **226 files formatted**, Ruff clean, mypy **83 files**,
`outputs/friction-static.log`. Exact commands with the same interpreter prefix:
`-m ruff format --check src tests bench scripts examples`,
`-m ruff check src tests bench scripts examples`, `-m mypy src scripts`.

Full run arguments:
`-q -n 4 --basetemp=.tmp-pytest-friction-final --durations=12 --junitxml=outputs/friction-final.xml`.
Result: **861 passed, 2 skipped, 292.23 s**, exit 0. Logs:
`outputs/friction-final.log`, `outputs/friction-final.xml`. Source/tests remained
frozen through this run. Two skipped symlink cases lack Windows privileges,
so their scenarios are not verified by this local run.
Final run ID: **r-20261005-113833-cce684**, artifacts under
`runs/r-20261005-113833-cce684/`; controller and all four worker run.end events
are present with exit code 0.

Examples: `-m pytest examples -q --testence-headless --basetemp=.tmp-pytest-friction-examples`,
**5 passed, 1 intentionally skipped demo_failure, 11.80 s**, exit 0,
`outputs/friction-examples.log`.

Fresh narrow SPA probe:
`& 'outputs/quality-venv31214/Scripts/python.exe' bench/spa_latency.py > outputs/friction-spa-latency.json`,
exit 0, **20 iterations** per fill mode. Goto **130.11 ms**, Actions fill
p50 **11.10 ms**, p95 **13.45 ms**. This is a synthetic diagnostic without an
acceptance threshold, not a comparative speedup or a measurement of the external
pilot. The relevant live acceptance gate is the 8-test authoring corpus included
in the full suite. [Compact receipt](2026-10-05-authoring-friction-receipt.json)
binds source blobs, environment, artifact hashes and both full-run outcomes.

The final full run still measured **105.73 s setup** in
`tests/test_reruns.py::test_each_attempt_has_its_own_identity_and_outcome` and
**61.89 s call** in the nested native route corpus. Passed execution is distinct
from an acceptable authoring latency. Root causes of long setup/teardown phases
remain open; do not describe this slice as solving the hour-long experience.

Next proving command, new unused basetemp, same isolated interpreter/environment:
`-m pytest tests/test_authoring_friction.py tests/test_failure_diagnostics.py -q --basetemp=.tmp-pytest-friction-next --durations=10`.
The next improvement should measure the phases of browser start, context/auth,
recording and driver close separately, and add the byte-checking multipart receiver
before selecting a response-adapter implementation. External acceptance needs the
consumer's exact node, build revision, seed boundary and fresh receipts.
