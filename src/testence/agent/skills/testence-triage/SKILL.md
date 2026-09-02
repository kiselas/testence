---
name: testence-triage
description: Classify a failed Testence run from its bounded evidence pack and produce a validated, claim-level verdict. Use when a test fails, a verdict template exists, or someone asks whether the cause is product behavior, test code, UI drift, timing, or environment.
---

# Testence Triage

Judge from recorded evidence. Keep this phase read-only except for completing the pack's verdict file.

## Workflow

1. Locate the failed test's pack, `pack.json`, and `verdict.template.json`. Confirm the plan ID, test ID, and exact claim list.
2. Read the PlanSpec and pack summary first. Inspect only the bounded artifacts needed to decide each claim: steps, oracle results, network, console, accessibility state, fingerprints, and screenshots when present.
3. For every claim, record `passed`, `failed`, `blocked`, or `not_evaluated`, a concrete reason, and references to existing pack files.
4. Choose one causal verdict using [references/verdict-v1.md](references/verdict-v1.md). If material evidence is missing, set `verdict` to `null` and name the missing facts in `blocked_on`.
5. Copy or complete the template as `verdict.json` without changing its binding fields.
6. Run `testence verdict validate <pack>/verdict.json --plan <plan> --json`. Fix contract errors; do not bend the evidence to fit a class.
7. Report the verdict, confidence, claim-level reasoning, decisive evidence, blockers, and the appropriate next phase.

## Triage rules

- Evidence beats plausibility. Never claim that an action occurred if the ledger does not record it.
- Do not read secrets or broader raw artifacts merely to increase confidence. Abstain and request the missing bounded evidence.
- Distinguish an accepted behavior change from a product regression and locator drift from a missing feature.
- Do not edit test or product code during triage. A repair is a separate reviewable phase.

## Completion gate

The phase is complete only when every bound claim appears exactly once, all passed/failed claims cite existing evidence, the verdict validates against the pack and PlanSpec, and uncertainty is explicit rather than hidden in the summary.
