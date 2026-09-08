# Verdict v2 reference

The current contract is `testence/verdict/2`. Copy every identity field from the pack template unchanged; they bind the decision to one immutable attempt and proof.

## Causal taxonomy

| Verdict | Use when |
|---|---|
| `real_bug` | The current PlanSpec is valid and the product outcome violates it. |
| `test_bug` | Product evidence satisfies the PlanSpec, but the test implementation contradicts it. At least one claim must be proven `passed`. |
| `behaviour_change` | Evidence shows intentional behavior different from the current PlanSpec. Do not assume acceptance; cite the product decision or mark it blocked. |
| `ui_change` | The intended capability remains, but its semantic address or presentation changed. A missing capability is `real_bug`, not locator drift. |
| `flaky_timing` | The same product state alternates because synchronization is nondeterministic and evidence excludes a stable product failure. |
| `environment` | Auth, service availability, test data, browser, or infrastructure prevented a product judgment. |
| `null` | Material evidence is missing. List each missing fact in `blocked_on`. |

## Minimal shape

```json
{
  "schema": "testence/verdict/2",
  "project_id": "checkout",
  "case_id": "discount",
  "variant_id": "default",
  "attempt_id": "attempt-controller-1",
  "run_id": "r-20260906-120000-abc123",
  "proof_id": "proof-0123456789abcdef0123",
  "plan_digest": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "test_digest": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "policy_digest": "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
  "pack_digest": "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
  "plan_id": "checkout.discount",
  "test_id": "tests/test_checkout.py::test_discount",
  "verdict": "real_bug",
  "confidence": 0.91,
  "summary": "The UI showed the discount but the authoritative API returned the old total.",
  "claim_results": [
    {
      "claim_id": "checkout.discount.persisted",
      "status": "failed",
      "reason": "UI and authoritative API disagree.",
      "evidence": ["oracle.json#/0", "network.jsonl"]
    }
  ],
  "blocked_on": []
}
```

Every pack claim appears exactly once. Claim statuses are `passed`, `failed`, `blocked`, or `not_evaluated`. A passed or failed result requires at least one relative reference to a manifested file inside the pack. JSON and JSONL fragments are RFC 6901 pointers and must resolve. Copy all four digest fields from the template unchanged: they bind the plan, test source, assurance policy, and exact pack manifest.

Validate the completed document:

```bash
testence verdict validate runs/<run>/<test>/pack/verdict.json \
  --plan specs/<feature>.md --json
```
