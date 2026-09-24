# Evidence schema `testence/2` (normative)

One JSON object per line in `runs/<run-id>/run.jsonl`. Append-only; UTF-8; `\n` line
endings on all platforms; fsync per event (crash-safety is the point, and it costs
0.5 ms per event). Fields are append-only within a major version; breaking changes
bump the version and parsers must refuse foreign versions loudly.

The fsync guarantee is the operating system's. On macOS `fsync` hands the data to the
drive but does not flush the drive's own write cache, which needs `F_FULLFSYNC` and
costs orders of magnitude more. A crashed or killed process loses nothing there either;
a power loss can drop the last events. Testence keeps plain `fsync` on every platform
rather than trade the per-event budget for that case.

**One file per process, never per run.** Under `pytest -n` each worker writes
`run-<worker>.jsonl` beside the controller's `run.jsonl`, all inside one run
directory named by `TESTENCE_RUN_ID`. Not a preference: four processes appending to
one file lost 27 % of their events and produced torn lines, because the writer's
lock is a `threading.Lock` and means nothing between processes (ADR-0012).

**Readers must merge, and must not trust `seq` across files.** `seq` restarts per
process, so it orders events within one ledger and nothing more. Raw files can contain
one `run.start`/`run.end` per surviving process. Read through
`testence.metrics.load_run`: it merges by timestamp, normalizes legacy statuses,
reconciles collection inventory with terminal events and exposes one logical
`run.end`. A started case without a terminal becomes `aborted`; a selected case that
was never started becomes `not_run`.

The controller also maintains `runs/<run>/manifest.json` with schema
`testence/run-manifest/2`. It is replaced atomically after `run.start`,
`collection.end`, and `run.end`; the complete checkpoint binds project/run identity,
selected scope, exit status, and every ledger shard by relative name, byte size, and
SHA-256. Readers retain complete JSONL records before an unterminated tail, but mark
the logical run `incomplete`. Empty or missing ledgers, a running or mismatched
manifest, mixed identities, duplicate event IDs, and duplicate terminal events also
produce an explicit `ledger.damage` projection and cannot become a successful run.
Corruption inside a newline-terminated record and unknown schema majors are rejected
because no safe prefix interpretation exists. Legacy `/1` runs without a manifest
remain readable with unverified assurance.

## Envelope (every event)

| field | type | meaning |
|---|---|---|
| `v` | string | schema version, `"testence/2"` |
| `project_id` | string | repo-owned namespace, independent of checkout path |
| `run_id` | string | run id (`r-YYYYMMDD-HHMMSS-xxxxxx`), shared by all workers |
| `run` | string | compatibility alias for `run_id`; deprecated for new consumers |
| `worker` | string | process/shard identity, or `controller` |
| `event_id` | string | unique `<worker>:<seq>` identity within the run |
| `seq` | int | monotonic **per process**, starts at 1 |
| `ts` | string | UTC ISO-8601, ms precision, `Z` suffix — the only cross-file order |
| `kind` | string | event kind, see below |
| `test` | string? | test id; absent on run-level events |

Every test event also carries `case_id`, `variant_id`, `attempt_id`, `proof_id` and
digest-only `parameters`. The full pytest `nodeid` remains the source locator. A
PlanSpec scenario ID is the explicit logical case ID; without a PlanSpec, Testence uses
a deterministic source-derived fallback that does not promise stability across rename.

## Kinds and payloads

| kind | payload fields |
|---|---|
| `run.start` | `testence` (version), `fingerprint` {os, python, base_url, attach, worker}, optional `redaction` (`testence/redaction-policy/1`: `keys`, `allow_keys`, `url_params`, `pii` — names only) |
| `run.end` | `duration_ms`, `exit_code`, `run_status`, counts for `passed`/`failed`/`broken`/`skipped`/`aborted`/`not_run` |
| `test.start` | `display_name`, `file`, `code` (12-hex digest of the test file), `nodeid`, `markers`, optional PlanSpec `owner`, scenario `risk`, `requirements` and `issues` |
| `test.phase` | `nodeid`, `display_name`, `phase`, pytest phase status, duration, optional error/xfail/xpass metadata |
| `test.end` | `nodeid`, `display_name`, canonical `status` (`passed`/`failed`/`broken`/`skipped`/`aborted`/`not_run`), `phase`, `duration_ms`, optional `pack`/error/xfail/xpass metadata |
| `test.waits` | `waited_ms`, `ops` (count), `by_op` {op: {ms, n}}, `top` (5 slowest) |
| `step.start` | `step` (id), `intent` (human sentence), `target`? (described), `depth` |
| `step.end` | `step`, `status`, `duration_ms`, `depth`, `children`, `fingerprint`? (green runs), `error`? |
| `net` | reserved (v0 captures network into packs; inline events may follow E4) |
| `console` | reserved (same) |
| `oracle` | `name`, `ok`, `diff`?, or typed `expected`/`actual` plus `observation` and bound `operation` |
| `assertion` | `assertion_id`, `claim_id`, `oracle_kind`, `outcome`, typed/redacted `expected` and `actual`, `source` |
| `pack` | `dir` (rel.), `sections_est_tokens` {aria, network, console, oracle}, `error` |
| `note` | `text` + free fields |
| `ledger.damage` | reader-created `integrity_code`, `error`, optional shard `path`; raw ledgers remain unchanged |

## Execution and assurance

Pytest execution status and proof assurance are separate axes. Reconciliation adds
`assurance` to each logical `test.end`: `verified`, `violated`, `inconclusive`, or
`unverified`. A passing test is `verified` only when its bound PlanSpec has a required
assertion inventory, every required assertion ran exactly once and passed, assertion
claim/oracle bindings match, and plan/test/policy SHA-256 digests are current. A plain
`pass`, a missing branch, duplicate or unknown assertion, or stale digest remains
`unverified`. An unavailable oracle is `inconclusive`; a failed assertion is
`violated`. This projection never rewrites immutable pytest status. Optional assertions
do not increase the required denominator.

Expected-state observations record their classification, reason, read count and elapsed
time. A bound operation records method/path, correlation or GraphQL identity, response
status and matching request count. Reconciliation consumes the emitted assertion
outcome; polling never rewrites or repeats the mutation.

When a pytest test is bound to a PlanSpec through the `testence` marker, the writer
additively attaches `plan` (`schema`, `id`, repository-relative `path`, SHA-256 digest),
`claims`, and the assertion inventory. `test.start` also binds the full test source and
assurance-policy digests. Older
readers may ignore them. This identity change belongs to `testence/2`; it is not added
retroactively to `/1`.

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

The envelope `test` key on new lifecycle events is the full pytest nodeid;
`display_name` remains the short human label. Legacy `pass`/`fail` events normalize to
`passed`/`failed`. `nodeid` and `markers` are there for the reporting exporters
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
| `manifest.json` | `testence/pack-manifest/2`: identity plus relative path, byte size and SHA-256 for every captured artifact | — |
| `TRIAGE.md` | the judge contract: taxonomy + instructions | — |
| `verdict.template.json` | `testence/verdict/2` starter with exact project/case/variant/attempt/run/proof and plan/test/claim IDs | — |
| `verdict.json` | typed agent verdict after successful validation; created by the agent, not the runner | — |
| `aria.txt` | ARIA snapshot of the page at failure | 8 000 |
| `network.jsonl` | full API request ledger since test start (bodies of non-2xx, plus `failure` on aborted requests) | 8 000 |
| `console.txt` | errors/warnings/pageerrors | 2 000 |
| `oracle.json` | UI↔API diff, when an oracle fired | 2 000 |
| `heal.json` | drift proposal: new address, score, rationale, suggested edit ([ADR-0011](adr/0011-heal-as-proposal.md)) | — |
| `browser.json` | live-attach manifest: CDP endpoint, page URL | 500 |
| `screenshot.png` | for humans; agents start from text | — |
| `full-*` | sanitized extended content when a budget clipped a section; capped at 262,144 characters | — |

Budgets are enforced by truncation with an explicit `<truncated: full content in …>`
marker — an agent must always be able to tell "small" from "clipped". Token counts
are estimates (~4 bytes/token); byte sizes are recoverable from the files themselves.

Sanitization happens before the ledger or pack text is written. Structured credential
keys (Authorization, cookies, passwords, tokens and API/private keys), Bearer/Basic
values, secret query parameters and the configured Testence username/password are
replaced with `<redacted>`. Ledger strings are capped at 16,384 characters. The
manifest contains only filenames relative to its pack; it intentionally excludes its
own hash. Screenshots remain visual captures and may contain application data, so the
alpha-candidate production-data restriction still applies until visual masking and the full
T12 security review are complete.

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
schema version, exact plan/test/full-claim-set match, abstention rules, and the four
immutable bindings copied from the template: `plan_digest`, `test_digest`,
`policy_digest`, and `pack_digest`. The pack digest covers the exact bytes of the
immutable manifest; that manifest in turn covers `pack.json` and every captured
artifact by byte size and SHA-256. Editable `verdict.*` files are deliberately outside
the manifest to avoid a circular digest.

Every evidence reference must name a manifested file inside the pack. A fragment on a
JSON or JSONL reference is resolved as an RFC 6901 JSON Pointer, including `~0` and
`~1` decoding. A missing pointer, modified artifact, unmanifested file, stale digest,
cross-attempt event, external path, or URL makes validation fail closed.

## Bound repair proposal

`testence/repair-proposal/1` binds a proposed source diff to the validated verdict,
PlanSpec semantics, and exact source base. Run:

```bash
testence repair validate repair.json --verdict <pack>/verdict.json \
  --plan specs/<feature>.md --base tests/<test>.py \
  --pack <pack> --evidence-root <proof-root> --json
```

Only `ui_change`, `flaky_timing`, and `test_bug` authorize locator, timing, and test
implementation repairs respectively. A proposal cannot change claims and must retain
the protected plan digest. It must bind exactly one healthy proof (`passed` and
`verified`), one defect control (`failed` and `violated`), and one harmless control
(`passed` and `verified`). The validator rejects a stale source base or missing proof
artifact before a patch can be treated as reviewable.

## `/1` compatibility

Readers accept `testence/1`, normalize legacy status spellings and retain unknown
fields. Missing identity and proof are marked `legacy`/`unknown` and assurance remains
`unverified`; the adapter never invents successful proof. Writers emit only `/2`.
Unknown evidence majors fail loudly before a report or quality result is produced.
