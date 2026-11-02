# ADR-0033: Negative proof — a recorded run in which the test failed for its claim

Status: implemented (engineering): `testence.controls`, `--control`,
`ci evaluate --quality-mode proven`; tracked as S06–S09 of
[stage 5](../../stages/05-proof-strength/README.md).

## Context

`verified` means every required assertion bound to a claim passed. It does not mean the
assertion could fail. A test whose expected value was copied from what the product showed
during discovery, or whose comparison is vacuous, is `verified` on every run, and
`ci evaluate --quality assurance` accepts it. Nothing in the ledger distinguishes it from
a test that would catch the defect its claim is about.

The author skill already demands the missing step: run the test against a negative control
and confirm it fails for the intended claim (`testence-author` step 8 and completion gate,
`testing-a-feature.md` section 5, repair completion gate). That proof lives only in the
agent's report. A reviewer cannot check it, and CI cannot require it.

The synthetic corpus solves the same problem for Testence itself: each seeded defect names
the claims it falsifies, and `right_reason` holds when those claims are among the claims
that failed (`bench/corpus/run.py`). Collateral failures are reported, not disqualifying.

## Options compared

1. **Mutate application code** (mutation testing, as PIT does for unit tests). Testence
   drives a deployed application through a browser; it does not own or build the code.
   Not applicable.
2. **Automatically perturb what an oracle reads** (flip a field in the read response and
   expect the assertion to fail). Cheap and needs no declaration, but it proves only that
   the comparator compares. It cannot tell whether the test exercises the path that breaks
   when the product breaks. Rejected as the proof; may return later as a lint.
3. **Agent attestation**: the agent writes in its report or in a verdict that it saw the
   test fail. Not machine-checkable, and it is exactly what the gap is today. Rejected.
4. **Declared negative controls evaluated from the ledger.** The project names ways to
   break the target and the claims each one falsifies. A run records which control was
   active; the existing assertion events record which claims failed. Chosen.

## Decision

**Control declaration.** A control is declared in `testence.json`, not in the PlanSpec:
the plan states what must be true, the project owns how to break it, and PlanSpec v2
scenario objects are strict, so a new field would break plans for older readers.

```json
{
  "controls": {
    "discount-not-persisted": {
      "description": "The cart API answers the save but drops the discount",
      "claims": ["checkout.discount.persisted"]
    }
  }
}
```

Names follow the identity rules of claim IDs. `claims` is non-empty. Testence does not
know how to break a product: the test or its fixtures apply the control (a response
adapter, a seed variant, a feature flag on a synthetic target) when it is active.

**Activation.** `testence run --control NAME` (pytest `--testence-control NAME`) activates
exactly one control for the whole run. An undeclared name is a usage error. Reruns are
refused while a control is active, because a repeated attempt can erase the defect
signature. `run.start` records `control: {name, description, claims}`. Tests read the
active control through the `testence_control` fixture (`None` when no control is active).

**Negative proof of a claim.** Given a green run `G` and a negative run `N` with control
`K`, claim `C` has negative proof when:

- `C` is in `K.claims`;
- a test `T` binds `C` in both runs, with the same `test_digest` and `plan_digest`;
- in `N`, `T` ended with a failed assertion whose `claim_id` is `C`, and assurance
  `violated`.

Per required claim of `G` the outcome is one of:

| Outcome | Meaning |
|---|---|
| `proven` | the conditions above hold for at least one test binding `C` |
| `stayed_green` | the control targeting `C` was active and `T` did not fail on `C`; the test cannot detect the defect its claim is about |
| `wrong_reason` | `T` went red, but `C` is not among its failed claims |
| `inconclusive` | `T` ended `inconclusive`, `aborted`, `not_run`, or failed outside an assertion |
| `stale` | `T` in `N` has a different test or plan digest than in `G` |
| `no_control` | no supplied negative run has a control that targets `C` |

Failed claims other than `C` in `N` are reported as collateral and do not change the
outcome, the same rule as the corpus `right_reason`.

**Gate.** `ci evaluate --quality proven --negative-run DIR` (repeatable) applies every
`assurance` check to `G`, then requires `proven` for each required claim bound in `G`.
The receipt gains `quality.negative_proof`: one entry per claim with outcome, test node
ID, negative run ID, control name and collateral claims. `assurance` and `execution`
modes are unchanged.

**A negative run never proves product behaviour.** A run whose `run.start` carries a
control is refused as `G` by `ci evaluate` in every mode. Mocked and adapted responses
remain inadmissible as proof of persistence (ADR-0030, ADR-0031); inside a negative run
they are the expected means of breaking the target.

## Consequences

- `proven` is opt-in. It costs one extra run per control, and some claims have no honest
  control (permissions on a shared target, third-party delivery). Those stay at
  `assurance`, and the receipt shows `no_control` instead of hiding them.
- `inspect` and the HTML report show, per claim, the green result and the negative-proof
  outcome when a negative run is supplied (S07).
- A control that breaks everything produces `proven` for every claim it lists and
  collateral for the rest. Collateral is visible in the receipt and the report, so a
  reviewer can see a control that is too blunt.
- Nothing in ordinary replay changes: without `--control`, runs and ledgers are
  identical to today's, apart from the absent `control` field.

## Tripwire

Revisit when any of these is observed:

- a test reaches `proven` while a regression control shows it cannot fail on the state
  change its claim describes;
- across a project's negative runs, more than half of failed claims are collateral, which
  means controls are too blunt for `proven` to carry information;
- `proven` adds more than the duration of one full green run per control to the median
  CI time of the projects that enable it.
