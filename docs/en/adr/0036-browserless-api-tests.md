# ADR-0036: An API-only test runs without a browser

Status: implemented (engineering). Refines ADR-0010 and ADR-0012.

## Context

`testence_api` depended on `testence_engine`, so every API-only test started a
fresh browser context and logged in through it even when the scheme logs in with
one HTTP request and the test never looks at a page. Measured on a React
application, such tests took 2.6-5.5 s against 1.2-1.8 s for a plain HTTP suite
running the same calls; the difference was the browser context and its login.
The browser was also what made such a test's failure pack possible, so dropping it
naively would have lost the evidence of a failed seed.

## Options compared

- Keep the browser and make the context cheaper: still pays a context and a
  login per test, and the gap stays proportional to the suite.
- A separate `testence_http` fixture: two clients for one session; existing tests
  keep paying the browser and need rewriting to benefit.
- Decide per test from what it asks for and how its scheme logs in, and give a
  browserless test a small session object that the strategies and the failure
  pack can use: chosen.

## Decision

`testence_auth` no longer depends on `testence_engine`. It asks for the browser
when the test's fixture closure contains `ex` or `testence_engine`, or when the
scheme needs a page (`form`, `attached`, `storage-state`, a custom
`module:factory`, `api_auth_from_storage`). Otherwise the login writes into a
`BrowserlessSession`, which keeps the cookies, headers and storage a strategy
produces and refuses every page operation with a message naming the fix.

- The calls of a browserless test are `api.request` events, as before, and its
  wait ledger: `test.waits` lists them as op `api.request`.
- A failure of a browserless test still assembles a pack: its history holds the
  calls, `browser.json` says `mode: browserless`, and the page sections say there
  was no browser.
- A test that asks for `ex` later through `request.getfixturevalue` gets a
  browser carrying the session the HTTP login produced.

## Consequences

An API-only test costs its HTTP calls plus a small fixed overhead (under 100 ms in
the regression test). Lifecycle notes of such a test contain no `browser.start`
or `context.fresh`. Healing, screenshots and the network digest need a page and
are absent for it, as they were in substance before.

## Tripwire

Revisit if a supported scheme starts to depend on browser state for an API call
(for example a CSRF token read from the page), or if an API-only test is found
whose evidence differs from the browser-backed run beyond the page sections.
