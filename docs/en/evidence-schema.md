# Evidence schema `testence/1` (normative)

One JSON object per line in `runs/<run-id>/run.jsonl`. Append-only; UTF-8; `\n` line
endings on all platforms; fsync per event (crash-safety is the point, and it costs
0.5 ms per event). Fields are append-only within a major version; breaking changes
bump the version and parsers must refuse foreign versions loudly.

**One file per process, never per run.** Under `pytest -n` each worker writes
`run-<worker>.jsonl` beside the controller's `run.jsonl`, all inside one run
directory named by `TESTENCE_RUN_ID`. Not a preference: four processes appending to
one file lost 27 % of their events and produced torn lines, because the writer's
lock is a `threading.Lock` and means nothing between processes (ADR-0012).

**Readers must merge, and must not trust `seq` across files.** `seq` restarts per
process, so it orders events within one ledger and nothing more. Enumerate with
`testence.evidence.ledger_paths(run_dir)` and read through
`testence.metrics.load_run`, which merges in timestamp order. A merged run
legitimately contains one `run.start`/`run.end` per worker, each naming its worker
in the fingerprint.

## Envelope (every event)

| field | type | meaning |
|---|---|---|
| `v` | string | schema version, `"testence/1"` |
| `run` | string | run id (`r-YYYYMMDD-HHMMSS-xxxxxx`), shared by all workers |
| `seq` | int | monotonic **per process**, starts at 1 |
| `ts` | string | UTC ISO-8601, ms precision, `Z` suffix — the only cross-file order |
| `kind` | string | event kind, see below |
| `test` | string? | test id; absent on run-level events |

## Kinds and payloads

| kind | payload fields |
|---|---|
| `run.start` | `testence` (version), `fingerprint` {os, python, base_url, attach, worker} |
| `run.end` | `duration_ms`, `passed`, `failed` |
| `test.start` | `file`, `code` (12-hex digest of the test file), `nodeid` (pytest's full test address), `markers` (sorted marker names) |
| `test.end` | `status` ("pass"/"fail"), `duration_ms`, `pack`? (rel. dir on fail) |
| `test.waits` | `waited_ms`, `ops` (count), `by_op` {op: {ms, n}}, `top` (5 slowest) |
| `step.start` | `step` (id), `intent` (human sentence), `target`? (described), `depth` |
| `step.end` | `step`, `status`, `duration_ms`, `depth`, `children`, `fingerprint`? (green runs), `error`? |
| `net` | reserved (v0 captures network into packs; inline events may follow E4) |
| `console` | reserved (same) |
| `oracle` | `name`, `ok`, `diff`? (list of {field, ui, api}) |
| `pack` | `dir` (rel.), `sections_est_tokens` {aria, network, console, oracle}, `error` |
| `note` | `text` + free fields |

When a pytest test is bound to a PlanSpec through the `testence` marker, the writer
additively attaches two optional fields to all of its events: `plan` (`schema`, `id`,
repository-relative `path`) and `claims` (the exact claim IDs bound to that test). Older
readers may ignore them, so the envelope remains `testence/1`.

Two payload fields exist because a metric was wrong without them, and both must be
honoured by anything aggregating a ledger:

- **`children` on `step.end`.** An ActionMap method composes primitives, so steps
  nest and a composite's duration *contains* its children's. Summing every
  `step.end` counted the same milliseconds twice — in one run 48 of 95 step starts
  were nested and the step total exceeded the test total, which cannot be true.
  Per-interaction latency means leaves (`children == 0`). Ledgers written before
  this field carry none; aggregate those as before rather than guessing.
- **`code` on `test.start`.** A digest of the file the test is defined in, so
  flakiness can be keyed by `(test, code)`. Without it, a case going fail → pass
  while being authored counts as flaky: a nine-case suite read 44.4 % with four
  named tests, none of which had ever flapped.

`nodeid` and `markers` are there for the reporting exporters
([ADR-0013](adr/0013-reporting-as-export.md)): a format needs the test's full address
and the suite's own taxonomy. They are the worked example of the rule above — an
integration that needs data gets a **new ledger field**, never instrumentation in
test code. Both are optional on read: ledgers written before them export with the
test name as its own address and no tags.

## Evidence pack (per failed test)

Directory `runs/<run>/<test>/pack/`, plain files so any agent can read them:

| file | content | token budget |
|---|---|---|
| `pack.json` | machine index: test, PlanSpec, claims, error, page_url, section sizes, taxonomy and verdict-template path | — |
| `TRIAGE.md` | the judge contract: taxonomy + instructions | — |
| `verdict.template.json` | `testence/verdict/1` starter with exact plan/test/claim IDs; the agent completes it as `verdict.json` | — |
| `verdict.json` | typed agent verdict after successful validation; created by the agent, not the runner | — |
| `aria.txt` | ARIA snapshot of the page at failure | 8 000 |
| `network.jsonl` | full API request ledger since test start (bodies of non-2xx, plus `failure` on aborted requests) | 8 000 |
| `console.txt` | errors/warnings/pageerrors | 2 000 |
| `oracle.json` | UI↔API diff, when an oracle fired | 2 000 |
| `heal.json` | drift proposal: new address, score, rationale, suggested edit ([ADR-0011](adr/0011-heal-as-proposal.md)) | — |
| `browser.json` | live-attach manifest: CDP endpoint, page URL | 500 |
| `screenshot.png` | for humans; agents start from text | — |
| `full-*` | untruncated originals when a budget clipped a section | — |

Budgets are enforced by truncation with an explicit `<truncated: full content in …>`
marker — an agent must always be able to tell "small" from "clipped". Token counts
are estimates (~4 bytes/token); byte sizes are recoverable from the files themselves.

## Verdict taxonomy (triage contract)

`real_bug` · `test_bug` · `behaviour_change` · `ui_change` · `flaky_timing` ·
`environment` —
definitions live in `TRIAGE.md` inside every pack (self-describing artifact).
Three hard rules: an element *gone* from the page is `real_bug`, not drift; a
proposed fix for `ui_change`/`flaky_timing` is a reviewable diff (motion), never a
runtime patch; and when every layer agrees with itself and only the test disagrees,
the PlanSpec distinguishes a `test_bug` from a real `behaviour_change` (ADR-0014).

`blocked_on` names the one thing that would settle a verdict the pack cannot settle
— usually the specification. A verdict carrying it is provisional and says so.

`testence verdict validate <pack>/verdict.json --plan <planspec> --json` checks the
schema version, exact plan/test/full-claim-set match, abstention rules, and that every
evidence reference names an existing file inside the pack. External paths and URLs are
rejected.
