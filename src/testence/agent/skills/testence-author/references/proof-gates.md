# Authoring and proof gates

## Contract binding

Start from a validated `testence/planspec/1` and bind only declared claim IDs:

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
    ex.verify("persisted widget", {"name": widget.name}, {"name": actual["name"]})
```

Collection must reject an external plan path or unknown claim. Use repository-relative plan paths so bindings survive across machines.

## Claim-to-proof review

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
5. Inspect `run.jsonl` and the bounded pack for plan and claim bindings.
6. Restore the target and clean seed data.
7. Run the same code green again.

Do not call a test accepted or launch-ready when steps 3–7 were skipped. Report the skipped gate and why.
