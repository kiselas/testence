# T21 multi-project quality pack implementation receipt

Date: 2026-09-06. Status: locally implemented and verified.

## Delivered behavior

`testence quality apply` validates a versioned, digest-bound pack and pins its exact
name/version/digest in project configuration and lock data. Managed paths are contained;
credential-like files are rejected. Updates overwrite only the prior managed bytes.
Owned local overrides require reason, owner and future expiry and remain visible;
undeclared edits produce a repeatable conflict without replacing the accepted lock.

Accepted revisions retain a local history. `quality rollback` restores an exact digest,
refuses concurrent edits and keeps history. `quality summary` reconciles multiple run
directories, namespaces identical case names by project, supports project/owner/risk/
case filters and returns only violations, missing execution/proof and integrity actions.
It does not embed ledger events or raw evidence artifacts. Four public JSON schemas
cover pack, lock, sync and summary.

## Consumer receipt

[`outputs/.../t21-quality-pack-consumer-v2`](../../../outputs/audit-2026-09-06-followup/t21-quality-pack-consumer-v2/README.md)
contains two pack versions, three repositories, an intentional override, an intentional
conflict, retained rollback and a three-project actionable summary.

## Verification

| Check | Observed |
|---|---|
| Focused quality-pack tests | `3 passed in 0.53s` |
| Contracts/application/quality subset | `38 passed` before final fixes; focused rerun green |
| Ruff | quality implementation and tests pass |
| mypy | success, 52 source files |
| Three-repository consumer | catalog applied, billing override preserved, admin conflict, catalog rollback |

## Boundary

This closes the local pack/update/conflict/rollback and summary contract. A real TMS
import/diff is still part of the live integration boundary, and the full U5 acceptance
needs three actual repositories with independent credentials and TMS projects. This
receipt becomes immutable only after review and commit.
