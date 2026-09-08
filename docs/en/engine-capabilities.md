# Engine capabilities and strict actions

Inspect the selected backend before collection:

```bash
testence capabilities --project . --json
```

The output uses `testence/engine-capabilities/1`. A PlanSpec scenario may require
capabilities such as `browser.dom`, `browser.frames`, or `browser.files`; collection
fails before execution when the backend does not declare every requirement.

The R1 Playwright backend declares lifecycle, session, navigation, DOM and open shadow
DOM, network/WebSocket, screenshot, accessibility, JavaScript, keyboard/focus/scroll,
frames, popups, upload/download and dialogs. Its DSL wrappers use strict locators:
multiple matches fail unless the author deliberately supplies `Target(..., nth=N)`.
`fast=True` is an explicit actionability weakening. It is recorded on `step.start` and
changes an otherwise verified attempt to `unverified` for review.

Adapters can implement `CapabilityProvider`, `LifecycleEngine`, and `EvidenceEngine`
without importing Playwright. A platform-neutral fake therefore exercises lifecycle,
evidence and export code while a browser action raises `UnsupportedCapability` with
the operation, required capability and available set. Pre-capability custom engines
retain the old composite surface as a migration path, but cannot claim conformance
until they declare their set.
