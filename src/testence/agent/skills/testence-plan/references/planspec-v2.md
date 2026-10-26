# PlanSpec v2 reference

The current contract is `testence/planspec/2`. A Markdown plan contains exactly one fenced block whose info string is `testence-planspec`. Surrounding prose may record assumptions, preconditions, seed/cleanup, approval boundaries, and exclusions. `project_id` is a repository-owned namespace; each scenario `id` is the stable logical `case_id` used by tests and reports.

Each scenario may declare a unique `capabilities` array using names from
`testence capabilities --json`. Collection fails before execution when the selected
engine cannot provide the declared operations; never turn that mismatch into a skip.

```testence-planspec
{
  "schema": "testence/planspec/2",
  "project_id": "checkout",
  "id": "checkout.discount",
  "title": "Apply an eligible discount",
  "source": "product requirement or issue URL",
  "claims": [
    {
      "id": "checkout.discount.persisted",
      "statement": "The discounted total is stored and returned for the current cart.",
      "oracles": ["ui", "api"],
      "required": true
    }
  ],
  "assertions": [
    {
      "id": "assert.discount.persisted",
      "claim_id": "checkout.discount.persisted",
      "oracle": "api",
      "required": true,
      "expected": "The cart API returns the discounted total."
    }
  ],
  "scenarios": [
    {
      "id": "eligible-code",
      "title": "Apply an eligible code",
      "claims": ["checkout.discount.persisted"],
      "risk": "false green from optimistic UI"
    }
  ]
}
```

Constraints:

- IDs use lowercase letters, digits, dots, underscores, or hyphens; start and end with a letter or digit.
- `claims`, `assertions`, and `scenarios` are non-empty and their IDs are unique.
- Oracle values are `ui`, `network`, `api`, `a11y`, `visual`, or `custom`.
- Every scenario references declared claims.
- Every claim whose `required` value is omitted or `true` is covered by at least one scenario.
- Every required claim has at least one required assertion bound by `claim_id`.
- An assertion's `expected` states the concrete value, or the rule that computes it
  from the seed, that the test compares against: "the cart total is 90.00 after a 10%
  code on a 100.00 cart", not "the total is correct". Authors take expected values
  from here, never from the running product, so a vague `expected` produces a test
  that cannot fail.
- Unknown top-level fields are preserved for additive compatibility; assertion, claim,
  and scenario objects remain strict. Put unstable context in the surrounding Markdown.

When the source does not fix an outcome, leave the scenario out and record an open
question in the surrounding Markdown instead of guessing:

```markdown
## Open questions

- `checkout.discount.expired`: the issue says an expired code is rejected "after a
  while". Is the cutoff the code's end date, the end of that day in the shop's time
  zone, or a grace period? No scenario until the owner answers.
```

Validate before authoring:

```bash
testence plan validate specs/<feature>.md --json
```

The command must return exit code zero and `"valid": true`.
