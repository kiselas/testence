# T14 bound verdict and repair implementation receipt

Date: 2026-09-06. Status: locally implemented and verified; review/commit SHA pending.

## Delivered behavior

Verdict `/2` now carries the exact plan, test source, assurance policy and evidence-pack
digests. Validation hashes the immutable pack manifest bytes, then verifies every
manifested artifact by relative path, byte size and SHA-256. Editable verdict files are
excluded from that manifest to avoid a circular digest. A file outside the manifest,
unsafe path, changed artifact, stale digest or mixed attempt fails closed.

Evidence fragments on JSON and JSONL are resolved as RFC 6901 JSON Pointers. Escaped
tokens are decoded, missing targets are rejected, and an event that exposes identity
fields must belong to the verdict's run, attempt and proof.

The new `testence/repair-proposal/1` contract binds a reviewable patch to the verdict
file, PlanSpec digest, protected PlanSpec semantics and exact source base. Only
`ui_change`, `flaky_timing` and `test_bug` authorize their corresponding repair kind.
Changed claims, stale source and mismatched identity are rejected.

Safe repair proof requires exactly three complete, integrity-checked run manifests:
a healthy run that is `passed/verified`, a defect control that is `failed/violated`,
and a harmless control that is `passed/verified`. The validator reads the actual
ledgers and refuses declarations that disagree with their execution or assurance.
`testence repair validate ... --json` exposes the same contract to agent clients.

## Verification

| Check | Observed |
|---|---|
| Full pytest | `289 passed, 2 skipped in 104.76s` |
| T14 contracts/pack/docs subset | `48 passed in 1.35s` |
| Ruff check and format | all checks passed; 85 files checked |
| mypy | success, 46 source files |

The two skips are the already recorded Windows link-creation boundary tests. The CLI
route, schema inventory, pack digest, pointer resolution, cross-attempt rejection,
artifact tampering, stale digests, claim protection, stale base and the three-control
proof matrix have executable coverage.

## Boundary

This closes the local T14 implementation. Human review of any proposed source diff is
still required by the workflow. T22 owns receipts from two real agent clients, and T23
owns the independent frozen correctness corpus and external review. This receipt is not
immutable until review and commit.
