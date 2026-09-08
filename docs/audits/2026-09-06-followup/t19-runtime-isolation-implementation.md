# T19 runtime isolation implementation receipt

Date: 2026-09-06. Status: locally implemented and verified on Windows; Linux gate open.

## Delivered behavior

The default pytest engine, auth and API fixtures are now function-scoped. Isolated mode
creates and closes runner-owned browser resources for every test, including failure.
Explicit warm mode retains the browser process but calls `reset_session` to replace the
owned context before each test and before authentication. Attached CDP sessions are
marked foreign: reset and cleanup never close or replace their context or browser.
Browser manifests expose mode plus browser/context ownership.

`TestNamespace` provides a deterministic collision-resistant marker bound to project,
run, worker, case, role and attempt. `SeedLifecycle` requires a named owner, seeds once,
and makes exact-marker cleanup visible. `debug_port` and `execution_mode` are validated
settings. ADR-0021 and EN/RU configuration docs define the ownership boundary and the
compatibility path for old custom engines.

## Consumer receipt

[`outputs/.../t19-isolation-consumer`](../../../outputs/audit-2026-09-06-followup/t19-isolation-consumer/README.md)
ran the same cookie-isolation scope in fresh and warm modes. Both runs passed two of two
tests with matching proof inventory and no integrity error; the owned CDP port was
closed after each command.

## Verification

| Check | Observed |
|---|---|
| Isolation/config/auth/warm/lifecycle subset | `79 passed in 57.29s` |
| Focused isolation/browser tests | `23 passed in 5.16s` |
| Ruff | source and focused tests pass after formatting |
| mypy | success, 50 source files |
| Real Chromium consumer | isolated and warm both `2 passed`; port closed |

## Boundary

The Windows local acceptance is complete. T19 still needs the same matrix on Linux and
an application-level role-switch/seed cleanup integration supplied by a real target.
T24 owns statistically useful warm/fresh and process-resource measurement. This
receipt becomes immutable only after review and commit.
