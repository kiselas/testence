# ADR-0031: Guarded debug and response-stage contract adapters

Status: implemented engineering candidate; acceptance recorded in the cycle audit.

## Context and proposal (AUD-DC26)

Field notes report full-suite selector reruns, multipart corruption when forwarding
uploads, early observations mistaken for silent rejection, and installation confusion.
Acceptance claims: DC26-01 exact-case selection/refusal plus ARIA; DC26-02 one original
upload with exact bytes and adapted JSON; DC26-03 one action with bounded declared
outcome observation; DC26-04 explicit parallel isolation gates; DC26-05 separate
phase timings; DC26-06 installation status. All evidence is synthetic.

## Options compared

Raw pytest node IDs are fast to type but imports may expand the selection. A guarded
fresh-process preflight costs another collection and rejects unexpected selection.
Playwright route.fetch reconstructs forwarding; a page-fetch shim only covers fetch
and changes the application runtime. CDP Fetch response interception covers the tested
fetch/XHR paths while leaving request submission to the browser. Reusing a context
would need additional isolation proof; existing opt-in warm authoring remains separate.

## Decision

Expose debug/status through CLI and MCP. Pin node IDs and collected test-file hashes
between preflight and replay. Collection is not a sandbox and imports execute; the
fingerprint does not pin conftest or dependencies. Parallel replay requires declared
account/cleanup policy plus markers and namespace fixtures; it cannot validate the
application's isolation merely from those declarations.

Rewrite bounded JSON only at CDP response stage. Mark provenance before fulfillment,
including failed transformations. Never resend a request. UI outcome observation has
a fixed deadline, rejects stale/ambiguous outcomes and never retries an action.

## Consequences and tripwire

Guarded debug adds collection overhead and two separate per-phase deadlines. Return
execution status independently from verified assurance. Phase totals overlap; worker
sums are not wall time. Adapters are Chromium-specific defect injection, never backend
acceptance. Service workers, OOPIF and streaming support remain unproven. Input body
size is checked after CDP retrieval, not a hard preallocation memory bound. Any duplicate
upload, unmarked adaptation, expanded selection executing a body, or false backend
assurance invalidates these claims and requires a failing regression control.

Primary references consulted 2026-10-05:
- [CDP Fetch](https://chromedevtools.github.io/devtools-protocol/tot/Fetch/)
- [pytest selection and fresh invocation](https://docs.pytest.org/en/stable/how-to/usage.html)

These are protocol/tool references, not a claim that academic research establishes
market leadership or that the private application pilot has been measured again.
