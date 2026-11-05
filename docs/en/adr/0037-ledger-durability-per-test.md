# ADR-0037: Ledger durability per test, flush per event

Status: implemented (engineering). Refines ADR-0003, whose fsync per event it
replaces by default; ADR-0009 and [kernels](../kernels.md) keep the writer, fsync'd
file I/O, in Python.

## Context

ADR-0003 made the ledger crash-safe with an `fsync` after every event. A step writes
two events, so a run of about 1 200 steps made some 2 400 `fsync` calls. On Windows
each costs milliseconds; measured on a 76-test run, about 10 s of the run was the
ledger waiting for the disk. Most of that protects against the death of the machine,
not of the process: a flushed line is already the operating system's, and survives a
killed or crashed test process, the case the ledger exists for.

## Options compared

- Keep `fsync` per event: the guarantee nobody needs between two passing steps, at a
  cost proportional to the suite.
- Sync on a timer: a failure could land just before a machine crash without being on
  disk, and the timing depends on load.
- Flush every event and sync at the points where evidence is read or would be lost:
  the end of a test, any failure, the pack, the manifest, the close: chosen.

## Decision

`EvidenceWriter` flushes every event. `evidence.durability` decides `fsync`:

- `test` (default): at `test.end`; on an event that records a failure or error (a
  `fail`/`failed`/`broken`/`error` status, `ok: false`, `outcome: failed`, an `error`
  field); at the manifest checkpoints (`run.start`, `collection.end`, `run.end`);
  when a failure pack binds the ledger prefix; at close.
- `step`: after every event, the ADR-0003 behaviour.

The setting is validated with the other `evidence` keys; an unknown value stops the
session before any test runs.

## Consequences

A killed process loses nothing in either mode. A machine crash in `test` mode can
lose the passing steps of the test that was running; the failure that stopped a test,
its end and everything a failure pack references are on disk. In the regression test
50 passing events cost at most 3 `fsync` calls instead of 50.

## Tripwire

Revisit if a ledger is found missing a failed test's events after a machine crash, or
if a reader starts to depend on events between two syncs being durable.
