---
name: testence-author
description: Discover, implement, and prove deterministic Testence browser tests from a validated PlanSpec. Use when asked to generate coverage, turn approved claims into pytest code, validate selectors and oracles, or complete the plan-to-evidence authoring phase.
---

# Testence Author

Turn an approved PlanSpec into a deterministic, reviewable test and prove that it detects the claimed failure.

## Workflow

1. Locate the PlanSpec and run `testence plan validate <path> --json`. Do not author against an invalid plan.
2. Build a small claim-to-proof map: action, UI observation, independent oracle, seed, cleanup, and expected failure signal.
3. Confirm the target, account/profile, mutation boundary, seed isolation, and allowed browser actions. Do not touch production or shared data without explicit authority.
4. Inspect source, API schemas, and project adapters. Use controlled browser discovery only against the approved target.
5. Prefer role plus accessible name, then label/placeholder, stable test ID, and only then CSS. Keep application-specific targets in project code.
6. Write ordinary pytest plus Testence actions. Bind the exact plan path and claim IDs with `@pytest.mark.testence` as shown in [references/proof-gates.md](references/proof-gates.md).
7. Prove every claim on the healthy target, exercise a seeded defect or negative control, verify failure for the intended reason, restore the target, and rerun green from a clean seed.
8. Report changed files, exact commands, claim coverage, evidence/run paths, remaining ambiguity, and any proof gate that could not be completed.

## Authoring rules

- Generated code is a hypothesis until it has run live.
- Never replace an independent oracle with only rendered UI or an HTTP acknowledgement.
- Avoid arbitrary sleeps, broad text matches, unbounded retries, and silent locator fallback.
- Do not modify product code merely to make the generated test pass.
- Keep accepted replay free of an LLM; discovery is authoring-time only.

## Completion gate

The phase is complete only when the exact code passes from a clean seed, fails on the intended negative control for the expected claim, passes again after restoration, and preserves every claim binding in the resulting ledger or evidence pack. If a negative control is unavailable, label the test as generated but not fully proven.
