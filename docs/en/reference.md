# Reference on one page

Everything a test author reaches for, in one place, with links to the page that
explains it. A test checks that every `ex` step and every command is listed here.

## Target

`Target(kind, value, name=None, nth=None, exact=None, within=None)` from
`testence.engine`. `kind` is `role`, `label`, `text`, `testid`, `placeholder` or `css`
(an `xpath=` value is a CSS target). Identity matches (`label`, `placeholder`, a role's
`name`) are exact; `text` matches a substring unless `exact=True`. `within` scopes to
another Target; `nth` picks one of legitimate repeats. Two matches fail a step and are
named in its message. [Engine capabilities](engine-capabilities.md)

## Steps of `ex`

Every step takes an `intent` (what the user does or sees) and records it.

| Group | Steps |
|---|---|
| Navigation | `ex.goto(url)`, `ex.navigate(url, hard=False)`, `ex.open(route)`, `ex.reload()`, `ex.url()` |
| Actions | `ex.click(target, fast=False, modifiers=None)`, `ex.double_click`, `ex.right_click`, `ex.fill(target, value, fast=False)`, `ex.type(target, text)`, `ex.select(target, value, label=)`, `ex.press(key, target=None)`, `ex.check`, `ex.uncheck`, `ex.hover`, `ex.focus`, `ex.scroll_into_view`, `ex.drag(source, destination, html5=False, handle=None)`, `ex.drag_by(target, dx, dy=0, steps=8)`, `ex.upload(target, paths)`, `ex.download(target, path)` |
| Checks | `ex.expect_text(target, text, exact=True)`, `ex.expect_visible`, `ex.expect_hidden`, `ex.expect_value`, `ex.expect_count`, `ex.expect_enabled`, `ex.expect_disabled`, `ex.expect_checked(checked=True)`, `ex.expect_attribute`, `ex.expect_url(contains=, equals=)`, `ex.expect_settled`, `ex.expect_screenshot`, `with ex.soft(intent):` |
| Readers | `ex.text`, `ex.texts(minimum=1)`, `ex.count`, `ex.is_visible`, `ex.attribute`, `ex.input_value`, `ex.box(settled=False)`, `ex.boxes`, `ex.storage_item`, `ex.viewport()`, `ex.read_js(intent, function, arg=None, target=None)` |
| Network | `with ex.expect_request(path, method=) as sent:`, `with ex.expect_outcome(outcomes):`, `ex.route(pattern, status=, json=)`, `ex.rewrite_response`, `ex.ws_gate(pattern)`, `ex.settle()` |
| Pages and windows | `ex.popup(target)`, `ex.switch_page(index, url_contains=)`, `ex.new_page(url)`, `ex.close_page()`, `with ex.frame(target):`, `ex.dialog(target, accept=True)`, `ex.set_viewport(width, height)` |
| State | `ex.set_storage({...}, session=False)`, `ex.reset_storage(keys)`, `ex.clock` (`install`, `fast_forward`, `run_for`, `pause_at`, `resume`, `set_fixed_time`) |
| Oracles | `ex.verify(name, expected, actual)`, `ex.verify_state(name, read, expected)`; `save_and_verify_state(...)` from `testence.oracle` |
| Evidence | `ex.attach(name, data)`, `ex.note(text)` |
| Raw access | `with ex.native(intent) as page:` (keeps the page from being handed on) |
| Plumbing | `with ex.step(intent, target):` for a kit or an adapter, `ex.finish()` (the plugin calls it) |

## Kits

`from testence.kits import koobiq, react_aria, react_select, xyflow, codemirror`.
[Component kits](kits.md)

## Fixtures

| Fixture | What it is |
|---|---|
| `ex` | the steps above, on a browser signed in with the project's `auth` |
| `testence_engine` | the engine behind `ex` |
| `testence_api` | `ApiClient` with the session of `ex`: `get`, `get_fresh`, `post`, `patch`, `delete`, `assert_absent` |
| `testence_actor(name)` | a second user from `users`: `.api`, `.ex` |
| `testence_settings` | the resolved `testence.json` and profile |
| `testence_auth` | the login itself |
| `testence_writer` | the run's evidence writer |
| `testence_namespace`, `testence_seed_marker` | a per-worker name space for seeded data |
| `testence_control` | the negative control of this run, or `None` |
| `testence_fingerprints` | the element fingerprint store |

## Marker

`@pytest.mark.testence(...)`: `plan`, `claims`, `case_id` (a PlanSpec case);
`allure_id`, `title`, `description`, `severity`, `labels`, `links`, `tms` (a report;
`tms={"cases": [...]}` for manual cases); `anonymous=True` (no login), `fresh_page=True`
(not under `page_reuse: module`), `timeout_s` (the test's deadline).
[Reporting](reporting.md)

## pytest options

| Option | What it does |
|---|---|
| `--testence-profile NAME`, `--testence-base-url URL`, `--testence-auth`, `--testence-api-prefix` | the target |
| `--testence-headless`, `--testence-browser-channel`, `--testence-browser-reuse`, `--testence-cdp URL` | the browser |
| `--testence-test-timeout S` | a deadline per test ([configuration](configuration.md#a-deadline-per-test)) |
| `--testence-reruns N` | repeat a failed test, recorded as attempts |
| `--testence-schedule longest-first` | slowest modules first under xdist |
| `--testence-control NAME` | a negative control |
| `--testence-runs-root DIR` | where runs are written |
| `--testence-allure-results DIR`, `--testence-empty-testplan`, `--testence-testplan-unresolved` | Allure and TestOps |
| `--testence-full-trace` | keep every traceback frame |

## `testence.json`

Fields: `base_url`, `project_id`, `api_prefix`, `auth`, `login_path`, `api_login_path`,
`cdp_url`, `execution_mode`, `browser_channel`, `debug_port`, `headed`, `timeout_ms`,
`verify_tls`, `ca_bundle`, `runs_root`, `user_var`, `password_var`, `profiles`. Objects
and keys read by features: `capture_policy`, `evidence`, `export`, `readiness`,
`controls`, `users`, `emulation`, `viewport`, `page_reuse`, `browser_reuse`,
`test_timeout_s`, `target_info`, `cases`, `test_id_attribute`, `session_cookie`,
`session_probe_path`, `storage_state`, `api_allowed_origins`, `api_auth_from_storage`.
[Configuration](configuration.md)

## Commands

| Command | What it does |
|---|---|
| `testence doctor [--target]` | check Python, the browser, the target and the login |
| `testence init` | a conflict-safe onboarding scaffold |
| `testence status` | the active package, project and settings |
| `testence run [-- PYTEST_ARGS]` | run tests under one run id |
| `testence prove` | the green run plus one per control, evaluated in strict mode |
| `testence debug NODE` | one test in a guarded process, with failure ARIA |
| `testence explore PATH` | the page's ARIA, unique Targets and kit lines |
| `testence watch -- CMD` | rerun a command on save |
| `testence inspect RUN` | what a run did, its packs and the target's build |
| `testence report RUN` | a self-contained HTML report |
| `testence timing RUN [OTHER]` | setup, call, teardown, API calls and waits; a comparison |
| `testence cases [--run RUN]` | manual cases against tests and outcomes |
| `testence export RUN --to allure\|ctrf\|junit` | an integration format |
| `testence metrics RUN...` | aggregate metrics |
| `testence inventory RUN` | screen references from a run |
| `testence oracle suggest RUN` | the API checks a run implies |
| `testence plan validate\|prepare\|skeleton` | PlanSpec checks and test stubs from a case file |
| `testence seed scaffold --openapi DOC` | cleanup fixtures from OpenAPI |
| `testence verdict validate\|submit`, `testence repair validate` | agent verdicts and repairs |
| `testence ci evaluate\|summary`, `testence delivery run` | CI receipts and uploads |
| `testence quality apply\|rollback\|summary` | multi-project quality packs |
| `testence agent install\|verify` | the portable agent skills |
| `testence mcp` | the MCP server |
| `testence auth export` | the login as a storage state |
| `testence capabilities` | what the engine declares |
| `testence bench -- CMD`, `testence demo run` | repeated timing, the proof demo |
| `testence corpus validate`, `testence release validate` | Testence maintainers only |
