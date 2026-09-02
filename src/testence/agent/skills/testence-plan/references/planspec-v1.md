# PlanSpec v1 reference

The current contract is `testence/planspec/1`. A Markdown plan contains exactly one fenced block whose info string is `testence-planspec`. Surrounding prose may record assumptions, preconditions, seed/cleanup, approval boundaries, and exclusions.

```testence-planspec
{
  "schema": "testence/planspec/1",
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
- `claims` and `scenarios` are non-empty and their IDs are unique.
- Oracle values are `ui`, `network`, `api`, `a11y`, `visual`, or `custom`.
- Every scenario references declared claims.
- Every claim whose `required` value is omitted or `true` is covered by at least one scenario.
- Unknown JSON fields are rejected. Put unstable context in the surrounding Markdown.

Validate before authoring:

```bash
testence plan validate specs/<feature>.md --json
```

The command must return exit code zero and `"valid": true`.
