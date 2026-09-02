# ADR-0008: Headed Chrome with an open CDP port as the shared substrate

Status: accepted (2026-09-02, shared-browser lifecycle measured)

## Context

Who owns the browser? Classic e2e launches a private (usually headless) browser per
run and destroys it. Our triage loop needs the opposite at failure time: the page
*at the failure state* is the single most valuable testence, and agents/humans must
be able to attach to it after the run.

## Options compared

| | headed Chrome, open CDP port (chosen) | headless, runner-private | per-test fresh browser |
|---|---|---|---|
| Post-failure live triage | attach via `--cdp-endpoint` / devtools MCP | impossible — state destroyed | impossible |
| Reuse a developer's logged-in profile | yes (`connect_over_cdp`) | no | no |
| Dev watches the run | yes (product requirement) | no | no |
| Speed | ≈ headless (E5 will measure the delta) | fastest | slowest (launch per test) |
| CI fit | via xvfb-run on Linux | native | native |

## Decision

- Default: **headed** system Chrome (`channel="chrome"`), launched with
  `--remote-debugging-port`, or attach to an already-running Chrome via
  `--testence-cdp` (the existing browser profile and cookies are reused).
- On any test failure the session **keeps the browser alive** and each evidence
  pack carries `browser.json` (CDP endpoint + page URL) — the attach protocol for
  any MCP/CDP client. Runner detaches; it never kills the crime scene.
- Context per session, page reused, capture buffers reset per test; per-test
  contexts/parallel shards are a designed-in later step (run/test ids in every
  event since day one).
- Ownership is explicit. A launched or persistent engine closes the context it
  created; a CDP-attached run borrows the launcher's context and only detaches its
  Playwright client. It must never close the logged-in context on a green run.
- CI: same headed mode under `xvfb-run` (Linux); live triage is a local feature —
  CI failures are triaged from evidence packs (they must suffice, hypothesis H3).

## Consequences

- One browser serves both the deterministic runner and interactive agent tools —
  no "reproduce it first" step in triage.
- A shared long-lived browser can accumulate state; the marker+cleanup discipline
  (SeedAdapter contract) and per-test tap resets bound the blast radius.
- Windows dev machines get headed natively; Linux CI pays an xvfb layer (standard).
- On the production-built React profile, five fresh launch-per-run processes measured
  3,208.11 ms p50. Five processes attached to one shared browser measured 2,022.56 ms
  p50 (37% lower); bootstrap p50 fell from 2,584.47 to 1,475.00 ms. Starting the shared
  browser cost 1,240.15 ms once, so this same-host profile breaks even on the second
  repeated run. These are development-loop diagnostics, not cross-machine claims.

## Tripwire

E5 measures headed vs `--headless=new` on the golden suite: if headed costs > 25%
wall-clock in CI *and* zero CI failures in a quarter needed live attach, CI may
flip to headless-new while local stays headed. Behavior divergence between modes
found by E5 on any case → that case pins headed everywhere and the divergence is
filed as evidence.

The attached latency budget must remain green for at least three fresh pytest
processes, and a second attach must preserve the launcher's context. If reuse saves
less than 15% after five repeated runs on two maintained hosts, remove the automatic
speed recommendation while retaining attach for authentication and triage.
