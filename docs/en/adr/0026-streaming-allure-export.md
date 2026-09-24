# ADR-0026: Stream Allure results as tests end

Status: accepted (ADR-0013 tripwire).

## Context

ADR-0013 rendered Allure results after the run and named the tripwire: if post-run
export blocks adoption, export incrementally on each `test.end`. TestOps launches fed by
`allurectl watch` stayed empty until the end, and a CI job killed by a timeout left no
results at all.

## Options compared

- **Allure SDK in the runner.** A second record of what happened, and a reporting
  dependency in every test process.
- **Periodic post-run export.** Repeated work and still nothing after a kill.
- **An evidence-writer listener.** Each redacted event is handed to a sink after it is
  durable; on `test.end` the sink renders that test with the post-run export functions.

## Decision

`--testence-allure-results DIR` (or `TESTENCE_ALLURE_RESULTS`) attaches the listener.
Attachments, the fixture container and the result are written in that order, each
through a per-process staging directory and an atomic rename; `environment.properties`
and `categories.json` are written at `run.end`. Listener failures become a `note` and
never change the pytest result. Parallel workers stream their own tests.

## Consequences

The streamed directory is byte-identical to `testence export --to allure` of the same
run. `allurectl watch` can upload results during the run. The post-run export remains
the path for re-exporting with a different attachment policy.

## Tripwire

Any byte difference between streamed and post-run output, a partially written file seen
by a watcher, or a lost or duplicated result under `-n` blocks this decision.
