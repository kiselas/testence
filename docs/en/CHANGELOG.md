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

### Changed

- Text assertions use exact matching by default; containment is explicit.
- Evidence metrics count leaf-step latency to avoid double-counting nested actions.
- Interaction flake metrics are keyed by test identity and code digest.
- Network capture records aborted requests as first-class evidence.

### Security and release hygiene

- Removed local credentials, browser profiles, generated run data and
  application-specific scratch material before repository initialization.
- Public examples use reserved example domains and synthetic applications only.

## Benchmark notes

The checked-in E1, I3 and kernel result files are reproducible snapshots, not product
claims. Hardware, browser, runtime and target latency materially affect the numbers;
new releases should publish the exact command and environment alongside any result.
