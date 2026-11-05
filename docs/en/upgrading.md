# Upgrading from 0.1.0a1

What changes for a suite written against the published `0.1.0a1`, and how to keep the
old behaviour where that is possible. The full list is in the [changelog](CHANGELOG.md).

## Behaviour you may notice

| Change | What to do |
|---|---|
| `ex` logs in with the configured `auth` scheme; before, only a test that also asked for `testence_api` or `testence_auth` did | a test of the login page or of public pages: `@pytest.mark.testence(anonymous=True)` |
| Bearer and Basic headers go only to `base_url` and `api_allowed_origins`; header auth without either is refused | list every origin that must receive them in `api_allowed_origins` |
| A pytest session writes `runs/` only when it is a Testence session (CLI, a `--testence-*` option, or a test using a Testence fixture or marker) | nothing; run through `testence run` or pass a `--testence-*` option to record a whole suite |
| The browser's debug port is chosen by the operating system | set `debug_port` if something must attach to a known port |
| A failed form login is `LoginFailed` naming the path and the missing success signal, not a Playwright timeout | catch `testence.auth.LoginFailed` if you caught the timeout |
| A missing visual baseline is `unavailable` (inconclusive), not an error from the file system | create the baseline as before |
| A settings profile merges tables with the base file instead of replacing them | an empty table (`{}`) in a profile no longer clears the base's table; restate the keys you want changed |
| Oracle views compare booleans strictly (`True` is not `1`) | compare the value the API returns |

## Reports and exports

| Change | Previous behaviour |
|---|---|
| Allure `fullName`, `testCaseId`, `historyId` follow allure-pytest for tests without a PlanSpec case | `export.allure.naming: nodeid` |
| Parameters show redacted values | `export.allure.parameters: digest` |
| Only user markers without arguments become tags | — (fix) |
| A non-assertion error in the test body is `broken` | — (fix) |
| An Allure test plan entry that matches nothing is a warning and the rest runs | `--testence-testplan-unresolved=fail` |
| CTRF steps, attachments, labels and parameters use CTRF's own fields; `extra.steps` is replaced by `steps` | — |
| `@allure.*` decorators and `allure.dynamic.*` work without allure-pytest | — (fix) |

## Python API

- `testence.adapters.AuthAdapter` is the `testence.auth.AuthAdapter` protocol
  (`authenticate(engine) -> AuthContext`, ADR-0010). The earlier `login(engine) -> None`
  shape had no caller in Testence.
- Engine protocol additions (`hover`, `drag`, `set_checked` and others) are optional
  for third-party engines: the DSL raises `UnsupportedCapability` naming a missing one.
  `api_auth_from_storage` needs `storage_item`.
- New: `ExpectedState.absent(...)`, `api_auth_from_storage`, `--testence-reruns`,
  `testence doctor --target`.

The agent skills installed into a project are copies: after upgrading, `testence agent
verify --project . --client <client>` reports `drift` until `testence agent install`
brings them up to the packaged pack.

## After 0.1.0a2

| Change | What to do |
|---|---|
| `--attachments full` (the default) and the live Allure stream no longer ship the trace, the video or binary attachments: they are stored unredacted | `testence export --attachments raw` where that data may leave the machine |
| `ExpectedState.absent(..., entity_id=...)` passes on an empty or 404 read; the binding is checked only on a row that is still there | nothing |
| `testence init` declares a `drop-save` control and the onboarding test applies it; `testence demo run` adds a fourth, negative run | `init` never overwrites existing files: to try it in an existing project, run `testence demo run --project testence-demo` in a new folder |
| MCP tools reject arguments their `inputSchema` does not declare, and wrong types; `testence_doctor` with a failed check returns `isError: true` | send only the documented arguments ([MCP](mcp.md)); read the doctor report from the error result |
| `LoginFailed` from a form login has more lines: what the page said and the login form's ARIA tree | match on its first line, or read `page_errors` and `form_aria` |
| `TRIAGE.md` opens with a section for a person; the judge's instructions follow `## For an agent judging this failure` | a tool that fed the whole file to a model can keep doing so; one that read only the start should read from that heading |
| `testence doctor --json` prints nothing on stderr; progress lines are for a terminal | drop `--json` to see them |
| `ApiClient` keeps connections alive; a call that gets no answer in time raises `TimeoutError` (urllib raised `URLError` for a connect timeout); other connection failures are still `URLError` | catch `TimeoutError` (or `OSError`, which covers both) where a connect timeout was caught as `URLError` |
| A POST or PATCH whose connection breaks while the request is in flight fails instead of being repeated | retry in the test only where the endpoint is safe to repeat |
| `session_role_field` is read only when named or when `session_expected_role` is set; cache records are version 2 | nothing; the first run after upgrading logs in once ([configuration](configuration.md#optional-session-cache)) |
| A test that asks for `testence_api` without `ex` or `testence_engine` starts no browser when the scheme logs in over HTTP | ask for `ex` or `testence_engine` where the test needs a page |
| The ledger is flushed per event and synced to disk per test | `evidence.durability: "step"` for the previous fsync per event |
| Values of environment variables with secret-looking names (`*TOKEN*`, `*SECRET*`, `*PASSWORD*` and others) are masked in all evidence, and `doctor` lists their names | if a value must stay visible, set `evidence.redact.auto_env: false` |
| Fingerprint entries of tests whose parameter id contained a masked secret are keyed with a digest | nothing; the next green run records them again |
| HTML, XML and CSV attachments have secret fields, elements and columns replaced by `<redacted>` (`&lt;redacted&gt;` in markup) | nothing; ship the file with `--attachments raw` only where the data may leave the machine |
