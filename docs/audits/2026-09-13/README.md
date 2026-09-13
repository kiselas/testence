# Consolidation and release audit — 13 September 2026

Status: engineering audit; public release acceptance remains open. The package is
still `0.1.0.dev0`. No public tag, PyPI upload or visibility change is authorized by
this audit receipt. Historical no-go manifests remain historical.

Final local suite source: `fdde5aee5ea93826df4fab247951cf658046634c`.
**404 tests passed, 2 skipped; all 48 external UI cases matched expectations.**
The two local skips require Windows symlink privileges unavailable on this host.
The same final source passed all eight [hosted CI jobs](https://github.com/kiselas/testence/actions/runs/34765807232),
including Linux/Windows Python 3.10/3.12 and installed-wheel browser checks.
The external UI receipt names its separately tested source `2493f81`.
The external cases produced 42 verified results and 6 expected violations, with no
integrity errors. See [validation.json](validation.json), [OSS samples](oss-result.json),
[reproducible build](build.json) and [isolated wheel smoke](wheel-smoke.json).
Receipts name the exact source revision tested; later fixes and hosted validation
are recorded separately rather than retroactively changing those receipts.

## Integration

Consolidated `codex/r1-rc` and all three fetched Dependabot branches into `main`,
preserving their commit ancestry. The dependency changes update setup-uv, the Node
Playwright comparison and the React/Vite benchmark toolchain. npm installation and
production React build succeeded. Branch refs are retained as history; there is one
development line. See Git history for source commits and subsequent audit receipts.

## Findings and changes

1. **Windows onboarding flake, fixed.** Full suite reproduced WinError 145 when
   removing a completed quality transaction. The CLI reported failure despite the
   managed write having committed. Cleanup now retries only Windows sharing and
   directory-not-empty errors, at most four attempts (150 ms total backoff), with
   path validation on each attempt. It does not retry transactions or user actions.
   Regression checks cover transient cleanup and propagation of other errors.
2. **Agent entry points missing, fixed.** Added root AGENTS.md and a thin CLAUDE.md.
   Portable skill pack 0.1.1 includes visual observation, state assertions, negative
   controls, measurement boundaries and a file-based handoff. Canonical assets ship
   inside the wheel; no personal agent memory is required.
3. **Stale capability and acceptance wording, fixed.** English/Russian workflow
   now distinguishes implemented bootstrap/verdict/redaction mechanisms from
   outstanding independent acceptance. Real Claude/Codex client trials are not
   claimed on the strength of an installer test.
4. **External UI coverage absent, added.** Pinned AdminLTE and Tabler, built Tabler,
   inspected screenshots plus accessible state, authored four plan-bound UI cases,
   and added a repeatable healthy/defect/restored/restyle runner. Full upstream
   sources/assets remain ignored. See [corpus instructions](../../../bench/oss/README.md).
5. **Environment issue, isolated.** The first test command hit an inaccessible
   system pytest temp directory. Using a unique repository-local basetemp resolves
   it; this is documented without changing the user's system permissions.

## Validation evidence

An initial repeated external-panel run hit the 120-second process deadline during
browser setup. This is retained as a failed environment attempt, not counted as a
successful repeat. The harness now uses ephemeral CDP ports and retains timeout
records, logs and checkpoints instead of losing the whole result. The cause of the
original startup hang is not established; subsequent successful samples do not
erase it. A regression test proves timeout recording and nonzero exit without retries.

Follow-up inspection found that the engine factory treated explicit `debug_port=0`
as false and silently replaced it with 9222. It now preserves zero, including under
xdist; fixed ports still receive worker offsets. This removes a concrete port
collision risk, without claiming it proves the cause of the earlier timeout.
Hosted Windows/Python 3.12 also caught a crash-test race: terminating the venv
launcher could leave the real Python worker holding the quality lock. The test now
records and terminates the actual worker PID. No production lock exclusion is weakened.

Hosted Windows/Python 3.10 subsequently caught a too-short 150 ms navigation budget
in the new UI regression fixture. Navigation now uses 10 seconds, while only the
deliberately missing assertion uses 150 ms; fixture cleanup includes setup failures.
The default application timeout and proof expectations were not relaxed.

The legacy collection run completed 36 expected outcomes, then stalled during
another browser setup. Its partial results and interrupted attempt remain in
[legacy-corpus-partial.json](legacy-corpus-partial.json); this is not a clean full
corpus receipt. Resuming with `TESTENCE_DEBUG_PORT=0` exposed two more problems:
the config loader rejected zero despite the factory supporting it, and the legacy
runner returned exit 0 even with incomplete cases. Both are fixed and regression
tested. The initial 15 rejected-config attempts are retained locally. Any later
successful continuation does not erase the interrupted or rejected attempts.

The resumed slow-response control then exposed a false red in the collection
specification: a strict single-element hidden wait matched ten skeleton rows.
`loaded()` now waits until no skeleton rows remain. A browser regression exercises
ten transient placeholders and ten persistent placeholders; the latter must still
fail. This changes the corpus readiness check, not the product or its expected state.

Post-fix live checks: the slow-response control passed all three repeats, and the
persistent-placeholder defect still failed for its expected claim. Preserve the
distinction between [the failed control run](legacy-controls-before-fix.json),
[the corrected control](slow-control-fixed.json) and
[the persistent defect](persistent-placeholders.json). These are engineering
follow-ups, not a single pristine 51-case acceptance run.

The first external trial exposed another authoring gap: UI assertions could pass
while assurance remained unverified because they emitted no bound assertion event.
`expect_visible` now optionally accepts assertion/claim IDs, records observed
visibility, and distinguishes unmet visibility from unavailable browser evidence.
The external suite now gates on verified/violated assurance and integrity as well
as expected pytest outcomes. Transport errors remain inconclusive. Other custom
engines should raise AssertionError for unmet visibility and another exception for
unavailable evidence, as documented in the engine protocol.

Local bundles live in ignored `outputs/release-audit-20260913/`. Compact, sanitized
JSON snapshots are kept next to this document as they complete. They disclose
revision and dirty state where the harness supports it. Build/authoring time is not
replay time; local engineering results do not satisfy hosted or independent gates.

Initial full run: 390 passed, 2 skipped, one Windows cleanup failure. The focused
cleanup/application regression run passed 21 tests. A later skills-version assertion
was updated from 0.1.0 to 0.1.1 and the six skill tests passed. Final candidate
results are recorded in the accompanying validation receipt.

Three-sample local Windows/Python 3.13.11/Playwright 1.62.0 measurements:

| Profile | Observed median | Gate |
|---|---:|---|
| Fresh React pytest process | 2,806.51 ms | existing latency budget passed |
| Controlled input, safe path | 14.35 ms | existing latency budget passed |
| React mutation round trip | 74.4 ms | existing latency budget passed |
| 10,000-result export, cold | 408.48 ms | existing scale budget passed |
| 1,000-failure storm | 94.15 ms | existing scale budget passed |

The scale output hashes are identical across samples. This machine is not the
specified reference host. Three samples are insufficient for a robust tail-latency
claim. External-panel raw timings and exact expected failures are in oss-result.json.

External four-case replay median: healthy 9,712.1 ms; defect 15,681.2 ms; restored
10,305.8 ms; harmless restyle 9,936.1 ms (three fresh processes per phase). Other
audit processes ran concurrently, so these are local engineering samples. The
updated Node Playwright comparison also ran successfully; its
[snapshot](competitive-replay.json) is retained without a performance superiority claim.

Manual screenshots were inspected at 1440×1000 and 390×844. The two sampled mobile
pages had document width 390 px, matching the viewport, and their form cards stacked
without observed horizontal clipping. This is a sampled observation, not automated
responsive acceptance; see [mobile inspection](mobile-inspection.json).

The packaged triage skill was exercised on a real bound checkbox failure pack.
Its verdict validated and was submitted through the CLI:
[triage receipt](triage-receipt.json). The initial out-of-pack submission path was
correctly refused; submission then used an allowed path within the same pack.
The verdict is `real_bug` for the locally injected defect, not a defect report about
unmodified upstream AdminLTE. No test repair is appropriate for that verdict.

## Remaining product and release work

- **Visual scope:** screenshot-guided authoring and semantic replay are supported;
  these four tests do not provide autonomous pixel-level visual regression,
  responsive coverage or a complete accessibility audit. Add viewport/state cases
  and explicit visual oracles before claiming those capabilities.
- **DSL ergonomics:** the external cases use CSS state predicates for checked and
  input masking assertions. Native checked/value/enabled assertions would make
  authoring more natural while preserving exact state checks.
- **Healing hint precision:** the checked-state failure produced a high-confidence
  `ui_change` hint for the still-present unchecked checkbox. The validated triage
  verdict rejected that hint. A state predicate is part of the claim, not an address
  to weaken; hints must remain advisory. Add dedicated state-predicate controls to
  the heuristic corpus before presenting hint confidence as classification quality.
- **Corpus depth:** two templates and four UI claims cannot satisfy the existing
  R1 frozen/holdout corpus requirements or prove real authentication/persistence.
  Add backend-driven apps, delayed and concurrent changes, modal/table workflows,
  and independent expected-state oracles. Preserve the existing freeze.
- **External infrastructure/people:** real client receipts, TestOps acceptance,
  independent truth/security/rights reviews and pilot/return-week evidence remain
  governed by [Stage 3](../../stages/03-r1-release/readiness.md). Do not fabricate them
  or replace them with more local agents. Reference-host measurement remains deferred.
- **Publication:** hosted engineering validation and immutable distributions are
  available. A publishable version still needs the complete acceptance manifest,
  required signing and owner release decision before publication.
  The positioning is “agent-first browser testing with evidence-backed verdicts”;
  historical primacy (“the first”) has not been established by this audit.

## Resume without this conversation

Read root AGENTS.md, the relevant packaged skill, then bench/oss/README.md. Run the
same pinned targets into a new output directory. Inspect any failed expected claim
in its `runs/<run-id>/.../pack`, validate the verdict, and preserve both source and
proof diffs. The next expansion is backend-driven negative cases and responsive
visual observations, followed by the real external acceptance receipts above.
