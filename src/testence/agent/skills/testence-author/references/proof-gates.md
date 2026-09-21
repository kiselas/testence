# Authoring and proof gates

## Contract binding

Start from a validated `testence/planspec/2` and bind only declared claim IDs:

```python
import pytest

from testence.engine import Target


SAVE = Target("role", "button", name="Save")


@pytest.mark.testence(
    plan="specs/widgets-create.md",
    claims=["widgets.create.persisted"],
)
def test_created_widget_is_persisted(ex, testence_api, widget_seed):
    widget = widget_seed.valid()
    ex.goto("/widgets", intent="open the widget collection")
    ex.click(SAVE, intent="save the widget")
    actual = testence_api.get(f"/api/widgets/{widget.id}").raise_for_status().json
    ex.verify(
        "persisted widget",
        {"name": widget.name},
        {"name": actual["name"]},
        assertion_id="assert.widget.persisted",
        claim_id="widgets.create.persisted",
    )
```

Collection must reject an external plan path or unknown claim. Use repository-relative plan paths so bindings survive across machines.

For a UI-only claim, bind the observed state to a declared assertion too:

```python
ex.expect_visible(
    Target("css", "#notifications:checked"),
    intent="Notifications are enabled",
    assertion_id="assert.notifications.checked",
    claim_id="notifications.enabled",
)
```

Declare that assertion with `oracle: "ui"` in the PlanSpec. A normal unbound
`expect_visible` still checks execution but does not satisfy the required proof
inventory. Missing visibility produces a failed assertion; an unavailable browser
produces an inconclusive one. Do not relabel browser errors as product violations.

## Claim-to-proof review

Before discovery, run the project's readiness contract:

```bash
testence plan prepare specs/widgets-create.md --project . --profile staging --json
```

Exit 3 is an actionable blocked result: use its scenario blockers to prepare the target
or narrow the authorized scope. Exit 2 means the PlanSpec or readiness configuration is
invalid. Do not open a browser for blocked scenarios.

When a failed check has a project-owned `fix.argv` recipe and the authorized scope permits
that preparation, rerun with `--apply-fixes`. Testence invokes the arguments without a
shell and rechecks the prerequisite. An applied command is not proof by itself; only the
second check result can move a scenario to `ready`.

For every bound claim, record:

| Question | Required answer |
|---|---|
| What action triggers the outcome? | Intent-bearing Testence step |
| What does the user observe? | Precise semantic UI assertion |
| What independently proves truth? | API, database adapter, network contract, accessibility, visual, or custom oracle |
| How is state isolated? | Run/worker-scoped seed and verified cleanup |
| How does the test fail? | Expected assertion and evidence signal on the negative control |

## Proof sequence

1. Validate the PlanSpec.
2. Run the exact test against the healthy target.
3. Activate a declared defect or safe negative control.
4. Run the same code and confirm the expected claim fails for the expected reason.
5. Inspect `run.jsonl` and the bounded pack for plan and claim bindings. Run
   `testence inspect <run-dir> --json`: healthy/restored cases must have verified
   assurance, and intended defect cases violated assurance, with no integrity errors.
   A pytest pass with unverified assurance is incomplete proof.
6. Restore the target and clean seed data.
7. Run the same code green again.

Do not call a test accepted or launch-ready when steps 3–7 were skipped. Report the skipped gate and why.
