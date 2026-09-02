# ADR-0018: Warm pytest process for the authoring loop

Status: accepted (2026-09-02, opt-in and measured)

## Context

After browser reuse, a fresh attached React run still spent about 1.5–1.8 seconds on
Python and pytest bootstrap. Repeating `pytest.main()` inside one interpreter removes
that cost, but doing so without an explicit lifecycle is unsafe: project modules stay
cached, plugin globals survive, a run id is process-scoped and wait summaries can mix
between sessions.

## Decision

- `watch --warm` and `bench --warm` are authoring-only modes. They refuse arbitrary
  commands and accept direct `pytest` or `python -m pytest` invocations only.
- Every iteration creates a new pytest session. Fixtures, engine attachment, auth
  context, evidence writer and run directory are recreated by that session.
- Before iteration two and later, imported project modules under the configured reload
  roots are removed from `sys.modules`, then import caches are invalidated.
- Testence modules and `__main__` are protected from eviction so the runner control
  plane cannot combine old objects with newly imported framework globals.
- Every session receives a new run id, and the pytest plugin clears its wait summary at
  session start.
- Browser persistence remains a separate CDP concern governed by ADR-0008.
- The warm process retains one Playwright/CDP engine across pytest sessions. A key over
  browser-connection settings replaces the engine when configuration changes; runner
  shutdown closes it. Auth, capture buffers and evidence remain session- or test-scoped.

## Consequences

The fixture boundary showed that reconnecting the Playwright/CDP engine was the largest
remaining controllable bootstrap component. On the maintained real-React profile,
fresh attached bootstrap p50 was 2,807.64 ms and steady warm bootstrap p50 was
447.18 ms: 84.1% lower. Whole-run p50 fell from 3,446.94 ms to 1,132.93 ms (67.1%).
The gate uses p50 and relative reduction; with five samples p95 equals a single maximum
and remains diagnostic so ambient host load cannot manufacture a false regression.

Warm mode does not promise operating-system process isolation. Process-global state in
third-party plugins or modules outside the reload roots may survive. Release, CI,
corpus and final validation runs therefore continue to use fresh processes.

## Tripwire

Disable warm mode if a rerun observes stale saved code, a shared run directory or a
surviving session-scoped fixture. Revisit the recommendation if bootstrap reduction is
below 15% across five runs on two representative hosts. Any correctness disagreement
between warm and fresh modes removes warm mode from the recommended authoring path.
Disable engine retention if a restarted browser or changed configuration can leave a
stale connection, or if warm and fresh modes disagree on auth or capture state.
