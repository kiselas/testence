# ADR-0022: Engine capability negotiation

Status: accepted. Date: 2026-09-06.

## Context

The original Engine protocol mixed platform-neutral lifecycle/evidence with every DOM
and CDP operation. A fake or future native adapter either had to pretend to implement
browser methods or fail late. Several observation helpers also selected `.first`
silently, allowing ambiguous targets to look healthy.

## Options compared

1. Keep one protocol and document unsupported methods.
2. Infer support with `hasattr` at the call site.
3. Publish versioned capabilities and small structural protocols, bind requirements in
   PlanSpec, and reject unsupported operations before they can become a skip or green.

## Decision

Use option 3. Capability documents are sorted, schema-validated data. Plan scenarios
declare requirements and pytest preflights them at collection. DSL operations enforce
the same contract and surface `UnsupportedCapability`. Playwright implements the R1 web
matrix; platform-neutral fake engines need only lifecycle and evidence. Locator
observations remain strict, and explicit fast actionability is evidence that lowers
assurance.

## Consequences

Adapters no longer expose Playwright types. Existing composite engines continue during
migration with assumed legacy web support, but this is not a conformance certificate.
New capabilities require a schema addition, implementation fixture and compatibility
decision.

## Tripwire

Split or version a capability when two backends attach materially different semantics
to the same name. Never widen a declaration to silence preflight.
