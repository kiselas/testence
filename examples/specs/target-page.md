# Target page proof plan

This PlanSpec is deliberately small. It demonstrates the repository contract that a
coding agent should create before authoring deterministic tests.

```testence-planspec
{
  "schema": "testence/planspec/2",
  "project_id": "testence",
  "id": "target-page.basic-behaviour",
  "title": "Verify the local target page",
  "source": "examples/test_target_page.py",
  "claims": [
    {
      "id": "target.counter.incremented",
      "statement": "Clicking increment increases the visible counter to one.",
      "oracles": ["ui"],
      "required": true
    },
    {
      "id": "target.row.visible",
      "statement": "Adding a name renders the corresponding row.",
      "oracles": ["ui"],
      "required": true
    },
    {
      "id": "target.async.loaded",
      "statement": "The asynchronous load eventually renders its result.",
      "oracles": ["ui", "network"],
      "required": true
    }
  ],
  "assertions": [
    {
      "id": "assert.counter.incremented",
      "claim_id": "target.counter.incremented",
      "oracle": "ui",
      "required": true
    },
    {
      "id": "assert.row.visible",
      "claim_id": "target.row.visible",
      "oracle": "ui",
      "required": true
    },
    {
      "id": "assert.async.response",
      "claim_id": "target.async.loaded",
      "oracle": "network",
      "required": true
    }
  ],
  "scenarios": [
    {
      "id": "increment-counter",
      "title": "Increment the counter",
      "claims": ["target.counter.incremented"]
    },
    {
      "id": "add-row-and-load",
      "title": "Add a row and load asynchronous data",
      "claims": ["target.row.visible", "target.async.loaded"]
    }
  ]
}
```
