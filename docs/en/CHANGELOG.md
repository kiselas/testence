# Changelog

This project is pre-alpha. Until a first tagged release, notable changes are grouped
under `Unreleased`; compatibility is not guaranteed.

## Unreleased

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
