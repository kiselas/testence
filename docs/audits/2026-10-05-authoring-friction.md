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

Final source revision, required checks, live latency gate and exact next command
will be recorded below after frozen-source runs.
