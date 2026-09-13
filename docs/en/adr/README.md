# Architecture Decision Records

Every significant choice is recorded here with the alternatives that were actually
compared and a **tripwire** — a measurable condition under which the decision gets
re-evaluated. A decision without a tripwire is a belief, not a decision.

Statuses: `accepted` · `proposed (experiment pending)` · `superseded by ADR-XXXX`.

| # | Decision | Status |
|---|----------|--------|
| [0001](0001-execution-engine.md) | Playwright-over-CDP as execution engine, behind a facade | accepted |
| [0002](0002-core-language.md) | Python for the framework core | accepted (E1 measured) |
| [0003](0003-evidence-format.md) | Own versioned run.jsonl as the source of truth | accepted |
| [0004](0004-dom-representation.md) | ARIA snapshot as the DOM evidence format | proposed (E2 pending) |
| [0005](0005-html-report.md) | Self-contained single-file HTML report | accepted |
| [0006](0006-no-llm-in-runner.md) | No LLM in the execution path; vendor-neutral contracts | accepted |
| [0007](0007-licensing-and-dependencies.md) | Apache-2.0; permissive-only dependencies | accepted |
| [0008](0008-headed-shared-browser.md) | Headed Chrome with open CDP port as shared substrate | accepted |
| [0009](0009-kernel-boundary.md) | Compute-kernel boundary for future native (Rust) backends | accepted (seam only — no kernel justifies Rust yet) |
| [0010](0010-modular-authentication.md) | Modular auth; browser form login as default; config-driven targets | accepted |
| [0011](0011-heal-as-proposal.md) | Self-healing as a reviewable proposal, never a runtime rebind | accepted (measured on the corpus) |
| [0012](0012-parallel-execution.md) | Parallel execution by process shard, with shard-safe evidence and seeding | accepted |
| [0013](0013-reporting-as-export.md) | Reporting integrations as exporters from the ledger (Allure, CTRF, JUnit) | accepted (seam implemented) |
| [0014](0014-verdict-taxonomy.md) | Behaviour-change and test-bug verdicts; `blocked_on` as the abstention channel | accepted |
| [0015](0015-agent-native-interface.md) | Portable agent control plane over a deterministic verification runner | proposed (golden path pending) |
| [0016](0016-plan-verdict-contracts.md) | PlanSpec and verdict as versioned proof contracts | superseded by 0019 |
| [0017](0017-event-driven-spa-latency.md) | Event-driven SPA readiness, mutation waits and input fast path | accepted (measured) |
| [0018](0018-warm-authoring-runner.md) | Warm pytest process for the authoring loop | accepted (measured, opt-in) |
| [0019](0019-identity-and-schema-v2.md) | Stable identity and schema v2 migration | accepted |
| [0020](0020-application-cli-contract.md) | Explicit, manifest-backed onboarding and submission CLI | accepted |
| [0021](0021-isolated-runtime-ownership.md) | Per-test state isolation and explicit browser ownership | accepted |
| [0022](0022-engine-capability-negotiation.md) | Versioned engine capabilities and strict action preflight | accepted |

| [0023](0023-visual-baseline-proof.md) | Digest-pinned visual assertions and installed-client simulation | implemented (engineering) |

Format: Context → Options compared → Decision → Consequences → Tripwire.
Metric names are defined alongside their implementation and benchmark documentation.
