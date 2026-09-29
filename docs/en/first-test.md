# Your first test

Ten minutes, your own app, no plan file. A PlanSpec is for tracking claims across a
team ([testing a feature](testing-a-feature.md)); a test does not need one to run, fail
with evidence, or prove something.

## 1. Point Testence at the app

```bash
pip install testence
python -m playwright install chromium   # or use Chrome/Edge: TESTENCE_BROWSER_CHANNEL=chrome|msedge
```

Create `testence.json` next to your tests (`auth` is `none` for a public app; see
[authentication](auth.md) for a login):

```json
{"base_url": "http://localhost:3000", "auth": "none"}
```

Then `testence doctor --target` reaches `base_url`, checks the credentials and tries the
login once, so a wrong URL or password is one line, not a timeout.

## 2. Write one test

`ex` is the browser, already logged in. Address elements by role and accessible name;
say in `intent` what the step is for, it is what the report shows.

```python
from testence.engine import Target


def test_home_page_greets(ex):
    ex.goto("/", intent="open the home page")
    ex.expect_visible(Target("role", "heading", name="Welcome"), intent="see the greeting")
    ex.click(Target("role", "button", name="Go"), intent="press Go")
```

## 3. Run it and read what happened

```bash
testence run --project . -- test_smoke.py -q
testence inspect runs/<the run id it printed>
```

Every run writes `runs/<id>/`. A failing test leaves an evidence pack (what the page
looked like, the API traffic, the console, a proposed fix for a stale selector).
`testence report runs/<id>` renders it as one HTML file.

A passing run says `assurance: 1 unverified`. That is not a warning: the test ran and
passed, and nothing states which claim it proves. Add one assertion that the API agrees
with the screen and it becomes `verified`; see the glossary for the four states.

## 4. Prove the save, not just the screen

A UI can say "saved" over a write that never happened. Ask the run what the app sent:

```bash
testence oracle suggest runs/<run id>
```

It lists, for each mutation the test made, the API read that proves it and a
`save_and_verify_state` call to complete ([testing a feature](testing-a-feature.md)).
Ids and field names need `"capture_policy": {"network_bodies": true}` for an app with
synthetic data.

## Where next

- Several users, permissions: `testence_actor` ([authentication](auth.md)).
- Error and empty states: `ex.route` ([testing a feature](testing-a-feature.md)).
- Claims and plans when a team needs them: [testing a feature](testing-a-feature.md).
- Words you meet in reports: [glossary](glossary.md).
