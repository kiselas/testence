# ADR-0013: Reporting integrations are exporters over the ledger

Status: accepted (2026-08-27)

## Context

`run.jsonl` already records tests, nested intent-bearing steps, oracles and evidence
packs. Adding a reporter SDK to test code would create a second source of truth and
couple the runner to each reporting platform.

## Decision

`run.jsonl` is the only source of truth. Reporting systems are deterministic sinks:

```text
versioned ledger -> parsed run model -> HTML / Allure / CTRF / future exporters
```

An exporter exposes `name` and `export(run, out_dir) -> list[Path]`. Built-ins are
stdlib-only and loaded lazily; third-party exporters register through the
`testence.exporters` entry-point group. JUnit XML remains pytest's responsibility.

Golden tests pin the byte-level output of bundled exporters. An exporter that needs
a client SDK belongs in a separate distribution so core startup and dependencies do
not change.

## Consequences

Tests contain no reporting calls. DSL intent strings become step names, markers
become tags and evidence-pack files become attachments. Allure and CTRF are
compatibility surfaces, not the internal data model. OpenTelemetry and service-side
reporters can be added without changing execution.

## Tripwire

If an exporter needs data absent from the ledger, extend the append-only evidence
schema instead of instrumenting test code. Repeated upstream format drift should
trigger explicit version pinning or deprecation.

## Amendment (2026-09-28): the allure compatibility listener

A suite moving from allure-pytest keeps its `@allure.*` decorators and
`allure.dynamic.*` calls. The `allure` package turns them into data only through
listeners registered in `allure_commons`, which allure-pytest provides; without it they
did nothing. `testence.allure_hooks` is the one module allowed to import
`allure_commons`, and only when that package is installed (it is not a dependency). It
registers the same listeners, so decorators create the pytest marks the ledger already
records, and it records dynamic values on `test.end` (`allure_dynamic`). It never writes
Allure results: the ledger stays the only source of truth, and the export is unchanged.
