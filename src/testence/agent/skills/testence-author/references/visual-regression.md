# Autonomous visual proof and client simulation

Use `testence[visual]` for deterministic viewport comparison. Ordinary replay makes
no model calls. The host agent supplies exploration, a visual contract, baseline
review and failure interpretation; pixel equality alone does not establish usability.

## Author and freeze

1. Declare the permitted local/test target, synthetic seed, states, viewports and
   visual claim in PlanSpec. For isolated Chromium set `viewport` to an object with
   integer `width`/`height`, `debug_port` to 0, and `capture_policy.screenshots` to true.
   Configure an attached browser's viewport through its owner instead.
2. Use visible controls and inspect screenshots plus accessible state. Explicitly
   wait for the required state before capturing. Give clocks/data/fonts a controlled
   fixture; do not mask errors, disable product features or add retries to obtain green.
3. In a separate authoring script call
   `testence.visual.capture_baseline(engine, NEW_directory, provenance=...)`.
   It requires two identical consecutive captures and returns the SHA-256 digest
   of `baseline.json`. Review the PNG at its actual viewport. An agent may accept
   a synthetic baseline inside an authorized engineering simulation; record that actor.
   Outside that scope use the project's existing baseline approval policy.
4. Freeze baseline directory and returned digest with the accepted test/plan.
   Defaults allow zero changed pixels and zero channel tolerance. A nonzero allowance
   is an explicit contract decision set at capture time and requires proving controls.
5. Replay only `ex.expect_screenshot(str(directory), baseline_digest=pinned_digest,
   assertion_id="a.visual", claim_id="page.visual")`. Bind the assertion in PlanSpec
   as `oracle: "ui"`. Never capture or replace baselines in the test or on failure.

## Prove and judge

Run fresh processes: healthy, a visible defect with working semantic controls,
restored healthy and a DOM-only harmless change. Exercise responsive breakage on
the relevant viewport, including a desktop control where the mobile defect is absent.
Gate on exact assertion failure, verified/violated assurance and clean integrity,
not pytest exit alone. Missing/tampered baselines, incompatible profiles, unstable
frames and transport failures are inconclusive. Never classify them as product defects.

Read `visual-*.json` and its expected/actual/diff PNGs in the failed pack. Their bytes
are bound by the pack manifest. Highlighted pixels locate a change; they do not prove
its cause. A changed accepted visual requirement may justify a reviewed new baseline;
an unintended visual defect does not justify locator healing or relaxed tolerances.

## Simulate a new client

Use a new project with its own `pytest.ini` and settings, an installed wheel, isolated
Python, no inherited `PYTHONPATH`/Testence configuration and the packaged client skills.
Record wheel/package hashes, install/verify commands, test/baseline hashes, observations,
replay and triage timings, and validated verdict submission. A second client layout
checks packaging portability; it does not mean Claude or another independent model ran.

Repository harness: `bench/client_simulation/README.md`. Its known synthetic contract
supports a narrow scripted judge which receives only a pack, not mutation labels.
For an independent agent evaluation supply only the mission, installed instructions,
target and raw evidence; withhold expected answers. Record who actually executed it.

Hand off the exact command, immutable baseline digests, plan/claim IDs, failed step,
artifact paths, failed attempts, remaining uncertainty and next proving command.
