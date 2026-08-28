# The benchmark corpus

Seeded behaviours from
[docs/en/benchmark/taxonomy.md](../../docs/en/benchmark/taxonomy.md),
run against the target in [bench/sut](../sut), scored mechanically.

```bash
.venv/Scripts/python bench/corpus/run.py                 # every item once
.venv/Scripts/python bench/corpus/run.py --repeats 3     # the repeat policy
.venv/Scripts/python bench/corpus/run.py --only D-40-first-interaction-swallowed
```

The runner starts the target if one is not already up, gives every item its own
store, and reads outcomes **from the run ledger** rather than from pytest's exit
code — the score needs per-claim detail and the ledger carries it (ADR-0003). That
also means the corpus is scored through the framework's own evidence: if the ledger
is wrong, the benchmark is wrong too, loudly.

Not related to the older `corpus/` at the repository root. That one mutates a
static page to pin heal behaviour; this one is the benchmark.

## What is scored, and what "caught" means

| metric | meaning |
|---|---|
| `outcome_accuracy` | the suite went red exactly when it should |
| `false_green_rate` | seeded behaviours that slipped through green |
| `false_red_rate` | controls reported as failures |
| `right_reason_rate` | of the items caught, how many broke **the claim the defect falsifies** |
| `heal_recall` | drift items that carried a proposal |
| `detection_by_stratum` | catches split by deceptiveness (N/P/O/A) |

`right_reason_rate` is what separates this from the older corpus. Going red is not
enough: a run that fails some other claim has not caught the defect, it has had an
accident that coincided with one. Collateral failures are *reported and not
punished* — a defect that stops the collection rendering breaks most claims, and
that is honest blast radius rather than imprecision.

## Three rules the canonical suite lives by

Stated here because each was learned by getting it wrong first.

**Nothing is retried.** Waiting for a condition is what an auto-waiting engine is
for; repeating an *interaction* is not. Two items in the set are cured by a repeat
(`retry_hides_it`), and they are precisely the ones that distinguish a framework
from a retry loop.

**Every oracle claim is self-checkable.** The oracle sends the same run and the same
defect list the page carries, so the API misleads it exactly as it misleads the
page. Claims are therefore answerable by the API against itself — "the reported
total equals what you will actually hand over" — rather than against a copy of the
product known to be healthy. No real oracle has one of those, and a corpus that
gives itself one measures the author's access rather than the framework's power.

**A parameter change is committed exactly once, through one path.** See below.

## What building this corpus found

Four things, none of which were visible from the design.

**Two items collided because one interaction had two commit paths.** The search box
debounces typing *and* commits on Enter. A control says typing alone is inert by
design, so a suite must press Enter — but then the debounce fires as a second
update and cures the swallowed-first-interaction defect, hiding it. Search commits
explicitly now, and the swallowed-first-interaction item is caught through paging,
whose commit path is a single click. That is also truer to the original defect,
which swallowed the first search, page change *or* sort alike.

**A "harmless change" control was not one.** Renaming a control was listed among
rename/restyle/reorder/wrap as changes that must stay green. Restyling, reordering
and wrapping survive semantic addressing; **renaming breaks the accessible name**,
and the correct outcome is a red run carrying a heal proposal. It is now a drift
item (`U-01`) with `ui_change` as its ground truth.

**A control found a fragile suite, which is what controls are for.** Adding 300 ms
to every response turned three claims red. The defect was mine: they read the
counter after setup had waited only for "a row exists", and placeholders are rows.
The suite was passing on the target's speed. Claims that read the counter now state
their own precondition.

**`expect_text` matched substrings, and that is a false-green generator.** Found by
a repeat producing a different failing-claim set: an assertion that the collection
holds 4 rows was satisfied by a transient 48 on the way there. The project had
already ruled on this shape for locators — loose matching on an identity value is a
silent hazard — but the assertion path had the same hazard with a worse outcome, a
*passing* assertion. Text assertions are now exact by default with an explicit
`exact=False` opt-out; pinned by `tests/test_expect_text.py`.

## An honest reading of the current numbers

The collection screen scores 1.0 across the board. **That is not a good benchmark
result, it is a saturated one**, and it was expected: this screen carries only the
P and O strata — defects that a precise assertion or an API oracle catches, which
is the territory the framework is built for.

The headroom lives in the A stratum ("green almost always"): a concurrent write
that silently overwrites another, a component that changes state after it looks
settled, a resource never released on delete. All of them live on screens that are
not built yet. Until those exist, treat these numbers as a **smoke floor** — they
prove the harness measures what it claims and would catch a gross regression, and
they do not yet discriminate between versions of the framework.
