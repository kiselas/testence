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
