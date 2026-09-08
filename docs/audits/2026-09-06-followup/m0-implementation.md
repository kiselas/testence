# M0 implementation receipt: current-head compatibility

Date: 6 September 2026. Baseline: `7be8d025f81d9116ab267c59d440e14b377cfce7`.
State: implemented and verified in the local working tree; no release or remote action
was performed. A commit SHA can be recorded after the changes are reviewed and committed.

## Delivered

- One canonical execution-status normalizer accepts legacy `pass`/`fail` and current
  `passed`/`failed`; unknown values fail closed as `broken`.
- The common ledger reader reconciles collection, controller and worker records into
  one logical run. A started case without a terminal is `aborted`; an unstarted selected
  case is `not_run`; multiple process-level `run.end` records become one summary.
- New lifecycle events use full pytest nodeid as the collision-free key and keep
  `display_name` separately. Existing fingerprint stores have a short-name read fallback.
- Strict XPASS is retained as failed execution with explicit xpass metadata.
- Corpus grading requires complete expected scope, one logical run end and pytest exit
  0/1. `passed` no longer becomes a false red; empty/crashed controls are incomplete.
- README verdict JSON validates against the public contract. Reporting recipes use an
  explicit run ID, preserve pytest exit and state that TestOps selection is not yet
  implemented.
- EN/RU evidence and architecture guides describe lifecycle hooks and reader
  reconciliation.

## Regression evidence

Consumer tests cover duplicate display names, `pytest -x`, KeyboardInterrupt, xdist
worker crash, all ordinary pytest outcomes, status migration, fail-closed corpus grading
and the documentation examples. The worker-crash fixture terminates only its own
synthetic worker process.

Validation performed after implementation:

| Check | Result |
|---|---|
| Full pytest suite | 176 passed in 75.24 seconds |
| Ruff format/check | 95 files formatted; lint passed |
| mypy | 42 source files passed |
| Frozen local corpus | 51 item-runs; accuracy 1.0, false green 0.0, false red 0.0, right reason 1.0, heal recall 1.0 |
| Build and installed-wheel smoke | wheel/sdist built; isolated Python 3.12 consumer import, resources, CLI, pytest and HTML report passed |

The corpus result is evidence for the current 17-item fixture repeated three times. It
does not satisfy the R1 requirement for 40 unique cases, two OSS applications or an
independent reviewer.

## Remaining boundary

M0 prevents the reproduced false-green paths in current readers and exporters. It does
not replace E01/M1: schema `/2`, explicit project/case/variant/attempt IDs, durable run
manifest/recovery and all failure modes from R01–R03 remain required. TestOps selective
execution, assertion assurance and security boundaries also remain open.
