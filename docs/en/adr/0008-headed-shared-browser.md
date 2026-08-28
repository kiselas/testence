# ADR-0008: Headed Chrome with an open CDP port as the shared substrate

Status: accepted (2026-08-25)

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
- CI: same headed mode under `xvfb-run` (Linux); live triage is a local feature —
  CI failures are triaged from evidence packs (they must suffice, hypothesis H3).

## Consequences

- One browser serves both the deterministic runner and interactive agent tools —
  no "reproduce it first" step in triage.
- A shared long-lived browser can accumulate state; the marker+cleanup discipline
  (SeedAdapter contract) and per-test tap resets bound the blast radius.
- Windows dev machines get headed natively; Linux CI pays an xvfb layer (standard).

## Tripwire

E5 measures headed vs `--headless=new` on the golden suite: if headed costs > 25%
wall-clock in CI *and* zero CI failures in a quarter needed live attach, CI may
flip to headless-new while local stays headed. Behavior divergence between modes
found by E5 on any case → that case pins headed everywhere and the divergence is
filed as evidence.
