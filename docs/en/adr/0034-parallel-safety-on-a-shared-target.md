# ADR-0034: Parallel safety on a shared target, classified from the ledger and proven

Status: accepted (methodology), 2026-11-02; a ledger footprint command and a neighbour
helper are pending.

## Context

ADR-0012 makes parallelism possible: process shards, ledger shards, per-worker seed
markers and ports. ADR-0031 adds an explicit opt-in for parallel debug, and says what
it cannot do: it cannot validate the application's isolation from declarations alone.
Nothing tells an agent which tests of a suite may share one target at the same time.

On a shared stand the browser is isolated, the server is not. Observed failure classes:

- cleanup scoped wider than the case, for example a sweep by a ticket or feature
  prefix, deletes objects of another worker running the same feature;
- one account for every worker: a login that revokes the previous session, a lockout
  after failed logins, per-user server state such as saved filters or column layout;
- assertions over unscoped reads: a count, an empty list, the first row, sort order or
  a page position see another worker's objects;
- singletons and reference data: global settings, dictionaries, feature flags;
- background jobs and queues whose length or completion a test waits on;
- load: timeouts that appear only when several workers hit the same stand.

A green parallel run does not show safety. Interference is timing-dependent; a run in
which two conflicting cases did not overlap passes.

## Options compared

1. Run everything serially on a shared target. Safe and slow; the cost grows with the
   suite and pushes teams to unrecorded shortcuts.
2. Let the author declare `testence_parallel` per test, as ADR-0031 already accepts.
   Cheap, but a declaration is a belief: nothing checks it.
3. Classify each case from what it actually read and wrote in a serial run, record the
   class in the test, and accept the class only after a parallel run with an
   adversarial neighbour shows no verdict change.
4. A stand per worker or per run. Strongest isolation; needs infrastructure many
   targets do not have. It remains the answer for class S at scale, outside this ADR.

## Decision

Option 3. A test runs in parallel on a shared target only after it is classified from
its footprint and the class survives the proof gates below.

**Footprint.** For each case, the serial baseline run gives two sources: the `net`
event (browser mutations and reads under `api_prefix`, identifiers templated as `{id}`)
and `api.request` events (fixture, seed and oracle calls, with full URL and a redacted
body clipped to 4 000 characters). From them, per resource (templated path), the case
has:

- own writes: create, update, delete of objects the case created in the same attempt
  or that carry its namespace marker;
- shared writes: any write to an object the case did not create;
- scoped reads: reads filtered by the case's marker or by IDs it created;
- unscoped reads: lists without such a filter, counts, singletons, settings, the
  current user's profile and preferences.

An unscoped read matters only when an assertion or a locator depends on it: a count, an
emptiness check, an order, a row index, a page position. Opening a list page and then
searching for the case's own object is a scoped read even though the page first loaded
the unfiltered list. Anything the ledger cannot see (browser requests outside
`api_prefix`, websockets, direct database seeding, a second HTTP client, a message bus)
makes the footprint unknown.

**Classes.**

| class | condition | how it runs |
|---|---|---|
| P | no shared writes; no assertion depends on an unscoped read of a resource another parallel case writes; no auth, account or global state | `@pytest.mark.testence_parallel`, any worker |
| G:`name` | shared writes or dependent unscoped reads on one resource `name` that no P case touches | `testence_parallel` plus `@pytest.mark.xdist_group("name")` under `--dist loadgroup`: serial within the group, parallel with the rest |
| S | login, logout, lockout and session tests; account or global settings; reference data; several shared resources; a control that changes server state; unknown footprint | a separate serial run, never concurrent with workers |
| X | must not run on a shared target, for example real deployments or external delivery; decided from the inventory before any run | runs only on a dedicated target; the shared-target run leaves it out with the recorded reason |

A case with no proof stays S. Classification moves a case only towards less
parallelism without proof; moving it towards P needs the gates again. A failure never
moves a case to X: AGENTS.md forbids deselecting a bound test to obtain green, and
interference moves a case to G or S, where it still runs.

**Completeness.** The parallel phase, the serial phase and the recorded X cases
together select exactly the collected set. A case selected by neither phase is a
silent deselection and blocks the run.

**Enforcement.** `testence debug --workers` refuses a parallel run unless
`extra.parallel` has `enabled: true`, `accounts` of `isolated` or `non-revoking` and
`cleanup: "asserted-absence"`, and every selected case carries `testence_parallel` and
`testence_namespace`. A plain `pytest -n` checks none of it. `testence debug` passes
only `-n`; an `xdist_group` marker has no effect without `--dist loadgroup`, and the
cases of one group then run at the same time. The project therefore puts
`--dist loadgroup` in its pytest `addopts`.

**Project prerequisites.** Data created by a case carries the `testence_namespace`
marker of that case, not a ticket or feature prefix. Cleanup deletes only that marker
and proves absence (`extra.parallel.cleanup: "asserted-absence"`). Leftovers of
interrupted runs are swept in one serial step before workers start, never by a
per-case fixture. The account policy is recorded as `extra.parallel.accounts`:
`isolated` when a project auth strategy gives each worker its own account,
`non-revoking` when a probe showed that a second login keeps the first session valid
and no test asserts per-user server state. A cached session (`session_probe_path`)
lets workers share one login but takes no lock: on a cold cache every worker logs in
at once, so it does not make a revoking target safe. Lockout is never probed by
failing logins on a shared account; it is taken from the product's documentation or
owner.

**Proof gates.** All on the same target, revision and worker count N:

1. Serial baseline: the selected set is green and its footprints are derived.
2. Repetition: the P and G set runs in parallel K times (K ≥ 3) with the same verdicts
   as the baseline, without `--testence-reruns`.
3. Neighbour: during one parallel run, also without reruns, a separate process
   creates, renames and deletes objects with a foreign marker in every resource the P
   set writes or reads unscoped. A verdict change marks the case as reading shared
   state. This is the negative control of isolation: a P class is proven only after
   it survived the neighbour. The neighbour writes to the shared target, so it needs
   the same authority as the tests and cleans its own marker with asserted absence.
4. Cleanup audit: every update or delete a case sent through the API client targets an
   ID it created in the same attempt or a name carrying its marker; after the run, a
   search for each case's marker finds nothing. Browser-side mutations are templated in
   `net`; for them, the step's target must be located by the case's marker. When a
   created ID is not visible in the recorded, redacted and clipped response body, the
   audit of that case is inconclusive and the case stays S.
5. False red: a failure that appears only in parallel is interference. It reclassifies
   the case or fixes its scoping. It is never rerun, retried, or absorbed by a longer
   timeout.

N is chosen by measurement: the largest N at which no step timeout appears that is
absent from the serial baseline, compared on `api.request` durations and test wall time.

The classification, its evidence run IDs and the account probe result are kept in a
project document beside the tests, so another agent can recheck them.

## Consequences

- Under `--dist loadgroup`, pytest-xdist appends `@name` to the node ID of a grouped
  test. Testence removes that suffix before deriving the ledger's `test`, the case
  and variant IDs, the Allure identity and the namespace marker, so a grouped case
  keeps the identity of its serial baseline. Before that fix, a probe on 2026-11-02
  gave the two variants of one grouped test two case IDs, both different from the
  serial run.
- The first parallel run of a suite costs a serial baseline, K parallel runs and a
  neighbour run. Every later run's ledger yields footprints again; only changed cases
  and cases whose footprint differs from the recorded one need the gates again.
- The serial S phase and the parallel phase are two runs with two run IDs;
  `ci evaluate` takes one run, so CI evaluates each phase on its own.
- An account per worker needs a project auth strategy; the framework has no per-worker
  credential mapping.
- A `--control` that changes server state (a flag on the target, a seed variant)
  affects every worker; such a negative run is class S. A response adapter is per
  context and stays with the case's class.
- Other people or agents running against the same stand are another neighbour this
  ADR does not control. Stand leasing is out of scope; a run that overlapped one is
  not evidence for gates 2–5.
- Until a footprint command exists, the agent derives footprints by reading `net` and
  `api.request` events; the neighbour is project code using the project's seed adapter.

## Tripwire

Revisit when a case classified P fails in parallel and passes serially on the same
revision, when the cleanup audit finds a write outside a case's own objects, or when
gate 3 cannot be run against a target. Any of these blocks parallel execution for the
affected resource until the class is corrected and the gates pass again. Revisit the
cost when classification and gates take longer than the parallel speedup saves over a
month of runs.
