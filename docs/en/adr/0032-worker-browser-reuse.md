# ADR-0032: One owned browser per worker, fresh context per test

Status: engineering candidate, explicit opt-in.

## Context

AUD-LC26 observes variable slow Edge shutdown (15..18s per process in a four-worker
synthetic probe). Repeated full launch/close adds work unrelated to a product claim.
Existing sibling sessions already support independent users in one browser.

## Options compared

Keep a full browser per test: strongest process isolation, pays startup/close per case.
Keep a page/context: loses cookie/storage/route isolation. Kill by image name or switch
channel after failure: violates ownership or hides the target failure. Retain an owned
browser per pytest worker and create a fresh context each time: avoids repeated process
lifecycle, keeps deterministic replay and independent context state, but browser-wide
crashes and process state can affect that worker.

## Decision

Opt in with --testence-browser-reuse or boolean extra.browser_reuse. This applies only
to isolated mode, rejects attached/persistent/warm configurations and uses the existing
sibling context path. Each case still authenticates and navigates normally, has its own
recording and network buffers and closes its context after pass/fail. The session owner
closes the owned browser/driver once before the run ledger closes. An idle owner context
is infrastructure, never a product case; its raw recording is discarded at shutdown.
CLI debug --reuse-browser and MCP browser_reuse expose the same explicit choice.

## Consequences and tripwire

No LLM dependency, automatic action retry or locator healing. This is context isolation,
not independent browser-process isolation. Tests of browser-wide settings/crashes must
use default fresh browsers. No optimization of goto or promise of a specific four-worker
speedup. Final session shutdown remains potentially slow. A leaked cookie/storage/route,
lost failed recording, missing worker shutdown or borrowed-browser termination rejects
this mode. Benchmark both process wall time and counts; never sum nested timing phases.

Primary references consulted 2026-10-05:
- https://playwright.dev/python/docs/browser-contexts
- https://github.com/microsoft/playwright/issues/41210
- https://github.com/microsoft/playwright/pull/41330

The upstream pipe mechanism is a hypothesis for this host, not an established explanation
of the historical 111.93s outlier. Preserve the baseline and all probe results.
