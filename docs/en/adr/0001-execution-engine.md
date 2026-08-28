# ADR-0001: Playwright-over-CDP as the execution engine, behind a facade

Status: accepted (2026-08-25)

## Context

The runner must drive real Chrome through the DevTools protocol (headed, attachable
by triage agents), execute steps in milliseconds, and survive a React SPA whose
timing behavior burned us repeatedly in manual agent-driven runs (30 s screenshot
timeouts, "wait 3–5 s and retry", canvas zoom eating clicks). The waiting layer is
where e2e flakiness is born: ~45% of flaky web tests are async-wait related.

## Options compared

| | Playwright (lib) | Puppeteer | raw CDP client | interactive MCP (playwright-mcp / chrome-devtools-mcp) |
|---|---|---|---|---|
| Transport | CDP for Chromium | CDP | CDP | CDP |
| Auto-waiting / actionability | built-in, mature | partial (waitForSelector; no actionability checks on all ops) | none — we write it | n/a (agent retries = LLM round-trips) |
| Semantic locators (role/label/text) | yes | limited | none | via accessibility snapshot |
| ARIA snapshots for evidence | `locator.aria_snapshot()` | manual via CDP | manual via CDP | yes, but per-call token cost |
| Attach to running Chrome | `connect_over_cdp` | `connect` | native | `--cdp-endpoint` |
| Network/console capture | events API | events API | manual | limited |
| Speed per step | ~ms (CDP call) | ~ms | ~ms | 10–40 s (LLM in loop), ~114K tokens/test (Currents, 2026) |
| Languages | Py/TS/Java/.NET | TS (Py port unofficial) | any | n/a |
| License | Apache-2.0 | Apache-2.0 | — | Apache-2.0 |

Key fact: Playwright, Puppeteer and a raw client all speak the same protocol — the
same `Input.dispatchMouseEvent` reaches the browser. The choice buys (or forfeits)
the *waiting and locating layer*, not transport speed.

## Decision

Playwright library (sync API) over CDP. **Behind a facade**: only
`testence/engine/` may import it (`Engine` protocol + `Target` dataclass are the
public boundary). CDP-raw remains reachable via `new_cdp_session` for evidence
collection. Interactive MCPs are kept for what they are good at: agent triage
against the live browser the runner leaves behind — never as the runner.

Rejected: raw CDP client (re-implementing actionability waits — the top flake
source — for zero transport gain); Puppeteer (same protocol, weaker
waiting/locators, Node-lock); MCP-as-runner (LLM cost and nondeterminism in CI).

## Consequences

- Auto-waiting kills the "sleep and retry" pattern from manual runs; DSL code
  never sleeps (enforced convention).
- Precedent (Stagehand v3 went CDP-native, claiming +44% on complex DOMs) stays
  available as an *optimization* behind the facade, not a rewrite.
- Upper layers are testable against a fake Engine.

## Tripwire

`step_latency_ms` p95 > 500 attributable to the driver (not the app), or ≥ 2
flakes/month traced into the engine layer → run a comparative experiment with a
CDP-native executor on the golden suite before any rewrite decision.
