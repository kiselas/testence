# Benchmark corpus

The benchmark runs seeded behaviours against the synthetic application in
`bench/sut/` and scores the results mechanically through Testence's own evidence
ledger.

## Current scope

The implemented collection-screen set contains one healthy baseline, nine behavioural
defects, one accessible-name drift case and six harmless controls. The authoritative
list and expected claims live in `bench/corpus/items.py`; injectable behaviour is
declared in `bench/sut/defects.json`.

Run it with:

```bash
python bench/corpus/run.py
python bench/corpus/run.py --repeats 3
python bench/corpus/run.py --only D-40-first-interaction-swallowed
```

The runner starts the synthetic target, gives every item an isolated store and reads
per-claim outcomes from `run.jsonl` rather than reducing a run to pytest's process
exit code.

## Metrics

| metric | meaning |
|---|---|
| `outcome_accuracy` | each item went red or stayed green as expected |
| `false_green_rate` | seeded defects that escaped detection |
| `false_red_rate` | harmless controls reported as failures |
| `right_reason_rate` | the intended claim, not merely another test, failed |
| `heal_recall` | drift cases that produced a proposal |
| `detection_by_stratum` | catches split by N/P/O/A deceptiveness |

Collateral failures remain visible but do not count as catching the intended defect.

## Design constraints

- No interaction retry: repeating an action can erase the defect signature.
- API oracles query the same seeded store and parameters as the UI.
- A parameter is committed through one explicit path so a second handler cannot
  accidentally hide a first-interaction defect.
- Controls include structural changes and latency so the suite cannot depend on the
  target being fast or on incidental DOM layout.
- Scores from a partial corpus are smoke-floor evidence, not proof of broad product
  coverage.

## Remaining coverage gaps

The corpus does not yet implement multi-page workflows, two concurrent browser
sessions, long-running operations, file uploads/downloads, cross-origin flows,
websockets, iframes, mobile viewports or accessibility assertions. Those gaps should
be closed before using a composite score to compare releases or competitors.
