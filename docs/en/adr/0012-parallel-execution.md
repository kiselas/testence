# ADR-0012: Parallel execution by process shard

Status: accepted (2026-08-26)

## Context

Browser tests benefit from process parallelism, but shared evidence files, debug
ports and seed data make naive sharding unsafe.

## Options

- Threads with the Playwright sync API: rejected because the API is not thread-safe.
- One async browser with many contexts: deferred because it would change the public
  engine and DSL shape.
- Pytest-xdist process shards: selected for isolation and compatibility.

## Decision

Parallelism is optional process sharding with four invariants:

1. A test owns its precondition and does not depend on another test's output.
2. Each worker writes its own ledger shard; readers merge shards by timestamp.
3. Seed markers include the worker id, and cleanup cannot delete another worker's
   data.
4. Machine-wide resources, including CDP ports, receive worker-specific offsets.

`TESTENCE_RUN_ID` is established before workers start so all shards belong to one
logical run. Heal-memory files follow the same sharding rule.

## Consequences

Each worker pays browser and authentication setup but gains crash and state isolation.
Serial execution remains supported and is the default because application fixtures
may not be shard-safe. Reports and exporters read the merged ledger, not individual
files.

## Tripwire

Revisit the async multi-context option when per-worker setup dominates run time.
Any lost ledger event, cross-worker data deletion or higher parallel false-red rate
is a correctness defect and blocks parallel execution.
