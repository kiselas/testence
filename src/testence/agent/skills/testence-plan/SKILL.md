---
name: testence-plan
description: Turn a feature request, product risk, bug report, or proposed change into a reviewable Testence PlanSpec with stable claim IDs, scenarios, and meaningful oracles. Use before browsing or authoring tests, and when coverage intent needs review or repair.
---

# Testence Plan

Create the semantic contract before creating test code or exploring the live UI.

## Workflow

1. Read the request, nearby product documentation, API/schema truth, and existing plans.
2. State the user or business outcome at risk. Separate independent outcomes into stable claims.
3. Give each claim a lowercase dotted ID. Record the observation sources that can prove it.
4. Prefer at least one oracle independent of the rendered UI when the claim concerns persistence, permissions, money, delivery, or another durable side effect.
5. Define positive, negative, permission, and failure scenarios only where the stated risk requires them. Every required claim must appear in a scenario.
6. Write `specs/<feature>.md` with human context and exactly one `testence-planspec` JSON block. Follow [references/planspec-v1.md](references/planspec-v1.md).
7. Validate the file with `testence plan validate <path> --json`. Fix every error before handing the plan to authoring.
8. Report the claim-to-scenario map, assumptions, exclusions, uncertain product facts, and validation result.

## Planning rules

- Plan observable outcomes, not browser gestures or selectors.
- Do not invent product behavior. Mark an unknown as an open question or exclusion.
- A toast, request status, or visible card does not by itself prove persistence.
- Keep IDs stable through wording changes; change an ID when the meaning changes.
- Do not browse the live UI or write test code unless the user also asks to continue into authoring.

## Completion gate

The phase is complete only when the PlanSpec validates, all required claims are covered by scenarios, each high-risk claim has a credible oracle, and unresolved ambiguity is visible to the reviewer.
