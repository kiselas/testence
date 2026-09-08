# T06 identity/schema implementation receipt

Date: 2026-09-06. Status: locally implemented and verified; review/commit SHA pending.

## Delivered contract

The public inventory is now:

| Artifact | Current writer schema | Compatibility input |
|---|---|---|
| ledger event | `testence/2` | `testence/1` |
| PlanSpec | `testence/planspec/2` | `testence/planspec/1` |
| verdict | `testence/verdict/2` | `testence/verdict/1` |
| evidence-pack index | `testence/evidence-pack/2` | legacy pack is not valid proof for a v2 verdict |
| pack manifest | `testence/pack-manifest/2` | `/1` remains readable as an artifact |

The shared test identity is `project_id`, `case_id`, `variant_id`, `run_id`,
`attempt_id`, and `proof_id`. Events add `event_id=<worker>:<seq>`. Pytest nodeid stays
the source locator. A PlanSpec scenario ID is the explicit case ID and therefore
survives source rename. Unbound tests receive a deterministic source-derived fallback.
Parameter values are retained only as canonical SHA-256 fingerprints.

The `/1` adapter runs before reconciliation for metrics, HTML, Allure and CTRF. It
preserves additive unknown fields, normalizes status spellings, and marks unavailable
proof as `unknown`/`unverified`. Unknown major versions fail. Allure result UUID uses
run/case/variant/attempt while history uses project/case/variant. CTRF carries the same
identity in `extra.testence_identity`.

Seven JSON schemas ship in the wheel: five current contracts and the PlanSpec/Verdict
v1 migration schemas. ADR-0019 records the decision; EN/RU guides and bundled agent
references use `/2`.

## Verification

| Check | Observed |
|---|---|
| Full pytest, `dev,parallel` environment | `207 passed, 2 skipped in 75.39s` |
| Windows serial/xdist lifecycle and identity subset | `36 passed in 15.62s` |
| Ruff | all checks passed; format clean |
| mypy | success, 43 source files |
| wheel + sdist | `uv build` succeeded |
| installed wheel, isolated cwd, Python `-I` | imported `testence/2`; found all 7 schemas and complete schema inventory |

The two skips are the existing Windows symlink capability skips. Tests cover 200
Unicode/long-prefix variants, raw-value exclusion, two project namespaces, explicit
case identity across source rename, distinct retry attempts, cross-run verdict
rejection, `/1` normalization and unknown-major rejection. Golden Allure and CTRF
outputs were regenerated and reviewed for the new identity fields.

Build artifacts are under `outputs/audit-2026-09-06-followup/t06-dist/`.

## Boundary

T06 does not close T07–T09. Controller-owned worker restart recovery, durable run
manifest validation, assertion IDs, plan/test/policy digests and assurance evaluation
remain open. A `/1` ledger cannot recover identity facts that were never recorded; its
proof remains unverified. This receipt is not immutable until review and commit.
