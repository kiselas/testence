# ADR-0011: Self-healing as a reviewable proposal, never a runtime rebind

Status: accepted (2026-08-25) — measured on the failure corpus

## Context

Locators drift: a button is renamed, a field's label changes, a component is
rewritten. Someone has to notice and update the test. The industry's answer is
"self-healing", and it comes in two very different shapes:

1. **Runtime rebinding** — on failure, find a similar element and use it, so the run
   goes green.
2. **Proposal** — on failure, record what the element used to look like, name the
   best candidate, and hand a human or agent a diff to accept.

Shape 1 is what makes self-healing sound magical and what makes it dangerous: a
framework that heals its way around a *deleted* button reports green while the
feature is broken. Every serious tool (Healenium, mabl, testRigor) reports healed
locators for confirmation rather than silently absorbing them.

## Decision

Heal is a **motion**: the framework proposes, a reviewer accepts, and the accepted
change lives in git as an ordinary edit to test code. There is no runtime rebinding
and no configuration flag to enable it.

Mechanics:

- Every green step records a multi-attribute fingerprint of the element it touched,
  keyed by `(test id, step intent)` — intent, not locator, because the locator is
  the thing that drifts. Storage is a JSON file in the project's repo
  (`.testence/fingerprints.json`): reviewable and diffable, unlike a database.
- On failure of a step that had a target, the page is scanned for addressable
  elements, each scored against the remembered fingerprint
  (`kernels.score_candidates`), and the result is written into the evidence pack as
  `heal.json` — score, runner-up, rationale, and a ready `suggested_edit`.
- **The floor is the point.** Below a similarity of `MIN_SCORE = 0.6`, the verdict
  hint is `real_bug` and no address is proposed: the element is gone, not moved.
- A test id that survived short-circuits to a perfect score. It is not one signal
  among many — a human put it there to say "this is the element the test means", so
  it outranks a rewritten tag, role and text.
- Two candidates within `AMBIGUOUS_MARGIN` are flagged `ambiguous`: the proposer
  still picks the winner, but the reviewer is told it was close.

## Measured on the corpus (9 items, `corpus/run.py`)

| metric | value |
|---|---|
| `heal_recall` (drifts that got a proposal) | 1.0 |
| `heal_precision` (proposals naming an acceptable address) | 1.0 |
| `disappearance_discrimination` (deleted elements refused a heal) | 1.0 |
| `false_green_rate` / `false_red_rate` | 0.0 / 0.0 |

Getting there required fixing three defects the corpus exposed and unit tests did
not: fingerprints computed inconsistently in two places, scoring weights that
favoured exactly the attributes which drift, and loose substring matching that hid a
real drift (see `corpus/README.md`).

## Consequences

- Heal quality is measurable and regression-tested, not a demo.
- The proposal is evidence, not authority: `TRIAGE.md` tells a triage agent to treat
  `heal.json` as something to check, since a confident wrong proposal is worse than
  none.
- A first run has no baseline and therefore no proposals. That is correct behaviour
  (a guess without a baseline is noise) and it is why the corpus always runs a green
  baseline first — measuring the cold start would measure the wrong thing.

## Tripwire

`disappearance_discrimination` below 1.0 on any corpus run blocks a release: healing
around a deleted element is the failure mode that discredits the whole feature. If
`heal_precision` drops below 0.8, revisit the weights *with corpus data*, and add the
item that exposed the drop.
