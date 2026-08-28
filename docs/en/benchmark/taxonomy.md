# Synthetic failure taxonomy

Testence evaluates itself with seeded behaviours whose expected outcomes are known in
advance. The taxonomy is product-neutral and intentionally small enough to audit.

## Outcome classes

| class | expected runner outcome | expected triage verdict |
|---|---|---|
| behavioural defect | red | `real_bug` |
| address drift | red plus a reviewable proposal | `ui_change` |
| timing instability | red with timing evidence | `flaky_timing` |
| harmless control | green | `none` |
| environment mismatch | red | `environment` |
| coherent behaviour change | red | `behaviour_change` or provisional with `blocked_on` |

## Deceptiveness strata

The dynamic collection corpus additionally labels defects by what a test needs to
observe:

- **N — naive:** a broad visible check should catch it.
- **P — precise:** only a precise assertion catches it.
- **O — oracle:** the UI looks plausible; an independent API oracle is required.
- **A — intermittent:** a single run is likely to pass; repeated or concurrent
  observation is required.

Controls are not assigned a stratum. Their job is to measure false-red behaviour.

## Implemented families

The checked-in synthetic target currently covers:

- a first interaction that is silently discarded;
- a view that fails to catch up after a successful write;
- permanent placeholders;
- deleted rows that remain listed;
- ignored deep-link state;
- counters and page windows that disagree with the API;
- prefix-only search where substring search is promised;
- a dropped filter;
- accessible-name drift with a heal proposal;
- harmless restyling, reordering and wrapping;
- slow responses, irrelevant console noise and an explicit Enter-to-commit design.

The older static-page corpus covers locator rename, element removal, wrong values,
actions that do nothing, delayed async results and harmless DOM restructuring.

## Rules

1. Every item names the claim that must fail; any other failure is collateral, not a
   successful detection.
2. Defects and controls are both required. A framework that catches everything by
   failing everything has zero value.
3. Interaction retries are disabled because some defects are specifically hidden by
   repeating an action.
4. A heal proposal never changes the running test. It is evidence for review.
5. Published scores must state the corpus revision, repeats, browser and hardware.

Source-of-truth item definitions live in `corpus/items.py` and
`bench/corpus/items.py`; this document describes their stable categories rather than
claiming coverage for scenarios that are not yet implemented.
