# Short authoring iterations

Start in the repository containing the application's `testence.json` and tests.
This framework repository contains synthetic examples and benchmark corpora. It does
not bundle private application pilots. Older consumer projects may still carry the
Exhibit or `stf_autotests` names; their settings, auth and seed adapters belong to that
consumer project. Use `testence` for the current package/import/CLI.

## Map the page once

```bash
testence explore /host-templates --project . --profile dev2 --json
```

Use a profile that actually exists in `testence.json`. The command uses configured
authentication and returns a redacted ARIA tree, candidate Targets with match counts,
and visible `data-key` rows. It performs no clicks and produces discovery data, not
verified test assurance. It closes its engine on exit. For menus and dialogs that must
remain open across observations, use the persistent MCP `testence_snapshot`,
`testence_click` and `testence_fill` session. A uniqueness count applies to the observed
page; it is not a guarantee about a later state.

## Scope controls, then run exactly one case

```python
from testence.engine import Target

IMPORT = Target("role", "dialog", name="Import")
CLOSE = Target("role", "button", name="Close", within=IMPORT)
NAME = Target("role", "textbox", name="Name", within=IMPORT)

def test_import_name(ex):
    # Navigate/open/select using the application's actions first.
    ex.expect_value(NAME, "suggested-name")  # wait for the app's known suggestion
    suggested = ex.input_value(NAME)        # one strict read, may return an empty string
    ex.fill(NAME, "chosen-name")
    ex.expect_value(NAME, "chosen-name")
    ex.click(CLOSE)
```

`within` is a Target and may itself be scoped. It preserves strict matching. Use a
stable row ID/container to distinguish a table entry from a toast. `nth=0` remains
an explicit choice; the framework never selects the first duplicate automatically.
Failure diagnostics list the first three match texts with their indices.

```bash
testence run --project . -- tests/test_import.py::test_import_name -q
python -m pytest tests/test_import.py::test_import_name --collect-only -q
```

Collect first when a debug file imports helpers. `from test_x import *` imports test
functions too, so pytest may collect the whole suite again. Keep helpers in a module
whose name does not start with `test_`. Read the failed case's `pack/aria.txt` and
`TRIAGE.md` before rerunning; do not run the whole suite to debug one target.

For repeated edits, the existing opt-in warm loop retains the engine while renewing
pytest sessions, fixtures, run IDs and evidence:

```bash
testence watch --warm -w tests -- python -m pytest tests/test_import.py::test_import_name -q
```

This does not preserve arbitrary fixture state or bypass authentication. For an
explicit attached browser profile see [fast authoring](../../README.md#fast-agent-authoring).
Finish acceptance with a fresh process and clean seed. Parallel runs require a
worker-specific data namespace and independently verified cleanup; they are not
automatically safe for every application.

## Windows and application-specific work

Prefer PowerShell or Python entry points. In Git Bash export `MSYS_NO_PATHCONV=1`
before passing routes beginning with `/`. Set `PYTHONUTF8=1` when printing Unicode,
and `TESTENCE_BROWSER_CHANNEL=msedge` on hosts where Edge is the working browser.
`explore` JSON uses ASCII escapes and decodes back to the original Unicode.

Open a row menu before calling `ex.download` on its download item. Wait for a specific
row after debounced search, and for the application's known field suggestion before
overwriting it. A generic "stable field" delay cannot prove that another update is
not scheduled. The framework does not retry fill or click to hide a race.

Response adapters are defect injection: `ex.route` is static; native fulfill is
marked mocked and cannot prove persistence. `route.fetch()` can modify a response,
but this cycle does not establish file-upload forwarding correctness. A multipart
adapter must first prove exact bytes reached a synthetic receiver. Do not replace a
broken transfer with an unverified page-fetch shim or present adapted FE/BE behaviour
as deployed-product acceptance. See [Playwright Route](https://playwright.dev/python/docs/api/class-route).

Seed/create/delete semantics and downloaded-file server validation require the
application's API contract. Keep these adapters in the consumer project and verify
cleanup with its authoritative absence predicate; a successful DELETE status alone
does not establish absence.
