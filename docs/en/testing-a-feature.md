# Testing a UI feature with Testence

This guide describes a product-neutral workflow for turning a behaviour claim into a
fast, maintainable UI test.

## 1. State the claim

Write one sentence with a subject, action and observable result:

> When an authenticated user submits a valid widget, the new widget appears in the
> collection and the API returns the same values.

Split independent claims into independent tests. A create/edit/delete journey is
useful as a smoke flow, but it is a poor regression unit: later assertions depend on
all earlier actions, parallelism is impossible and a single failure hides the rest.

For each claim record:

| field | question |
|---|---|
| precondition | what state must exist before the interaction? |
| UI address | which role, label or stable test id identifies the control? |
| oracle | what independent observation proves the result? |
| mutation | does the test create or change shared data? |
| cleanup | how is created data identified and removed? |

## 2. Discover the surface

Use the browser and accessibility tree to verify routes, roles and accessible names
before writing selectors. Prefer, in order:

1. role plus accessible name;
2. label or placeholder;
3. a stable configured test-id attribute;
4. CSS only when the application exposes no semantic address.

Do not infer an API contract from the rendered page. Read the documented API or a
public schema, and keep application-specific selectors in a project `ActionMap`
rather than in the framework package.

## 3. Seed through the API

Create preconditions through a project `SeedAdapter` or the shared-session
`ApiClient`. Drive a precondition through the UI only when that UI flow is the claim
under test.

Every created record should carry a run- and worker-scoped marker. A safe fixture:

- removes only records carrying its own marker;
- verifies cleanup instead of swallowing errors;
- respects dependency order;
- reports leftovers as test infrastructure failures.

Read-only tests are preferred on shared environments. Mutating tests should use an
isolated tenant or ephemeral environment when possible.

## 4. Drive intent, not implementation

Keep the test small and readable:

```python
def test_created_widget_is_visible(ex, testence_api, widget_seed):
    widget = widget_seed.valid()

    ex.goto("/widgets", intent="open the widget collection")
    ex.click(CREATE_BUTTON, intent="start creating a widget")
    ex.fill(NAME_FIELD, widget.name, intent="name the widget")
    ex.click(SAVE_BUTTON, intent="save the widget")

    ex.expect_text(ROW_NAME, widget.name, intent="show the created widget")
    actual = testence_api.get(f"/api/widgets/{widget.id}").raise_for_status().json
    ex.verify("created widget", {"name": widget.name}, {"name": actual["name"]})
```

Avoid arbitrary sleeps. Wait for the state that matters: a request, response,
visible value, row count or application-specific readiness signal.

## 5. Prove the test can fail correctly

A green test is not evidence that the assertion is useful. Before accepting a case:

1. run it against the healthy target;
2. inject or temporarily simulate the behaviour it claims to detect;
3. verify the expected assertion fails for the expected reason;
4. restore the target and verify the test is green again.

The synthetic corpora in `corpus/` and `bench/corpus/` apply this discipline to the
framework itself.

## 6. Author narrowly, validate broadly

During authoring, run one test with a long-lived attached browser:

```bash
python -m testence.dev_browser --profile staging
pytest tests_e2e/test_widgets.py -k created_widget --testence-profile staging-attached
```

Before merging, run the full suite repeatedly on unchanged code. Compare:

- outcome stability;
- total and per-operation wait time;
- false-red controls;
- evidence-pack completeness;
- cleanup success;
- serial versus parallel results.

Enable `pytest-xdist` only after fixtures have per-worker namespaces and all
machine-wide resources have worker-specific offsets.

## Common failure modes

- A presence assertion passes on skeleton or placeholder rows.
- A stale panel satisfies a generic “dialog is open” condition.
- A request succeeds server-side but the page aborts its response.
- The UI and API query different sort, filter or pagination windows.
- Loose text matching selects a different element or accepts a transient value.
- Retrying an interaction hides a swallowed-first-click defect.
- Silent locator healing redirects the test to the wrong control.

Testence records evidence for these cases, but the test still has to state a precise
claim and a meaningful oracle.
