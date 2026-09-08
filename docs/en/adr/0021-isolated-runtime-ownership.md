# ADR-0021: Isolated runtime and resource ownership

Status: accepted. Date: 2026-09-06.

## Context

A session-scoped browser context let cookies, storage, pages and role state pass from
one test to the next. Preserving a locally launched browser after failure also left an
owned process alive in CI. Worker-specific ports alone did not provide test isolation.

## Options compared

1. Keep a session context and rely on every project to clear it correctly.
2. Launch a complete browser for every test in all modes.
3. Make isolated execution the default, retain a browser only in explicit warm mode,
   replace its owned context per test, and treat CDP attachment as foreign ownership.

## Decision

Use option 3. Stateful pytest fixtures are function-scoped. Isolated runs create and
close an owned browser for each test, including failures. Warm authoring retains one
owned browser but replaces the context before auth for every test. Attached authoring
borrows a context and never closes or replaces it. Seed markers bind project, run,
worker, case, role and attempt; adapter cleanup is an owned, visible lifecycle step.

## Consequences

CI pays browser startup cost for the strongest default boundary. Teams can measure and
opt into warm mode without changing proof scope. Old custom engines without
`reset_session` retain a compatibility path that only resets taps; they must migrate
before claiming warm isolation. Browser manifests expose ownership and mode.

## Tripwire

Revisit if isolated startup makes the accepted CI budget impossible after measurement.
Any optimization must preserve fresh cookies/storage/auth and owned-process cleanup.
