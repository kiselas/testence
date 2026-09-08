# Failure corpus

Mutation testing, applied to a test framework. Each item breaks the target page in a
way whose correct interpretation is known in advance, which turns claims that would
otherwise be untestable — "the evidence is sufficient", "healing works", "we don't
report false failures" — into numbers.

```bash
python corpus/run.py                                  # all items
python corpus/run.py --only ui_change_button_renamed  # one item
python corpus/run.py --keep                           # keep workspaces to inspect
```

Results land in `corpus/results/corpus.json` (summary + per-item records).

`expected-state-v1.json` is the deterministic oracle classification corpus. Pytest runs
its 13 healthy/adversarial cases directly through `observe_expected_state`; it covers
optimistic and stale reads, delayed commit, rollback, wrong entity/role and unusable
HTTP responses. It has no browser or external-service dependency and ships in the
source distribution.

`r1-correctness-v1.json` is the frozen R1 registry: 40 unique cases in the required
20 product-defect / 10 healthy-control / 5 repairable-drift / 5 ambiguous-infrastructure
strata, including eight holdouts. Validate its structure and adjacent SHA-256 freeze in
CI with:

```bash
testence corpus validate corpus/r1-correctness-v1.json --structure-only --json
```

Omit `--structure-only` for the acceptance gate. It intentionally exits 3 until two
licensed OSS targets record exact commits/reset recipes and two independent reviewers
confirm the truth labels and deterministic reproduction. The structural freeze is
complete; those external receipts are not synthesized by the project.

## How an item runs

1. A workspace is created with a pristine copy of the target page.
2. **Baseline run** on the pristine page — this is what gives the heal proposer a
   memory of "working". Without it a proposal is a guess, so the corpus measures
   the framework as it actually operates: second run onwards, not a cold start.
3. The mutation is applied and the same suite runs again.
4. Mechanical expectations are checked against the evidence packs.

## What is measured without an LLM

| metric | meaning | current |
|---|---|---|
| `outcome_accuracy` | suite failed exactly when it should | 1.0 (9/9) |
| `false_green_rate` | seeded defects that slipped through green | 0.0 |
| `false_red_rate` | controls (reorder, restyle) reported as failures | 0.0 |
| `heal_recall` | drifted locators that got a proposal | 1.0 |
| `heal_precision` | proposals naming an acceptable new address | 1.0 |
| `disappearance_discrimination` | deleted elements refused a heal (guardrail) | 1.0 |

`expect_heal` is a *list* of acceptable addresses: several addressings of one
element (role+name, a test id, an id selector) are equally valid, and grading
against one arbitrary form would measure the corpus author's taste rather than the
proposer's accuracy.

## What still needs an agent

`verdict` on each item is ground truth for grading triage verdicts
(`verdict_accuracy`, `real_bug_recall`) — that pass reads the packs with an agent and
compares its verdict to the label. The corpus produces the packs; scoring them is a
separate, deliberate run.

## Defects this corpus has already found

Kept as a record, because each one was invisible to inspection and to the unit tests:

1. **Inconsistent fingerprints.** `element_fingerprint` read the `role` attribute
   while `candidate_elements` inferred it from the tag, so the same element scored
   against itself as a stranger — a rename looked like a deletion.
2. **Weights favoured volatile attributes.** Text and aria-label — exactly what
   drifts — outweighed tag, role and id, pushing a renamed button below the
   "it's gone" floor (0.48 against a 0.6 threshold).
3. **Loose matching hid a real drift.** `get_by_placeholder` matches substrings by
   default, so a field renamed from "name" to "full name" kept passing against an
   element the test never meant to address. Identity attributes now match exactly
   (`Target.exact`), and the drift surfaces as a failure with a proposal.

## Adding an item

Add a `CorpusItem` to `items.py`: a mutation, the ground-truth `verdict`, whether the
suite should fail, and — where relevant — `expect_heal` or `expect_no_heal`. Prefer
mutations that model a realistic behaviour change; a mutation nobody would ever make
teaches nothing. Include controls: a framework that cries wolf at reordering or
restyling is worse than no framework.
