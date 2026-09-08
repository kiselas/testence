# T15 Allure projection and consumer implementation receipt

Date: 2026-09-06. Status: locally implemented and verified; review/commit SHA pending.

## Delivered behavior

The Allure projection now gives every attempt three deliberate identities:
`testCaseId` for `(project, case)`, `historyId` for `(project, case, variant)`, and a
result UUID for `(run, case, variant, attempt)`. Retries therefore remain separate
results in one stable history, and projects or variants cannot collide.

PlanSpec `/2` accepts typed `owner`, requirement links and issue links; scenario risk
travels with its selected case. Pytest writes these values once into `test.start`.
The shared export model retains them and setup/teardown phase records. Allure emits
owner/risk/requirement/issue labels, standard `tms` and `issue` links, digest-only
parameters, fixture containers, all attempts, status/assurance, nested steps and
redacted evidence attachments. Older ledgers still export with empty optional fields.

## Real consumer receipt

Pinned `allure@3.14.3` accepted the generated result directory and produced its
Awesome single-file report. The report was served locally, opened through the app,
and returned HTTP 200. Its own `summary.json` parsed two results: one passed and one
failed. The consumer inputs, report, hashes and exact commands are in
[`outputs/.../t15-allure-consumer-v2`](../../../outputs/audit-2026-09-06-followup/t15-allure-consumer-v2/README.md).

## Verification

| Check | Observed |
|---|---|
| Full pytest | `291 passed, 2 skipped in 85.24s` |
| Export/contracts/lifecycle/docs subset | `70 passed, 1 skipped in 22.21s` |
| Focused export/contracts/lifecycle/repair | `80 passed, 1 skipped in 27.09s` |
| Ruff check and format | all checks passed; 85 files checked |
| mypy | success, 46 source files |
| Allure Report consumer | `allure@3.14.3`, generation successful, HTTP 200 |

The skipped checks are the already recorded Windows link-creation boundary tests.

## Boundary

This closes local T15 including a real Allure Report consumer. T16 still owns offline
TestOps plan selection plus the live tenant round trip. T17 owns CI delivery outcome
and upload receipt semantics. No TestOps upload was attempted. This receipt is not
immutable until review and commit.
