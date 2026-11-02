# Parallel safety on a shared target

Use this when a person asks to run tests in parallel against one target, when you add
`@pytest.mark.testence_parallel`, or when a test fails only under `-n`. The decision
record is ADR-0034 in the Testence docs; this file is the procedure.

The browser of every worker is isolated. The server is shared. A green parallel run is
not proof: conflicting cases may simply not have overlapped. Do not mark a test
parallel because it "looks independent"; classify it from what it did and prove the
class.

## 1. Inventory the target once

Write a short project document beside the tests (for example
`docs/parallel-safety.md`) and fill it before classifying any case:

| Question | Where the answer comes from |
|---|---|
| Does a second login with the same account keep the first session valid? | Probe: log in twice, call the session probe path with the first session |
| Is there a lockout after failed logins? | Product documentation or its owner. Never probe it by failing logins on a shared account |
| Which server state is per user? | Saved filters, column layout, recent items, notifications, preferences |
| Which data is global? | Settings, reference dictionaries, feature flags, singletons |
| Which names must be unique? | API schema, validation errors |
| How are lists sorted and paged by default? | API schema, a read of the list endpoint |
| Which actions start background jobs or queues? | Product documentation, `net` mutations followed by polling reads |
| Can the ledger see every write? | Browser requests under `api_prefix` and calls through `testence_api` are visible; other browser paths, websockets, direct database writes and another HTTP client are not |

Record the policy in `testence.json`:

```json
"parallel": {"enabled": true, "accounts": "non-revoking", "cleanup": "asserted-absence"}
```

`accounts` is `isolated` when a project auth strategy gives each worker its own
account, `non-revoking` when the probe showed both sessions stay valid and no test
asserts per-user server state. A cached session (`session_probe_path`) does not make a
revoking target safe: the cache takes no lock, so on a cold cache every worker logs in
at once. Otherwise the target is not ready for parallel runs: stop and report it.

`testence debug --workers` refuses a parallel run that lacks this policy or a case
without `testence_parallel` and `testence_namespace`. A plain `pytest -n` checks
nothing, so check the same conditions yourself before using it.

## 2. Make the project shard-safe

- Name created data with the case's `testence_namespace` marker (or
  `testence_seed_marker`). A ticket or feature prefix is not a namespace: two cases of
  one feature in two workers then delete each other's objects.
- Clean up only the case's own marker and prove absence with
  `testence_api.assert_absent(...)` or `ExpectedState.absent(...)`.
- Sweep leftovers of interrupted runs in one serial step before workers start, never
  in a per-case fixture.
- Locate the case's objects by marker or by the ID the seed returned, through search or
  a direct read, never by row index, first row or page position.

Changing the naming or cleanup of an existing suite is a change to its fixtures: show
the diff and run the affected cases serially green before continuing.

## 3. Derive each case's footprint

Run the selected set serially and read its ledger. `net` events hold browser mutations
and reads with IDs templated as `{id}`; `api.request` events hold fixture, seed and
oracle calls with the full URL. This prints both per test:

```python
import json, re, sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ids = re.compile(r"/(?:[0-9a-f]{8}-[0-9a-f-]{27}|\d+)(?=/|$)")
cases = defaultdict(lambda: {"writes": set(), "reads": set()})
for shard in sorted(Path(sys.argv[1]).glob("run*.jsonl")):
    for line in shard.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        case = cases[event["test"]] if "test" in event else None
        if case is not None and event["kind"] == "net":
            case["writes"].update(f"{m['method']} {m['path']}" for m in event["mutations"])
            case["reads"].update(f"{r['method']} {r['path']}" for r in event["reads"])
        elif case is not None and event["kind"] == "api.request":
            url = urlsplit(event["url"])
            query = f"?{','.join(sorted(parse_qs(url.query)))}" if url.query else ""
            side = "reads" if event["method"] == "GET" else "writes"
            case[side].add(f"{event['method']} {ids.sub('/{id}', url.path)}{query} (api)")
for test, footprint in sorted(cases.items()):
    print(test)
    for side in ("writes", "reads"):
        for entry in sorted(footprint[side]):
            print(f"  {side[0]} {entry}")
```

Run it as `python footprint.py <runs_root>/<run_id>`. Adjust the ID pattern to the
target's identifiers. The `net` reads drop query strings; check a list read's filter in
the test code or in `api.request`.

For every resource (templated path) a case touches, decide:

- **own write**: the object was created in the same attempt or carries the case's
  marker;
- **shared write**: anything else, including a PATCH to a pre-existing object, a
  setting or a dictionary entry;
- **scoped read**: filtered by the marker or by IDs the case created;
- **unscoped read**: a list without such a filter, a count, a singleton, the current
  user's profile or preferences.

An unscoped read matters only when an assertion or a locator depends on it: a count,
`expect_count`, an empty-state check, an order, a row index. A list page that loads
unfiltered and is then searched for the case's own object is scoped. If the footprint
misses writes the ledger cannot see, it is unknown.

## 4. Classify

| Class | Condition | Marking |
|---|---|---|
| P | no shared writes; no dependent unscoped read of a resource another parallel case writes; no login, account or global state | `@pytest.mark.testence_parallel` |
| G:`name` | shared writes or dependent unscoped reads on one resource that no P case touches | for now no parallel marker: record `G:name` in the project document and run the case in the serial phase |
| S | login/logout/lockout, account or global settings, reference data, several shared resources, a `--control` that changes server state, unknown footprint | no parallel marker; runs in a separate serial run |
| X | must not run on a shared target (real deployments, external delivery); decided from the inventory before any run | runs only on a dedicated target; the shared-target run leaves it out with the recorded reason |

Do not use `@pytest.mark.xdist_group` yet. Under `--dist loadgroup`, pytest-xdist
appends `@name` to the node ID, and Testence derives the case ID, the variant and the
namespace marker from the node ID, so a grouped case gets a different identity than in
the serial run. Without `--dist loadgroup` the marker does nothing and the group runs
concurrently. G stays a recorded class until identity ignores the suffix.

Without proof a case stays S. You may always move a case towards less parallelism;
moving it towards P needs the gates again. Never move a case to X because it failed:
that is a deselection to obtain green. Interference moves a case to G or S, where it
still runs. Write each case's class, the resource that decided it and the baseline
run ID into the project document.

Check completeness: the parallel phase, the serial phase and the recorded X cases
together select exactly the collected set. Compare the collected node IDs of
`pytest --collect-only -q` with and without each `-m` expression; a case selected by
neither phase is a silent deselection.

## 5. Prove the classes

Same target, same revision, same worker count N:

1. **Serial baseline** green; it is the footprint source from step 3.
2. **Repetition**: run the P set at least three times, `pytest -m testence_parallel
   -n N`, without `--testence-reruns`; verdicts equal the baseline.
3. **Neighbour**: during one parallel run, also without reruns, a separate process
   uses the project's seed adapter with a foreign marker to create, rename and delete
   objects in every resource the P set writes or reads unscoped. Any verdict change
   means a case reads shared state: reclassify it or scope its read. A P class is
   proven only after this gate. The neighbour writes to the shared target: it needs
   the same authority as the tests, and it cleans its own marker with asserted
   absence.
4. **Cleanup audit**: in `api.request`, every PUT, PATCH and DELETE of a case targets
   an ID the same attempt created or a name with its marker. Browser mutations are
   templated in `net`; check that their step targets are located by the marker. After
   the run, a search for each case's marker finds nothing. Response bodies are
   redacted and clipped at 4 000 characters; when a created ID is not visible there,
   the audit of that case is inconclusive and it stays S.
5. **False red**: a failure seen only in parallel is interference. Reclassify the case
   or fix its scoping. Never rerun it, retry the action, add a sleep or raise a timeout
   to absorb it.

Pick N by measurement: the largest N with no step timeout absent from the serial
baseline, comparing `api.request` durations and test wall time. Then run the G and S
cases serially: `pytest -m "not testence_parallel"`. The two phases are two runs;
evaluate each with `ci evaluate`.

A run that overlapped someone else's work on the same target is not evidence for
gates 2–5. Say so and repeat it.

## Report

Give the inventory answers, the account policy, each case's class with the deciding
resource, the run IDs of the baseline, repetitions and neighbour run, the cleanup audit
result, the chosen N with the measured times, and every case left in S or X with its
reason. A gate you could not run is reported as not run, and its cases stay S.
