# ADR-0038: Opt-in page reuse within a module

Status: implemented (engineering, opt-in). Refines ADR-0021 and ADR-0032.

## Context

Every test gets a fresh browser context and logs in (ADR-0021); ADR-0032 keeps the
browser process per worker but still creates a context per test. On a single-page
application most of a short test is that setup: a context, a login, a document load
and the application booting, repeated for each test of a module that looks at the same
signed-in screen. Measured on a React application, `goto` alone averaged 854 ms over 96
calls of a 76-test run. A competing suite sharing one page per file finished the same
cases faster serially.

Sharing state between tests is what isolation exists to prevent, so the change must be
opt-in, bounded to tests that agree on how they log in, and must never carry over what
one test configured for itself.

## Options compared

- A session-wide shared page: the fastest, and the order of tests starts to matter
  across the whole suite.
- Module-scoped fixture written by the project: works, but every project reimplements
  the reset and gets the evidence boundaries wrong.
- An opt-in `page_reuse: module` in the engine fixture that hands the page to the next
  test of the same module and login, after a reset, and stops at anything that cannot
  be reset: chosen.

## Decision

`testence.json` accepts `page_reuse`: `test` (default, unchanged) or `module`. With
`module`, a test hands its page to the next test pytest runs when that test is in the
same module, logs in the same way (the configured scheme, or anonymous) and is not
marked `@pytest.mark.testence(fresh_page=True)`. The next test takes it over:

- other tabs are closed and the network, console, WebSocket and wait buffers cleared,
  so each test's evidence and `test.waits` stay its own;
- its `auth` phase reuses the login (`reused: true`, 0 ms) instead of logging in again;
- the ledger records `page.reuse` instead of `browser.start`, and a `page reused` note
  naming the test it came from.

A page is not handed on, and the next test starts fresh, when the test failed, when it
installed something that belongs to it alone (`ex.route`, a fake clock, a WebSocket
gate, a response rewrite, `ex.native`, a frame scope), when trace or video recording is
on, in warm or attached mode, or when the next test does not share the key; a `page not
kept` note says why. `ex.reset_storage(keys)` removes named `localStorage` (or
`sessionStorage`) keys a previous test left. An interrupted run closes a kept page at
session end.

## Consequences

Tests of a module that opt in run without a context, a login and a cold application
per test. They do share cookies, storage and the current document, so a test that
needs a clean slate says `fresh_page=True` or clears what it reads. Order within a
module now matters for those tests; a failure always breaks the chain, so it cannot
spread into the next test.

## Tripwire

Revisit if a defect is traced to state handed on between tests that the reset or the
blockers missed, or if reordering tests (`--testence-schedule`, random order plugins)
makes page reuse rarely apply.
