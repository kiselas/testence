# ADR-0002: Python for the framework core

Status: accepted (2026-08-25)

## Context

Both Python and TypeScript provide mature Playwright clients. TypeScript has the
first-party Playwright test runner and agent tooling; Python provides pytest's
fixture, parametrization and plugin ecosystem. The Python client communicates with
the Playwright driver process, so the decision includes measurable IPC overhead.

## Experiment E1

`bench/e1_python.py` and `bench/node/e1_node.mjs` run the same seven actions over the
same synthetic page for 30 iterations. The checked-in snapshot recorded:

| metric | Node | Python | delta |
|---|---:|---:|---:|
| instant-step p50 | 9.43 ms | 10.28 ms | +9.0% |
| async assertion p50 | 310.32 ms | 311.70 ms | +0.4% |
| browser launch | 1664 ms | 1753 ms | +5.3% |

The acceptance criterion was Python p50 overhead below 15%. The snapshot satisfies
it, but it is hardware- and version-specific and must remain reproducible rather
than being treated as a universal claim.

## Decision

Use Python 3.10+, pytest and the synchronous Playwright API. Test bodies remain
linear; parallelism is provided by isolated processes (ADR-0012). Evidence and
configuration contracts stay language-neutral.

## Consequences

Node-only Playwright tools are integrations rather than in-process APIs. Projects in
other languages can consume the CLI and JSONL artifacts, and a future runner port can
reuse the contracts.

## Tripwire

Repeat E1 for meaningful Playwright upgrades. Reopen the decision if Python's p50
overhead reaches 15% on the maintained benchmark or an execution-critical capability
is only available in the TypeScript API.
