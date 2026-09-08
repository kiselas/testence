# T07–T08 lifecycle and ledger integrity implementation receipt

Date: 2026-09-06. Status: locally implemented and verified; review/commit SHA pending.

## Delivered behavior

The controller now owns one logical result across serial and xdist execution. Collection
inventory is persisted before execution, worker shards are merged by timestamp, and the
reader produces exactly one logical `run.end`. A selected case that never starts becomes
`not_run`; a started case without a terminal becomes `aborted`. Worker crash events retain
the controller envelope and name the failed worker separately. Replacement worker shards
are included after an xdist restart. Repeated pytest protocols allocate a new
`attempt_id` and `proof_id`; consumers retain every attempt independently.

The controller writes `manifest.json` using `testence/run-manifest/2`. The checkpoint is
flushed, fsynced, and atomically replaced after `run.start`, `collection.end`, and
`run.end`. The completed manifest binds project/run identity, selected scope, exit state,
and the exact ledger set by relative filename, byte size, and SHA-256.

The shared reader validates the manifest and event stream before reconciliation. It
retains complete records before an unterminated JSONL tail and emits a read-only
`ledger.damage` projection. Empty or missing ledgers, incomplete/mismatched manifests,
mixed run/project identity, duplicate event IDs, duplicate attempt terminals, and shard
digest drift force `run_status=incomplete`. Corruption in a completed line and unknown
schema majors raise a clear integrity error. Legacy `/1` ledgers without a run manifest
remain readable with unverified identity.

HTML displays an `INCOMPLETE RUN` banner. Allure environment data and CTRF summary extras
carry the logical run status and integrity errors. Metrics list incomplete run IDs. The
raw append-only ledgers are never rewritten by recovery.

Eight JSON schemas now ship in the wheel, including `run-manifest.schema.json`, and the
public schema inventory names all current contracts.

## Verification

| Check | Observed |
|---|---|
| Full pytest, `dev,parallel` environment | `217 passed, 2 skipped in 82.29s` |
| T07/T08 lifecycle, identity, reader, exporter and report subset | `60 passed, 2 skipped in 20.71s` |
| Focused T07 retry and xdist restart set | `16 passed in 18.40s` |
| Ruff check and format | all checks passed; 79 files formatted |
| mypy | success, 44 source files |
| wheel + sdist | `uv build` succeeded |
| installed wheel, isolated cwd, Python `-I` | 8 schemas found; complete manifest read as `passed` |

The recovery regression matrix covers torn tail, completed-line corruption, empty and
missing ledgers, running manifest, manifest digest mismatch, duplicate event ID,
duplicate terminal identity, and unknown major. The xdist test kills a synthetic worker,
allows one replacement, verifies the `gw2` shard, and confirms the crashed test is
`aborted` while remaining tests finish.

Build artifacts are under `outputs/audit-2026-09-06-followup/t08-dist/`.

## Boundary

This closes the local implementation scope of T07 and T08. It does not close R1 or the
whole M1 milestone. T09 assurance gates, plan/test/policy digests and required proof are
still open. The two skips are the existing Windows link-creation capability skips; the
release gate still requires the path/link matrix on Linux and a capable Windows host.
This receipt is not immutable until review and commit.
