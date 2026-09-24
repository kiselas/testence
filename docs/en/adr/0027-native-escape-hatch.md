# ADR-0027: One recorded escape hatch to raw Playwright

Status: accepted (amends ADR-0001).

## Context

ADR-0001 keeps Playwright types inside `testence.engine` so the DSL stays engine-neutral.
Anything the DSL did not express — canvas interaction, a custom drag widget, a key
chord, a browser API — had no route at all: a team had to fork the library or abandon
the test. Every DSL gap became a dead end.

## Options compared

- **Keep the boundary absolute.** Engine neutrality, and adoption blocked on every gap.
- **Expose the page freely** (a fixture returning `Page`). Easy, and unrecorded actions
  would erode the evidence and step intent the framework exists for.
- **One explicit, recorded seam.** A context manager that yields the engine's own page
  inside a DSL step, gated by a capability.

## Decision

`with ex.native("<intent>") as page:` yields the Playwright `Page` of the current test
inside one `step` with that intent. A non-empty intent is required. A `native.used`
event records that interactions inside were not recorded one by one. A failure inside
is a failed step with a pack; no heal is proposed. Engines declare `browser.native`;
one that does not refuses with `UnsupportedCapability` before the block runs.

## Consequences

The DSL remains the default and the documented path; the author skill says so. Tests
using `ex.native` are tied to Playwright. Assertions should still go through the DSL
after the block, so oracles and evidence stay bound.

## Tripwire

If `native.used` appears in most tests of real suites, the DSL is missing primitives
and they should be added (L12) rather than the seam widened.
