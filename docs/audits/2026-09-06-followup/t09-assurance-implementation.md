# T09 assertion and assurance implementation receipt

Date: 2026-09-06. Status: locally implemented and verified; review/commit SHA pending.

## Delivered behavior

PlanSpec `/2` now contains a strict assertion inventory. Each assertion has a stable
`assertion_id`, declared `claim_id`, oracle kind, required/optional flag, and optional
human-readable expected outcome. Every required claim must have at least one required
assertion. Unknown claim bindings, duplicate assertion IDs, and unsupported oracle kinds
are rejected. Legacy PlanSpec `/1` stays readable without invented proof.

`Actions.verify`, `oracle.verify`, and `save_and_verify` can emit typed `assertion`
events containing assertion/claim identity, oracle kind, outcome, sanitized expected and
actual values, diff, and repository-relative source location. Supplying only one of
assertion or claim ID is rejected. The event model and packaged JSON schema enforce the
same required fields and outcome vocabulary.

The runner binds each attempt to SHA-256 digests of the exact PlanSpec file and test
source plus the versioned default assurance policy. Reconciliation evaluates assurance
independently of pytest execution:

- `verified`: all required assertions ran exactly once, passed, matched their declared
  claim/oracle binding, and all proof digests match;
- `violated`: an assertion produced a decisive failed outcome;
- `inconclusive`: execution/oracle availability could not settle the claim;
- `unverified`: required proof is absent, duplicated, unknown, misbound, or stale.

A pytest `passed` outcome without required proof therefore stays `passed` on the
execution axis and becomes `unverified` on the assurance axis. Optional assertions do
not increase the required denominator. HTML shows both axes; Allure labels and CTRF
extras carry assurance and reasons. Diagnosis never rewrites execution outcome.

`testence/assurance-policy/1` is part of the public schema inventory. Nine JSON schemas
ship in the wheel.

## Verification

| Check | Observed |
|---|---|
| Full pytest, `dev,parallel` environment | `227 passed, 2 skipped in 86.02s` |
| Assurance/contracts/metrics/event/lifecycle subset | `53 passed, 1 skipped in 21.74s` |
| Real pytest consumer | pass without proof → `unverified`; pass with bound proof → `verified` |
| Ruff check and format | all checks passed; 81 files formatted |
| mypy | success, 45 source files |
| wheel + sdist | `uv build` succeeded |
| installed wheel, isolated cwd, Python `-I` | 9 schemas; synthetic passed proof evaluated `verified` |

Tests also cover failed proof without status rewriting, optional assertions, stale plan
digest, duplicate proof, schema/runtime parity, required-claim coverage, and unknown
claim binding. Golden Allure and CTRF outputs were regenerated for the new assurance
projection and reviewed.

Build artifacts are under `outputs/audit-2026-09-06-followup/t09-dist/`.

## Boundary

This closes the local T09 foundation. T13 still owns richer expected-state timing,
request correlation, persistence windows, roles and adversarial product-state corpus.
T14 owns verdict pointer/digest binding and repair proof. The M1 security receipt still
requires its stated Linux/Windows path matrix and independent review before release
acceptance. This receipt is not immutable until review and commit.
