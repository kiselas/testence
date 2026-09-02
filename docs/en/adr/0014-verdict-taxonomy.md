# ADR-0014: Behaviour-change and test-bug verdicts with explicit abstention

Status: accepted (amended with PlanSpec-aware `test_bug`, 2026-08-28)

## Context

A failed expectation is not always a product defect. The UI, API and network may
agree on a coherent new behaviour while the test encodes an older specification.
Calling that `real_bug` is misleading; calling it `ui_change` is also wrong when
element addressing did not drift.

Evidence cannot prove whether a coherent change was intended because the
specification may be outside the pack. The contract therefore needs both a distinct
observation and an abstention channel.

## Decision

The verdict set is:

- `real_bug`: observable layers disagree or the requested operation fails;
- `test_bug`: the product and current PlanSpec agree, but the test implementation
  contradicts them;
- `behaviour_change`: the product behaves coherently but differently from the current
  PlanSpec/test expectation;
- `ui_change`: the element address or presentation contract drifted;
- `flaky_timing`: timing or nondeterminism explains the failure;
- `environment`: target availability, configuration or version mismatch explains it.

`test_bug` requires positive evidence that at least one PlanSpec claim passed; merely
changing an assertion until the run turns green is not enough. `blocked_on` optionally
names the missing fact that would settle a provisional verdict, usually the current
specification or change record. A judge must not infer intent from absence of errors
alone.

Failure grouping is separate from verdict classification and remains future work.

## Consequences

Evidence packs are self-describing and carry the available taxonomy. The addition of
`test_bug` changes accuracy baselines, so benchmark revisions must be reported with
scores and include at least one test-implementation control.

## Tripwire

The synthetic corpus must contain coherent-change controls, test-implementation controls
and coherently wrong defects. If `behaviour_change` or `test_bug` recall improves by
misclassifying real defects, narrow the prompt to require positive cross-layer and
PlanSpec evidence and use `blocked_on` more often.
