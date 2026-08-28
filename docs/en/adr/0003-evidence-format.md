# ADR-0003: Own versioned run.jsonl as the source of truth

Status: accepted (2026-08-25)

## Context

The framework's central artifact is the evidence a run leaves behind. Agents read it
to deliver verdicts (token-budgeted), humans read a report rendered from it, metrics
aggregate over it. It must survive crashes (that is exactly when it matters), be
diffable, and stay stable across framework versions.

## Options compared

| | Own JSONL (`testence/1`) | Playwright trace.zip | Allure results as primary |
|---|---|---|---|
| Schema stability | ours, versioned envelope | private, "not documented, may change between versions" | stable but *report*-shaped |
| Agent-readable in-context | yes: line-per-event, token budgets first-class | needs unpacking; sizes unbounded | XML/JSON per test, no step timing granularity we need |
| Crash-safe | append-only + fsync per event | written on context close — lost on hard crash | written at end |
| Carries intents/fingerprints/oracle diffs | yes (our fields) | no | via labels, awkwardly |
| Human time-travel viewer | our HTML report (v0 simpler) | excellent (trace viewer) | Allure UI |
| Cost | we own a schema | free | free |

## Decision

Own `run.jsonl`, schema `testence/1`: envelope `{v, run, seq, ts, kind, test?}` +
per-kind payload; append-only; fsync per event; UTF-8 with `\n` on all platforms.
Green-path events stay compact; failures attach an evidence-pack directory with
per-section token budgets (normative doc:
[`evidence-schema.md`](../evidence-schema.md)).

Playwright trace.zip: optionally recorded *in addition* (free time-travel viewer for
humans), never parsed as a data source. Allure results: an *export* generated from
run.jsonl for TestOps integration, not the source of truth.

## Consequences

- One source of truth, three renders (agent pack, HTML report, Allure export) —
  they can never disagree.
- We pay for schema evolution: `testence/1` fields are append-only; breaking changes
  bump the version and the parser refuses foreign versions loudly.
- Every run is a benchmark: timings ride in the ledger, `testence metrics` aggregates.

## Tripwire

Playwright ships a stable, documented trace format → run the comparison: triage
verdicts from our pack vs from their trace on the failure corpus
(`verdict_accuracy`, `tokens_per_triage`). Losing both → migrate, keeping the
envelope as an adapter.
