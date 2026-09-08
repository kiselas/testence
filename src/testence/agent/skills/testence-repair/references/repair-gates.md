# Repair category gates

Start only from a verdict that validates against its PlanSpec and evidence pack.
Across every category, never weaken or remove a claim merely to make the rerun green.

| Verdict | Default action |
|---|---|
| `real_bug` | Do not change the test. Report or fix the product, then rerun the unchanged test. |
| `environment` | Do not change product expectations. Repair the environment or fixture outside this workflow, then rerun. |
| `ui_change` | Propose a semantic target update only when evidence and a prior fingerprint identify the same capability. |
| `test_bug` | Correct the implementation while preserving the claim and its product oracle. |
| `flaky_timing` | Replace accidental timing with a wait for the meaningful state; do not mask a stable failure with retries. |
| `behaviour_change` | Require an explicit acceptance source. Update the PlanSpec first, then align code and prove the new claim. |
| `null` | Do not repair. Collect the named missing evidence and triage again. |

## Proposal contract

Write `repair.json` with schema `testence/repair-proposal/1`. Bind it to the exact
`verdict.json`, PlanSpec, protected PlanSpec semantics, and source base with their
SHA-256 digests. Record:

- plan ID and claim ID;
- failed step intent and source location;
- validated verdict and confidence;
- old target/assertion and proposed target/assertion;
- fingerprint, candidate, oracle, and other decisive evidence references;
- rejected alternatives and ambiguity;
- exact diff;
- exactly one healthy proof (`passed`/`verified`), one defect control
  (`failed`/`violated`), and one harmless control (`passed`/`verified`);
- expected artifact paths and residual risk.

A high similarity score is supporting evidence, not permission to edit. If candidates are ambiguous or the capability is gone, preserve the failure and request review.

Validate before presenting the proposal as safe:

```bash
testence repair validate repair.json --verdict <pack>/verdict.json \
  --plan specs/<feature>.md --base tests/<test>.py \
  --pack <pack> --evidence-root <proof-root> --json
```

The validator rejects changed claims, stale source, missing proof artifacts, a green
defect control, or a repair category not authorized by the verdict.
