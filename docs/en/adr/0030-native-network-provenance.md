# ADR-0030: Observe the outcome of native network routes

Status: implemented (engineering). Extends ADR-0027.

## Context

`ex.route` marks substituted answers, but raw `page.route` and `context.route`
could make an equivalent answer look authoritative to a mutation oracle.

## Options compared

- Treat all registered routes as mocks: misclassifies spying and authentication.
- Return a Page facade: breaks the explicit raw Playwright seam.
- Patch Playwright globally or inspect private transport: affects unrelated
  clients and binds correctness to implementation details.
- Observe public route outcomes on these client instances: chosen.

## Decision

Keep the original Page and Route objects. Observe native route registrations on
the page/context and future pages once the seam is entered. Wrap handler dispatch
with its original signature; map original callback identities for `unroute`.
Observe `fulfill` and `abort` before dispatch so response/failure events have
provenance. Emit `network.mocked` with source native and actual request URL.
`continue_`/`fallback` are not substitution. The API oracle uses its independent
HTTP client. A fetched response later fulfilled is still substituted.

## Consequences

Scoped public-method interposition is a compatibility surface: verify one- and
two-argument handlers, times, fallback chains, new pages and session replacement.
Cleanup restores client methods and removes only registrations made through this
observer, including from borrowed contexts. Preexisting handlers are preserved.
HAR replay, service workers, external interception and registrations predating
the seam remain outside this contract. Async native handlers are not introduced.

## Tripwire

Healthy and passthrough saves must remain proved. Native fabricated saves must
be rejected explicitly as mocked, aborts must remain marked without a response,
and model exploration of registration/cancellation/dispatch/close must match its
independent state model. No automatic retry or assertion relaxation is permitted.

Semantics: [Playwright Route](https://playwright.dev/python/docs/api/class-route).
