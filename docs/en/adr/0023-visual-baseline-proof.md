# ADR-0023: Baseline-bound visual assertions

Status: implemented engineering capability; independent acceptance pending.

## Context

UI visibility assertions missed visual defects while semantic controls still worked.
The release audit also lacked reproducible client-consumer visual trials.

## Options compared

Model judgment on every replay would add nondeterminism and a provider dependency.
Screenshot storage alone cannot detect regression. A frozen pixel comparison offers
an explicit narrow visual oracle while leaving exploration and interpretation to agents.

## Decision

Provide optional `testence[visual]` using Pillow's PNG decoding and channel operations
([permissive MIT-CMU license](https://pillow.readthedocs.io/en/stable/about.html#license)).
Core replay without visual assertions has no new dependency. Capture a new baseline
only in an explicit authoring phase, pin its manifest digest, bind viewport/environment
and image bytes, and require two identical consecutive frames. Replay compares once
under frozen tolerances and emits the existing bound `ui` assertion contract.
Missing, tampered, unstable or incompatible evidence is inconclusive. Completed
pixel disagreement is a failed visual assertion. Retain expected/actual/diff images
and measured change region in the manifested failure pack. Never update baselines
or tune thresholds during replay. Limits: 16 MiB per PNG and 8 million decoded pixels.

## Consequences

Pixel mismatch does not establish intent, usability, accessibility or backend truth.
Profiles record OS, user agent, viewport, DPR, locale and media preferences; fonts
and OS patch-level rendering still require a controlled host. No perceptual masking,
automatic region discovery or anti-aliasing exemption is claimed; explicitly configured
redaction masks ([ADR-0024](0024-evidence-redaction-policy.md)) are recorded in the
baseline profile. Viewport configuration
is explicit for owned browsers; attached browser sizing belongs to its owner.

The installed-wheel client simulation proves package and deterministic proof plumbing.
Two client layouts with one scripted actor do not satisfy independent client acceptance.

## Tripwire

Any green on a seeded visual defect, false red on the DOM-only control, changed
baseline during replay, or violated assurance from unavailable evidence blocks this
capability. Run `bench/client_simulation/run.py` and the visual unit/live controls.
