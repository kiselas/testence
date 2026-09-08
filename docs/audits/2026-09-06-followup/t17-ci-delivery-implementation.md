# T17 CI outcome and delivery implementation receipt

Date: 2026-09-06. Status: locally implemented and verified; live upload belongs to T16.

## Delivered behavior

`testence delivery run` requires explicit run, project, launch and job-run identities.
It refuses an incomplete/damaged or mismatched run, validates that every Allure result
attachment exists, and binds delivery to the exact artifact-directory digest. Timeout
and nonzero uploader exits are retried within a bounded 0–5 retry policy. A successful
`testence/delivery-receipt/1` is idempotently reused for the same identity and bytes.
Uploader stdout/stderr and command text are not persisted in the receipt.

`testence ci evaluate` produces `testence/ci-receipt/1` with separate test, quality and
delivery exits. Quality checks completion/integrity, execution or assurance policy,
and optional CTRF/JUnit inventory against the same reconciled ledger. Final exit keeps
the test failure first, then quality, then delivery, so a successful export/upload
cannot turn a failed, incomplete or unverified run green.

Both receipt schemas are packaged and listed in the public schema inventory.

## Consumer receipt

The installed CLI executed a two-test project with explicit run/project identity,
produced pytest-native JUnit plus Testence Allure/CTRF, ran a local identity-checking
delivery substitute, and evaluated all artifacts to `final_exit=0`. A second delivery
invocation used an exit-9 substitute but reused the already successful receipt and
remained exit 0. Inputs and receipts are under
[`outputs/.../t17-ci-consumer-v2`](../../../outputs/audit-2026-09-06-followup/t17-ci-consumer-v2/README.md).

## Verification

| Check | Observed |
|---|---|
| Full pytest | `304 passed, 2 skipped in 91.83s` |
| CI/testplan/export/lifecycle/contracts/docs subset | `83 passed, 1 skipped in 30.69s` |
| Ruff check and format | all checks passed; 89 files checked |
| mypy | success, 48 source files |
| Installed CLI consumer | test/delivery/quality/final exits all `0`; repeated delivery reused receipt |

Unit coverage includes test-exit preservation, assurance failure, CTRF/JUnit mismatch,
retry success, timeout exhaustion, wrong project, missing attachment and CLI receipt.

## Boundary

This closes T17's local execution and delivery contract. The local uploader substitute
does not satisfy the live TestOps upload/launch/history gate recorded in T16. This
receipt is not immutable until review and commit.
