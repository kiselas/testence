# ADR-0017: Event-driven SPA readiness and mutation synchronization

Status: accepted (2026-09-02, latency probe implemented)

## Context

React and similar SPAs break two generic readiness shortcuts. A page can be usable while
its root contains only an input, icon or canvas and therefore has no `innerText`.
Conversely, polling, analytics and streams can keep the network permanently non-idle.
Waiting for text or global network quiet turns successful actions into timeout-shaped
latency.

The same-host `bench/spa_latency.py` probe models an asynchronously mounted root,
controlled input and 100 ms API polling. Before this decision, navigation spent
5,048.67 ms waiting for text that would never exist; `Actions.fill` took 11.10 ms p50
because fingerprinting made two extra browser round-trips; a 750 ms `networkidle`
fallback consumed essentially its full budget.

The complementary `bench/react_latency.py` gate drives the repository's production-built
React SUT through the public DSL. It separates fresh-process bootstrap, navigation,
controlled-input steps, the exact POST-response wait, React's visible commit and the
complete mutation round trip. Three fresh processes are the gate floor; the documented
maintainer run uses five.

## Options compared

1. Lower every timeout globally.
2. Assign `element.value` directly and bypass Playwright for input speed.
3. Keep `networkidle`, with per-project budgets.
4. Wait on local semantic state and the exact mutation response; optimize ambient
   evidence work independently.

## Decision

Choose option 4.

- SPA readiness accepts text or meaningful non-text UI inside a known `#root`, `#app`,
  React root, or the body fallback. It remains best-effort and has a 2 s budget; the
  next locator action owns exact readiness through Playwright auto-waiting.
- `save_and_verify(expect_request=...)` takes a network mark before the click and waits
  for the matching completed response after that mark, then gives local UI state two
  animation frames to commit. It does not wait for global network quiet. `networkidle`
  remains only a compatibility fallback when no mutation signal is declared and before
  bounded failure evidence capture.
- Green-run fingerprints use one non-waiting `evaluate_all` snapshot instead of
  `count()` followed by an auto-waiting evaluation.
- Normal fill stays Playwright's event-correct `locator.fill()`. `fast=True` uses its
  `force` path only after an explicit readiness proof; direct DOM assignment is rejected
  because it can bypass controlled-input state and application events.
- Capture-buffer waits yield to Playwright's event loop in 10 ms quanta. This preserves
  responses that completed before the wait began while avoiding the 50 ms observation
  floor paid by fast APIs.
- CI evaluates broad, absolute ceilings on distributions from fresh processes. They are
  regression tripwires, not a machine-comparison score; a single millisecond assertion is
  explicitly not part of the contract.

## Consequences

On Windows 11, Python 3.12.13 and Playwright 1.62.0, the same probe measured navigation
at 114.29 ms (44× faster), `Actions.fill` at 6.97 ms p50 (37% lower), and a scoped
mutation response at 116.39 ms versus 737.62 ms for the polling-hostile idle wait. These
are same-host diagnostic measurements, not public cross-machine claims.

On the real React SUT, reducing the capture-buffer quantum from 50 to 10 ms changed the
POST-response p95 from 63 to 16 ms and mutation-round-trip p50 from 127.5 to 84.0 ms.
Across the final five-process launch snapshot the mutation p50 was 81.9 ms, and the
public controlled-fill step measured 15.2 ms p50 in the default path and 14.0 ms with
`fast=True`; all maintained budgets passed. Raw results and
the exact environment are in `bench/results/react_latency.json`.

Default actionability checks remain intact. Applications with no declared request signal
still use the slower fallback. The wait ledger retains both the operation and time, so a
future regression is attributable rather than hidden in total test duration.

## Tripwire

Revisit if the SPA readiness heuristic returns before the first actionable state in more
than 1% of golden runs, if response-scoped saves miss an emitted mutation in any accepted
test, or if steady-state `Actions.fill` p95 exceeds 20 ms on the synthetic probe without
application work. The real-React gate must also remain green for three or more fresh
processes. A fast path that changes controlled-input behavior is removed even if its
latency is lower.
