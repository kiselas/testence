# T20 engine capability and strict action implementation receipt

Date: 2026-09-06. Status: locally implemented and verified on Chromium/Windows.

## Delivered behavior

Engine adapters now publish `testence/engine-capabilities/1`. Public structural
`CapabilityProvider`, `LifecycleEngine`, and `EvidenceEngine` protocols contain no
Playwright types. A platform-neutral fake can participate in lifecycle/evidence/export
without pretending to provide DOM. Missing operations raise typed
`UnsupportedCapability`; PlanSpec scenarios can declare capability requirements and
pytest rejects an unsupported backend during collection.

Playwright implements the declared R1 matrix: navigation, strict DOM locators and open
shadow DOM, network/WebSocket, screenshot/accessibility/JavaScript, keyboard/focus/
scroll, frame scope, popup/page switching, upload/download, and dialogs. Observation
helpers no longer select the first ambiguous match. `fast=True` remains explicit,
lands in step evidence as `fast-actionability`, and lowers assurance to `unverified`.
The public `testence capabilities` command supports machine preflight.

ADR-0022 and synchronized EN/RU guides define versioning, adapter migration and the
rule against widening declarations to hide missing behavior.

## Consumer receipt

[`outputs/.../t20-capability-consumer`](../../../outputs/audit-2026-09-06-followup/t20-capability-consumer/README.md)
contains the CLI capability document and a real Chromium conformance run covering the
web fixtures plus the no-DOM fake negative.

## Verification

| Check | Observed |
|---|---|
| Full pytest | `322 passed, 2 skipped in 111.87s` |
| Focused contracts/capabilities/assurance/pack | `59 passed in 7.85s` |
| Real Chromium capability suite | `5 passed in 5.08s` |
| Ruff check/format | 121 files clean |
| mypy | success, 51 source files |

## Boundary

Windows Chromium conformance is complete. The matching Linux browser matrix and old
third-party custom-engine migration receipt remain release acceptance work in T25.
Firefox, WebKit and native/mobile capabilities stay outside R1. This receipt becomes
immutable only after review and commit.
