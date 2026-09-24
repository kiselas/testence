# Changelog

This project is an alpha candidate. Until a first tagged release, notable changes are grouped
under `Unreleased`; compatibility is not guaranteed.

## Unreleased

### Added

- `testence export --to junit`: JUnit XML with Testence identity and case-id
  properties, `<failure>`/`<error>` split like Allure, step intents and redacted
  evidence files ([ADR-0028](adr/0028-junit-exporter.md)).
- `@pytest.mark.testence(tms={"testrail": "C123", "xray": "PROJ-12", ...})`
  declares test-management case ids; they reach JUnit (`test_id`, `test_key`,
  `testrail_result_step`, `tms.<system>`), Allure labels and CTRF labels.
- `with ex.soft("<intent>"):` runs every check in the block and fails once at the
  end with `SoftAssertionsFailed` listing the failed ones; each is still a failed step
  marked `soft`. Actions and browser errors are not softened.
- Tabs: `ex.switch_page(index)` or `ex.switch_page(url_contains=...)`, which waits
  for a tab the application is opening, and `ex.close_page()`.
- Fake time: `ex.clock.install`, `fast_forward`, `pause_at`, `resume` and
  `set_fixed_time` over Playwright's clock, behind the new `browser.clock`
  capability.
- DSL checks `expect_value`, `expect_count`, `expect_enabled`, `expect_disabled`,
  `expect_checked`, `expect_attribute` and `expect_url(contains= | equals=)`, and
  steps `press(key, target=None)`, `check`, `uncheck`, `hover` and
  `select(target, label=...)`. Each is an intent step with evidence; checks are
  exact. [Testing a feature](testing-a-feature.md) lists the whole vocabulary.
- Skill pack 0.1.7: `testence-author` prefers the DSL, lists its checks and actions,
  groups screen facts in `ex.soft`, drives timers with `ex.clock`, and says when to use
  `ex.native`.
- `with ex.native("<intent>") as page:` hands the Playwright page to code the DSL does
  not express, inside one recorded step with a `native.used` event
  ([ADR-0027](adr/0027-native-escape-hatch.md)).
- Evidence: `evidence.redact` in `testence.json` adds or exempts field names and URL
  parameters, names environment variables whose values are redacted, and opts into email
  and phone redaction. `evidence.mask` paints listed elements black in every screenshot,
  including visual baselines ([ADR-0024](adr/0024-evidence-redaction-policy.md)).
- `testence export --attachments full|minimal|none` limits which pack files an export
  ships.
- Allure TestOps: `--testence-allure-results DIR` streams each result as its test ends,
  byte-identical to the post-run export, so `allurectl watch` fills the launch live and a
  killed job keeps its finished results ([ADR-0026](adr/0026-streaming-allure-export.md)).
- Allure: identities follow allure-pytest (`export.allure.naming: allure-pytest`), so a
  migrated suite keeps its TestOps cases and history; `@allure.*` metadata is read without
  allure installed; `@pytest.mark.testence(allure_id=..., title=..., severity=...,
  labels=..., links=...)` works without a PlanSpec. Cards gain the suite tree, readable
  redacted parameters ([ADR-0025](adr/0025-parameter-display-values.md)), failed/broken
  status, the full trace, PlanSpec scenario titles and claims, `categories.json`, the
  failure screenshot on the failed step and `evidence.screenshots: always`.

### Security

- Evidence redaction matched only exact key names, so `authToken`, `sessionToken`,
  `X-Api-Key`, `csrfToken`, `pwd`, OAuth `code` and `session` URL parameters, JWTs and
  provider tokens in free text, card numbers, and secrets named in data such as an
  oracle diff `{"field": "authToken", ...}` could reach the ledger, the pack and an
  Allure upload in clear text. Names are now matched by their parts and values by their
  shape. Export and report apply the recorded policy again, so evidence written by an
  earlier release leaves redacted.

### Fixed

- A pytest started as a subprocess by a test inside an xdist worker inherited
  `PYTEST_XDIST_WORKER` and wrote a worker shard with no controller ledger, so its run
  never completed. The worker id now comes from xdist itself.
- `expect_hidden` timed out with Playwright's `TimeoutError`, so an element that
  never went away was reported `broken`. It now raises `AssertionError`.
- `expect_text` raised Playwright's `TimeoutError` when the text never appeared, so a
  product disagreement was reported like an environment failure (`broken`). It now
  raises `AssertionError`, as `expect_visible` already did.
- Quality packs: a pack listing paths that differ only by letter case or Unicode
  normalization, such as `quality/A.json` and `quality/a.json`, was accepted. Default
  macOS and Windows file systems store them as one file, so one file landed while the
  lock tracked two, or a Linux-built pack failed with a misleading digest mismatch. Such
  a pack is now refused with the colliding pair named.
- Evidence: a network capture holding more than one request was redacted by text rules
  only, so a credential field inside a request body could reach `network.jsonl` in clear
  text. JSON Lines are now redacted record by record.
- Lifecycle: a browser start that failed halfway left its Playwright driver process
  running, one per failed run. `start()` now releases what it created.
- Quality packs: when the file system refused the operation lock, as SMB and NFS mounts
  can, the command reported "another quality pack operation is in progress". Only real
  contention says that now; other lock failures name the lock file, the system error and
  the network file system as a likely cause.
- `switch_page()` did not re-attach the evidence taps, so a second tab produced an
  empty network and console section.
- `TESTENCE_DEBUG_PORT=0` advertised `127.0.0.1:0` in the triage manifest. The engine
  now resolves a real free port, so the failure browser stays attachable.
- `.env`, `testence.json` and `testence.toml` are read as UTF-8 with an optional
  byte-order mark, so a file saved by a Windows editor no longer loses its first key.
- An unparsable settings file reports the file and the position instead of a traceback,
  and a relative navigation without `base_url` names the missing setting.
- An empty `TESTENCE_BROWSER_CHANNEL` keeps the packaged default instead of launching
  with no channel.
- The default form-login submit target also matches `<button>` without an explicit
  `type`, which submits its form per the HTML specification.
- A `.DS_Store` or AppleDouble `._name` file that Finder leaves in an opened folder no
  longer blocks quality-pack recovery, changes the CI delivery identity of an Allure
  results folder, or enters the installed skill pack from an editable checkout.
  Explorer's `Thumbs.db` and `desktop.ini` are skipped the same way.
- Expected state: a read that the host scheduler delayed past the deadline could
  complete a positive `stability_ms` window, so a window longer than its deadline could
  pass without being sampled. A positive window must now be observed within the
  deadline; a point-in-time check with `stability_ms=0` is unchanged.
- The demo target server that `testence demo run` writes into a project, the test
  fixtures and the benchmark servers no longer resolve `127.0.0.1` back to a host name
  when they bind. On a hosted macOS runner the first such lookup in a process took
  35 s, so each demo scenario started 35 s late and the `bench/competitive` and
  `bench/i3_baseline` targets did not listen within their startup wait. New
  `testence.loopback` provides the server and `python -m testence.loopback PORT`.
- Expected state: two matching reads at the edges of a stability window, with the
  scheduler asleep in between, completed it. A positive window now also needs a matching
  read inside it. A window that is not shorter than its deadline, a negative deadline
  or a non-positive poll interval raise `ValueError`, and `save_and_verify_state` checks
  them before it clicks save instead of after the mutation was sent.

### Changed

- CTRF: steps, attachments, the suite path, labels, parameters and the trace use CTRF's
  own fields; `extra.steps` (a list of indented intent strings) is replaced by `steps`.
  `summary.start`/`stop` are always present, as the schema requires.
- Allure test plans: an entry that matches no collected test is reported (warning,
  `testplan.unresolved` event, export, CI receipt) and the rest of the plan runs;
  `--testence-testplan-unresolved=fail` restores the strict behaviour. An `allure_id` on a
  parametrized test selects every variant, an allure-pytest `fullName` selects every
  variant, overlapping entries select a test once, unknown plan fields are ignored with a
  warning. A plan in which nothing resolves still fails.
- Allure export: `fullName`, `testCaseId` and `historyId` follow allure-pytest for tests
  without an explicit PlanSpec case (`export.allure.naming: nodeid` restores 0.1.0a1);
  only user markers without arguments become tags; parameters show redacted values
  (`export.allure.parameters: digest` restores digests); a non-assertion error in the
  test body is `broken`.

- CI runs the test matrix, the installed-wheel smoke and the visual client simulation
  on macOS (Apple Silicon). `0.1.0a1` was published without macOS receipts.

- `testence init` writes the readiness mapping its generated plan needs, so
  `plan prepare` reports `ready` for a freshly initialized project.
- `testence doctor` starts the configured browser channel instead of checking that a
  bundled executable path exists, and reports the command that fixes a failure. The
  check is named `browser`.
- `testence --version` prints the installed version.
- README links are absolute, so they resolve on PyPI, and the quick start follows the
  `pip install testence` path that needs no clone.
- CI runs and lints `examples/`, which the published quick start points at.

- `TESTENCE_BROWSER_CHANNEL` now also sets the default for `Settings` and engines
  constructed directly, so a host whose bundled Chromium cannot start can run the
  browser tests on `msedge` or `chromium-headless-shell`; explicit arguments and CI
  defaults are unchanged.

## 0.1.0a1 — release candidate

### September release audit

- Made frame contexts apply consistently to locator actions, JavaScript evaluation and
  predicate waits, closing a real authoring gap found in the NextDish site preview.
- Hardened the manual PyPI workflow against shell interpolation of dispatch inputs and
  made publication verify the embedded project name and version in both wheel and sdist.
- Added `testence plan prepare`, a browser-free per-scenario readiness gate for engine
  capabilities, required oracle adapters, credentials, files and HTTP/JSON fixtures.
  Explicit argv fix recipes can prepare dependencies, isolated targets or synthetic
  seeds and are always rechecked. Skill pack 0.1.4 requires this gate before discovery.
- Added optional digest-pinned viewport regression, explicit viewport profiles,
  manifested expected/actual/diff images, and inconclusive handling for unusable
  visual evidence. Installed-wheel client simulations run on Linux/Windows CI.
- Skill pack 0.1.2 documents autonomous visual proof and simulated-client boundaries;
  state-predicate selectors no longer get address-only healing proposals. See the
  [visual/client follow-up](../audits/2026-09-13/visual-client/README.md).

- Added plan-bound visibility assertions with verified/violated/inconclusive proof
  outcomes, plus regression coverage for unavailable browser evidence.
- Added pinned AdminLTE/Tabler UI cases, negative and harmless controls, timing
  receipts, root agent instructions and visual-discovery guidance in skill pack 0.1.1.
- Preserved explicit ephemeral CDP ports through settings and engine creation.
- Fixed transient Windows transaction cleanup and crash-test worker termination.
- Made corpus failures return nonzero, separated audit output directories and fixed
  the loading wait for multiple placeholders. See the
  [audit and remaining acceptance work](../audits/2026-09-13/README.md).

### Added

- Deterministic Playwright-over-CDP execution behind an engine protocol.
- Intent-bearing pytest DSL with exact-by-default assertions and element fingerprints.
- Append-only `testence/1` evidence ledger, bounded evidence packs and a single-file
  HTML report.
- Pluggable authentication strategies and an API client that shares the browser
  session for UI-to-API oracles.
- Reviewable locator-heal proposals; a failing step is never silently rebound.
- Process-sharded evidence for optional `pytest-xdist` execution.
- Allure and CTRF exporters rendered from the ledger.
- Synthetic mutation corpora for false-green, false-red and heal-quality checks.
- Reference compute kernels behind a versioned optional-native ABI.
- Versioned PlanSpec and verdict contracts with claim traceability through pytest,
  ledger, evidence packs and reports.
- A packaged, versioned Agent Skills set for `plan`, `author`, `triage` and `repair`,
  with Codex metadata and a safe cross-client update contract.
- A production-built React latency profile and broad multi-process performance budget
  gate for navigation, controlled inputs and mutation synchronization.
- A separate shared-browser CDP profile and budget for repeated agent-authoring runs.
- Opt-in warm `bench` and `watch` modes that reuse Python and pytest while reloading
  project modules between isolated sessions.

### Changed

- Text assertions use exact matching by default; containment is explicit.
- Evidence metrics count leaf-step latency to avoid double-counting nested actions.
- Interaction flake metrics are keyed by test identity and code digest.
- Network capture records aborted requests as first-class evidence.
- SPA readiness recognizes non-text controls inside asynchronously mounted roots instead
  of spending five seconds waiting only for `innerText`.
- Signalled save oracles synchronize on the scoped mutation response instead of global
  `networkidle`; fingerprint capture uses one non-waiting browser evaluation.
- Form fill has an opt-in `fast=True` path that preserves input events while skipping
  actionability checks already proved by a preceding readiness gate.
- Network capture waits yield in 10 ms event-loop quanta, reducing fast POST response
  observation p95 from 63 ms to 16 ms on the maintained real-React profile.
- CDP-attached runs no longer close the launcher's context. Five-process fresh-run p50
  fell from 3.21 s with launch-per-run to 2.02 s with a shared browser on the maintained
  profile.
- Warm pytest sessions reset run ids, fixtures, auth and evidence writers on every
  iteration while retaining one Playwright/CDP engine connection. On the maintained
  React profile, bootstrap p50 fell from 2.81 s to 0.45 s and whole-run p50 from
  3.45 s to 1.13 s.

### Security and release hygiene

- Removed local credentials, browser profiles, generated run data and
  application-specific scratch material before repository initialization.
- Public examples use reserved example domains and synthetic applications only.

## Benchmark notes

The checked-in E1, I3 and kernel result files are reproducible snapshots, not product
claims. Hardware, browser, runtime and target latency materially affect the numbers;
new releases should publish the exact command and environment alongside any result.
The React gate runs with `python bench/react_latency.py --repeats 5 --check`; its broad
ceilings detect timeout-shaped regressions and are not cross-host speed claims.
