# T16 TestOps test-plan implementation receipt

Date: 2026-09-06. Status: offline implementation verified; live tenant acceptance open.

## Delivered offline behavior

The pytest plugin consumes `ALLURE_TESTPLAN_PATH` before execution. It accepts the
standard Allure `version: "1.0"` shape and resolves each entry by TestOps/Allure ID,
exact pytest `fullName`, or the collision-safe
`testence://<project>/<case>/<variant>` selector. Test IDs may be strings or integers
and are normalized to strings. The PlanSpec marker exposes optional `allure_id`; the
same ID is carried into Allure results.

Every plan entry must resolve to exactly one collected item, and two entries cannot
silently select the same item. Unknown versions or fields, malformed JSON, duplicate,
unresolved and ambiguous entries fail with pytest usage error before a test starts.
An empty plan also fails by default. `--testence-empty-testplan=noop` (or
`TESTENCE_EMPTY_TESTPLAN=noop`) is the only explicit zero-test path and records a
successful, complete zero-test run rather than falling back to the full suite.

## Verification

| Check | Observed |
|---|---|
| T16 + lifecycle/export/contracts/docs subset | `78 passed, 1 skipped in 29.96s` |
| One-of-eight selection | exactly `test_cases.py::test_3` started and ended |
| Variant selection | only the requested `chromium` parameter variant ran |
| Invalid/unresolved plans | exit 4, no `test.start`, run status `usage_error` |
| Empty plan | exit 4 by default; explicit no-op exits 0 with no `test.end` |
| Ruff/mypy before final import cleanup | behavior tests passed; final quality rerun pending |

The contract follows the standard Allure test-plan shape documented by Allure Report
and the `ALLURE_TESTPLAN_PATH` flow documented by the official `allurectl` cookbook.

## External gate

A real TestOps tenant is not configured in this workspace. The required
select → CI → upload → launch/history round trip, screenshots or sanitized API
receipts, project mismatch test and upload retry behavior cannot be claimed. T17 can
complete the local CI/delivery contract without credentials, but T16 remains externally
unaccepted until a test tenant and owner-provided access exist. No upload or external
configuration change was attempted.
