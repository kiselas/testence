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
`ex.clock`), context emulation (`browser.emulation`), recorded request mocking (`browser.network_mock`,
`ex.route`), a recorded WebSocket gate (`browser.websocket_mock`, `ex.ws_gate`) and
`browser.native` (`ex.native`). Its DSL wrappers use strict locators:
multiple matches fail unless the author deliberately supplies `Target(..., nth=N)`.
`fast=True` is an explicit actionability weakening. It is recorded on `step.start` and
changes an otherwise verified attempt to `unverified` for review.

`ex.expect_settled(target, intent=None, *, timeout_ms=None)` (`browser.dom`) waits
until the target's `getBoundingClientRect` is the same in two consecutive
`requestAnimationFrame` frames and the box lies wholly inside the viewport. Use it
before measuring anything that animates in: a drawer is visible from its first frame,
so its width read after `expect_visible` is a width of the transition. The frames are
counted in the page in one round trip; the wait is an `expect_settled` entry of the
wait ledger. An element that never stops, or stays outside the viewport, fails as an
assertion naming its last box.

`ex.open(route, intent=None)` (`browser.navigation`) opens a route the fastest correct
way: when the page already shows the application on `base_url`'s origin (its root has
rendered something), the route is pushed to the app's own router, as a click on an
in-app link would; otherwise (the first navigation, another origin, a route outside
`base_url`, an application not mounted) it is a document load. The client-side path
needs a router that listens to `popstate` (React Router, Vue Router and most others
do): if the document does not change within 500 ms of the pushed route, `ex.open`
loads the route instead. It returns `navigate` or
`goto`, and the step's `step.end` records it as `navigation`. Client-side navigation
keeps mounted component state: a case about a first load uses `ex.goto`.

After a document load the engine probes whether the application has painted
anything (`wait_until_rendered`). Under the DSL the probe waits for the next step: a
step with a target skips it, because waiting for its own element is the stronger
readiness signal (`wait_until_rendered(skipped)` in the wait ledger); a step without
a target (a URL check, a screenshot, an oracle, `ex.native`) runs it first; a probe
still due when the test ends runs then. An engine used directly, without the DSL,
probes right after `goto` as before, and a direct engine call that follows a deferred
probe (outside a DSL step) runs it first.

`ex.reset_storage(keys, intent=None, *, session=False)` (`session`) removes the named
`localStorage` (or `sessionStorage`) keys and returns how many were set; under
`page_reuse: module` it clears what a previous test left on the shared page.

Inside `with ex.frame(...)`, locator actions, `eval_js`, and `wait_for_predicate_js`
share the same active iframe. Leaving the context restores the previous page or nested
frame scope. Page-level session and network operations remain page-level.

Adapters can implement `CapabilityProvider`, `LifecycleEngine`, and `EvidenceEngine`
without importing Playwright. A platform-neutral fake therefore exercises lifecycle,
evidence and export code while a browser action raises `UnsupportedCapability` with
the operation, required capability and available set. Pre-capability custom engines
retain the old composite surface as a migration path, but cannot claim conformance
until they declare their set.

## Readers

A reader returns what the page shows to the test, as one recorded step with the
target's diagnostics when it fails. It is as strict as a click: a target that matches
two elements fails and names both. The step records how much it read (`read` on its
`step.end`: characters, items, a box size), never the value, and leaves the page fit to
hand to the next test under `page_reuse: module`, which `ex.native` does not.

| Reader | Returns | Waits |
|---|---|---|
| `ex.text(target)` | the visible text of one element | for the element |
| `ex.texts(target, minimum=1)` | the texts of every match, in document order | for `minimum` matches; `0` reads what is there |
| `ex.count(target)` | how many elements match now | no (use `expect_count` to wait for a number) |
| `ex.is_visible(target)` | whether the one element is visible now | no |
| `ex.attribute(target, name)` | the attribute, or `None` | for the element |
| `ex.box(target, settled=False)` | a `Box` (`x`, `y`, `width`, `height`, `right`, `bottom`, `center`) | for a visible element; `settled=True` also until it stops moving |
| `ex.boxes(target, minimum=1)` | the boxes of every visible match | for `minimum` matches |
| `ex.url()` | the current page's address | no |
| `ex.storage_item(key, session=False)` | one `localStorage` (`sessionStorage`) value, or `None` | no |
| `ex.read_js(intent, function, arg=None)` | what a JavaScript function returns | no |

`read_js` is for what no other reader expresses, such as a computed style or a value the
product keeps in a global. The function must only read: anything that acts on the page
belongs in an action or in `ex.native`, because a page changed by a reader would still
be handed on. Coordinates are CSS pixels of the page viewport, the ones the pointer uses.

## Raw Playwright: `ex.native`

When the DSL cannot express an interaction, `ex.native` hands over the Playwright
`Page` inside one recorded step:

```python
with ex.native("sign on the signature pad") as page:
    box = page.locator("canvas#signature").bounding_box()
    page.mouse.move(box["x"] + 10, box["y"] + 10)
    page.mouse.down()
    page.mouse.move(box["x"] + 120, box["y"] + 40, steps=8)
    page.mouse.up()
ex.expect_enabled(Target("role", "button", name="Submit"))
```

The step carries the intent, duration and any failure like every other step, and a
`native.used` ledger event marks that the interactions inside were not recorded one by
one. A failure inside produces the usual pack; no heal is proposed, because no target
went through the DSL. The block runs in the page, not in an active `ex.frame`; use
`page.frame_locator(...)` inside it for frames. An engine without the `browser.native`
capability refuses before the block runs ([ADR-0027](adr/0027-native-escape-hatch.md)).
