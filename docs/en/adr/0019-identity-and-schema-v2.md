# ADR-0019: Stable identity and schema v2

Status: accepted (2026-09-06)

## Context

Schema `/1` used a short test label as an operational key and added lifecycle meaning
without a major migration. That allowed cases, parameter variants and retries to merge
in reports. Plan, pack and verdict documents also lacked one shared run/proof binding.

## Decision

Writers emit ledger `testence/2`, PlanSpec `testence/planspec/2`, Verdict
`testence/verdict/2`, evidence-pack `testence/evidence-pack/2` and pack-manifest
`testence/pack-manifest/2`.

The shared identity is `project_id`, `case_id`, `variant_id`, `run_id`, `attempt_id`
and `proof_id`; events additionally carry `<worker>:<seq>` as `event_id`. The pytest
nodeid remains a source locator and the display name remains presentation. A PlanSpec
scenario ID is the explicit logical case ID. Source-derived case IDs are allowed for
unbound tests but do not promise rename stability. Variant parameters are canonical
SHA-256 fingerprints, so raw credentials and business data do not enter artifacts.

All readers call one `/1` adapter before reconciliation. It retains additive unknown
fields, normalizes status spellings and marks missing legacy proof `unverified`; it does
not invent a successful assertion. Unknown majors fail before export. Result UUIDs use
run/case/variant/attempt; history identity uses project/case/variant.

## Consequences

Retries remain distinct results, explicit case IDs survive source renames, and pack and
verdict validation can reject cross-run or cross-project binding. `/1` schemas continue
to ship for migration and compatibility tests. New documents use `/2` only.
