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
frames, popups and tabs, upload/download, dialogs, fake timers (`browser.clock`,
`ex.clock`), context emulation (`browser.emulation`) and `browser.native` (`ex.native`). Its DSL wrappers use strict locators:
multiple matches fail unless the author deliberately supplies `Target(..., nth=N)`.
`fast=True` is an explicit actionability weakening. It is recorded on `step.start` and
changes an otherwise verified attempt to `unverified` for review.

Inside `with ex.frame(...)`, locator actions, `eval_js`, and `wait_for_predicate_js`
share the same active iframe. Leaving the context restores the previous page or nested
frame scope. Page-level session and network operations remain page-level.

Adapters can implement `CapabilityProvider`, `LifecycleEngine`, and `EvidenceEngine`
without importing Playwright. A platform-neutral fake therefore exercises lifecycle,
evidence and export code while a browser action raises `UnsupportedCapability` with
the operation, required capability and available set. Pre-capability custom engines
retain the old composite surface as a migration path, but cannot claim conformance
until they declare their set.

## Raw Playwright: `ex.native`

When the DSL cannot express an interaction, `ex.native` hands over the Playwright
`Page` inside one recorded step:

```python
with ex.native("drag the card to the Done column") as page:
    page.drag_and_drop("[data-card=42]", "[data-column=done]")
ex.expect_text(Target("testid", "done-count"), "1")
```

The step carries the intent, duration and any failure like every other step, and a
`native.used` ledger event marks that the interactions inside were not recorded one by
one. A failure inside produces the usual pack; no heal is proposed, because no target
went through the DSL. The block runs in the page, not in an active `ex.frame`; use
`page.frame_locator(...)` inside it for frames. An engine without the `browser.native`
capability refuses before the block runs ([ADR-0027](adr/0027-native-escape-hatch.md)).
