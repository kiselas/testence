# Consolidation and release audit — 13 September 2026

Status: engineering audit; public release acceptance remains open. The package is
still `0.1.0.dev0`. No public tag, PyPI upload or visibility change is authorized by
this audit receipt. Historical no-go manifests remain historical.

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

## Remaining product and release work

- **Visual scope:** screenshot-guided authoring and semantic replay are supported;
  these four tests do not provide autonomous pixel-level visual regression,
  responsive coverage or a complete accessibility audit. Add viewport/state cases
  and explicit visual oracles before claiming those capabilities.
- **DSL ergonomics:** the external cases use CSS state predicates for checked and
  input masking assertions. Native checked/value/enabled assertions would make
  authoring more natural while preserving exact state checks.
- **Corpus depth:** two templates and four UI claims cannot satisfy the existing
  R1 frozen/holdout corpus requirements or prove real authentication/persistence.
  Add backend-driven apps, delayed and concurrent changes, modal/table workflows,
  and independent expected-state oracles. Preserve the existing freeze.
- **External infrastructure/people:** real client receipts, TestOps acceptance,
  independent truth/security/rights reviews and pilot/return-week evidence remain
  governed by [Stage 3](../../stages/03-r1-release/readiness.md). Do not fabricate them
  or replace them with more local agents. Reference-host measurement remains deferred.
- **Publication:** obtain an exact-candidate hosted matrix, immutable wheel/sdist,
  complete acceptance manifest and owner release decision before publication.
  The positioning is “agent-first browser testing with evidence-backed verdicts”;
  historical primacy (“the first”) has not been established by this audit.

## Resume without this conversation

Read root AGENTS.md, the relevant packaged skill, then bench/oss/README.md. Run the
same pinned targets into a new output directory. Inspect any failed expected claim
in its `runs/<run-id>/.../pack`, validate the verdict, and preserve both source and
proof diffs. The next expansion is backend-driven negative cases and responsive
visual observations, followed by the real external acceptance receipts above.
