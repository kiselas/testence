---
name: testence-repair
description: Turn an evidence-backed Testence verdict into a reviewable test-maintenance proposal and targeted proving rerun. Use after triage when UI drift, a test bug, timing defect, or accepted behavior change may require test code or PlanSpec changes.
---

# Testence Repair

Repair only after the failure has a validated verdict. A locator guess is not a repair.

## Workflow

1. Read the validated `verdict.json`, PlanSpec, evidence pack, failing source, and the last relevant green fingerprint or run.
2. Apply the category gate in [references/repair-gates.md](references/repair-gates.md). Stop when the verdict calls for a product or environment fix instead of a test change.
3. Create a `testence/repair-proposal/1` document before editing: bind the verdict, PlanSpec semantics and source base digests; record the affected step, exact diff and proving scope.
4. If the user requested only investigation or a proposal, do not apply it. If implementation was requested and host permissions allow it, make the smallest visible edit.
5. Run the targeted test on a healthy target, a defect control where the claim must fail, and a harmless control. Record their execution and assurance results in the proposal.
6. Confirm that plan/claim bindings and independent oracles remain present, then run `testence repair validate` with the verdict, plan, source base, pack and proof root.
7. Report the diff, rerun results, artifact paths, residual risk, and whether the proposal is ready for human review.

## Repair rules

- Never silently rebind a locator at runtime.
- Never weaken or remove a claim to make a run green.
- Do not replace an independent oracle with only UI evidence.
- Do not add arbitrary sleep, broad retries, or a less-specific selector as a generic fix.
- An accepted behavior change updates the PlanSpec before or with test code; evidence of change alone is not acceptance.
- Preserve local repository policy and produce a reviewable diff.

## Completion gate

The phase is complete only when the category permits test maintenance, the change is minimal and reviewable, the intended claim still fails on its negative control, the targeted scope passes after restoration, and no broader claim or oracle was weakened.
