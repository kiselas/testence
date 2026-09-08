# Project audit

Historical snapshot. See the [2026-09-06 audit](../audits/2026-09-06/audit.md) for current verified findings and the [proposed release specification](../audits/2026-09-06/release-spec.md).

Snapshot: 2026-08-28.

## Verdict

Testence is a **credible pre-alpha engineering foundation**, not yet a consumable
open-source product. Its architecture is more mature than its release surface: the
seams, evidence model, ADR discipline and synthetic correctness corpus show senior-level
systems thinking, while installation, security hardening, browser breadth and the actual
agent workflow are still early.

Approximate maturity:

| Dimension | Rating | Rationale |
|---|---:|---|
| Architecture | 4/5 | Clear execution/analysis split, engine protocol, versioned ledger, plugin-oriented exporters/auth and documented decisions |
| Test engineering | 3.5/5 | 121 framework tests, golden exporter checks and a defect/control corpus; scenario breadth remains narrow |
| Runtime performance | 4/5 | Thin Playwright path, reuse over CDP and no LLM in replay; public numbers are promising but synthetic |
| Security/privacy | 1.5/5 | Secrets stay out of config, but evidence bodies and cached sessions need systematic redaction and protection |
| Developer experience | 2/5 | Pytest-native DSL and examples exist; setup diagnostics, recorder/agent loop, packaging polish and migration policy do not |
| OSS readiness | 2/5 | Apache-2.0 and product-neutral docs are present; CI, contribution policy, security policy, release automation and external validation are missing |
| Product maturity | 1.5/5 | The agent-native verification contract is now explicit, but its end-to-end product experience has not been shipped |

Overall: **2.5/5 — advanced prototype / pre-alpha**.

## Evidence behind the assessment

- 33 Python source files and roughly 4,000 source lines.
- 15 test files and roughly 1,460 test lines.
- 121 unit/integration-style framework tests pass on the inspected machine both
  serially and with four xdist workers (`--dist loadfile`; 22.86 s for the parallel
  run).
- The runner, DSL, auth, API oracle, evidence, triage, report/export and kernel seams are
  already separated.
- The checked-in benchmark measures Python and Node Playwright on the same synthetic
  workload. Their instant-step medians are close (10.28 ms vs 9.43 ms), suggesting the
  Python facade adds little compared with browser work.
- A separate six-step synthetic comparison measured 0.353 s for deterministic replay
  versus 70.6 s for interactive agent clicking. The reported 200× ratio is a per-step
  experiment, not a promised real-suite speed-up.

## Strong technical decisions

- Keep Playwright behind a protocol rather than expose it as the public API.
- Keep model calls out of deterministic execution.
- Preserve an append-only event ledger and derive reports/export formats from it.
- Carry intent and fingerprints through UI actions so repairs can be reasoned about.
- Use same-session API observations to catch plausible-looking UI false greens.
- Benchmark harmless controls as well as seeded defects.

## Highest risks

1. **Evidence leakage.** Captured URLs and request/response bodies can contain tokens,
   personal data or application secrets. This blocks responsible use on real sensitive
   systems.
2. **Positioning outruns implementation.** "Agent-native UI verification" is now a
   concrete workflow contract, but Testence does not yet ship the bootstrap, PlanSpec,
   portable skills or typed agent interface needed to deliver it. Playwright already
   ships concrete planner/generator/healer definitions.
3. **One-path validation.** The strongest path is an existing Chromium browser over CDP.
   Cross-browser compatibility and browser ownership are not yet demonstrated.
4. **Quality debt.** The test suite is green, but the current broad Ruff configuration
   reports 72 findings (42 automatically fixable), and mypy reports 12 errors in two
   source files. This makes public contribution and API evolution riskier.
5. **Benchmark over-interpretation.** The mechanism is plausibly fast, but current results
   do not establish suite-level superiority on realistic public applications.

## Release recommendation

Do not present the next release as production-ready. Publish only after the P0 release
gates in the roadmap are met, label it `0.1.0a1`, and frame it as an invitation to test
the deterministic/evidence-first thesis on real open applications.
