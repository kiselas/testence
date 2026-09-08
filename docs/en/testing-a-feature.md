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

Capture this in a PlanSpec before opening the browser. The file contains human context
plus exactly one machine-readable `testence-planspec` block; see
`examples/specs/target-page.md` for a minimal working example. Validate the contract
immediately:

```bash
testence plan validate specs/widgets-create.md --json
```

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
@pytest.mark.testence(
    plan="specs/widgets-create.md",
    claims=["widgets.create.persisted"],
)
def test_created_widget_is_visible(ex, testence_api, widget_seed):
    widget = widget_seed.valid()

    ex.goto("/widgets", intent="open the widget collection")
    ex.click(CREATE_BUTTON, intent="start creating a widget")
    ex.fill(NAME_FIELD, widget.name, intent="name the widget")
    ex.click(SAVE_BUTTON, intent="save the widget")

    ex.expect_text(ROW_NAME, widget.name, intent="show the created widget")
    actual = testence_api.get(f"/api/widgets/{widget.id}").raise_for_status().json
    ex.verify(
        "created widget",
        {"name": widget.name},
        {"name": actual["name"]},
        assertion_id="assert.widget.persisted",
        claim_id="widgets.create.persisted",
    )
```

Avoid arbitrary sleeps. Wait for the state that matters: a request, response,
visible value, row count or application-specific readiness signal.

For React/SPAs, do not add a global `networkidle` wait after every action. Polling and
streams may make it consume the full timeout even when the outcome is ready. Declare the
mutation signal when using the oracle helper; Testence scopes the completed response to
the save click and then reads the independent oracle:

```python
save_and_verify(
    ex,
    SAVE_BUTTON,
    name="widget",
    ui_view=read_widget_from_ui,
    api_view=read_widget_from_api,
    expect_request="/api/widgets",
)
```

For a persisted business state, bind the mutation more narrowly and poll an
authoritative cache-bypassing read. The mutation is executed once; only GET reads are
repeated. `minimum_revision` rejects a stale value that happens to agree with the UI,
and `stability_ms` catches a commit that is rolled back shortly afterwards:

```python
from testence.oracle import ExpectedState, RequestExpectation, save_and_verify_state

save_and_verify_state(
    ex,
    SAVE_BUTTON,
    name="widget",
    request=RequestExpectation(
        "/api/widgets",
        "POST",
        origin=settings.base_url,
        correlation_id=widget.run_marker,
    ),
    read=lambda: testence_api.get_fresh(f"/api/widgets/{widget.id}"),
    expected=ExpectedState(
        "the created widget remains persisted",
        lambda body: body["name"] == widget.name and body["state"] == "saved",
        entity_id=widget.id,
        correlation_id=widget.run_marker,
        minimum_revision=widget.expected_revision,
        stability_ms=500,
    ),
    assertion_id="assert.widget.persisted",
    claim_id="widgets.create.persisted",
)
```

The request expectation can additionally name a GraphQL operation or a custom record
predicate. Empty/non-JSON/HTML and 401/403/404/500 oracle responses are
`inconclusive`; a valid stale, wrong-entity, wrong-role or rolled-back state is a failed
assertion. Negative claims use a negative predicate plus `stability_ms` as their
observation window.

`ex.fill(...)` keeps Playwright's visibility/editability checks and is the default.
`ex.fill(..., fast=True)` skips those checks but preserves the normal `input` event; use
it only after a readiness assertion has already proved the control actionable. The wait
ledger in `test.waits` shows whether time is being spent in navigation, actionability,
response synchronization, assertions or evidence capture.

## 5. Prove the test can fail correctly

A green test is not evidence that the assertion is useful. Before accepting a case:

1. run it against the healthy target;
2. inject or temporarily simulate the behaviour it claims to detect;
3. verify the expected assertion fails for the expected reason;
4. restore the target and verify the test is green again.

The marker is validated during pytest collection. At runtime its plan and claims reach
every test event, the failure pack and the HTML report. On the expected failure, complete
the pack's `verdict.template.json`, save it as `verdict.json`, and validate its binding to
the plan and evidence:

```bash
testence verdict validate runs/<run>/<test>/pack/verdict.json \
  --plan specs/widgets-create.md --json
```

The synthetic corpora in `corpus/` and `bench/corpus/` apply this discipline to the
framework itself.

## 6. Author narrowly, validate broadly

During authoring, run one test with a long-lived attached browser:

```bash
python -m testence.dev_browser --profile staging
pytest tests_e2e/test_widgets.py -k created_widget --testence-profile staging-attached
```

Attached runs borrow the launcher's logged-in context and do not close it when they
finish. On the maintained real-React profile this reduced fresh-process p50 from
3.21 s to 2.02 s; the one-time browser launch breaks even on the second repeated run.

For the tight authoring loop, keep Python and pytest warm as well:

```bash
testence watch --warm -w tests_e2e -w src -- \
  python -m pytest tests_e2e/test_widgets.py -k created_widget \
  --testence-profile staging-attached -q
```

Warm mode accepts only direct `pytest` or `python -m pytest` commands. It creates a
new pytest session, run id, engine attachment, writer and fixtures on every iteration,
and evicts imported project modules under the selected `-w` roots before rerunning.
Testence itself stays loaded so runner startup is not paid repeatedly.

The Playwright/CDP engine connection also survives between warm sessions. A settings
change replaces it; stopping watch closes it. On the maintained React profile this
reduced steady bootstrap p50 to 447 ms and whole-run p50 to 1.13 s.

Use normal subprocess mode for release and CI validation, and for suites whose
third-party plugins keep undocumented process-global state.

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
