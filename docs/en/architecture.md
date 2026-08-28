# Architecture

```
 Claude Code · Codex/ChatGPT · OpenCode · other coding agents
                           │
       project instructions · Agent Skills · typed CLI/MCP
                           │
                           ▼
        PlanSpec ──► deterministic tests ──► typed verdict/proposal
                           │                          ▲
                           ▼                          │
               Testence runner (pytest/DSL)           │
               Playwright over CDP, auto-wait        │
                           │                          │
                           ▼                          │
             run.jsonl (schema testence/1) ──► evidence pack
                    │              │
               HTML/Allure       metrics
```

## Product planes

The **agent control plane** turns human intent into plans, test code, verdicts and
maintenance proposals. It is taught through portable skills and repository instructions;
CLI/MCP exposes bounded operations. This plane may use an LLM and must remain replaceable.

The **deterministic verification plane** owns browser execution, API oracles and the
event ledger. It never relies on a model call during ordinary replay. This is the source
of truth for what ran and what passed.

The **trust and governance plane** spans both: traceability IDs, schemas, redaction,
retention, permissions, proposal review and provenance. Agent output becomes trusted only
after it crosses one of these explicit contracts.

See [agent-workflow.md](agent-workflow.md) for the target public lifecycle and
[product-positioning.md](product-positioning.md) for the product boundary.

## Layers (dependency direction: top depends on bottom, never sideways-up)

| layer | module | responsibility | may import |
|---|---|---|---|
| test cases | project repo | 5–15 intent-bearing DSL lines each | project ActionMap |
| ActionMap | project repo | app steps, selectors, product-trap workarounds, oracles | `testence.dsl`, `testence.oracle`, adapters |
| DSL | `testence.dsl` | step wrapper: intent + timing + fingerprint + events | `testence.engine`, `testence.evidence` |
| adapters | `testence.adapters` | Auth/Seed contracts (implemented per project) | `testence.engine` |
| triage | `testence.triage` | pack assembly, verdict taxonomy contract | engine, evidence |
| engine | `testence.engine` | the ONLY module that imports Playwright | playwright |
| evidence | `testence.evidence` | run.jsonl writer, schema, budgets | kernels, stdlib |
| views | `testence.report`, `testence.metrics`, `testence.cli` | renders over the ledger | evidence, kernels |
| kernels | `testence.kernels` | pure CPU functions behind a versioned ABI; swappable for a native backend | stdlib only |

Rules that keep the facade honest:
- Nothing outside `testence/engine/` imports Playwright or handles its types
  (`Target`/`NetRecord` are ours). Checked in review; lint rule when the repo grows.
- DSL code never sleeps — waiting belongs to the engine (auto-wait) or to explicit
  `expect_*` conditions.
- Everything the run learns goes through `EvidenceWriter`; no side-channel logs.
- CPU-heavy pure functions live in `testence.kernels` (plain data in/out, no I/O)
  so they stay mechanically portable to a native backend — see
  [kernels.md](kernels.md). I/O-bound code (the writer, the engine) never does.

Inside the verification plane there are two performance profiles. The **driving path**
(engine/DSL/pytest) is
I/O-bound — a step waits on a CDP round-trip, so language choice is irrelevant
there; the **analysis path** (ledger parsing, snapshot diffs, candidate scoring) is
CPU-bound and lives behind the kernel ABI. Optimization effort belongs in the second
path only, and only when `bench/kernels.py` says a threshold was crossed.

## Execution flow (one test)

1. `ex` fixture: reset capture buffers → `test.start`.
2. Each `Actions` call: `step.start` (intent, target) → engine action (auto-wait) →
   `step.end` (duration, fingerprint on green).
3. Oracle points: `save_and_verify`-style checks emit `oracle` events; divergence
   raises and fails the step.
4. On failure: `assemble_pack` captures aria/network/console/oracle + `browser.json`,
   emits `pack`, `test.end(fail)`; session keeps the browser alive (ADR-0008).
5. On green: `test.end(pass)` — the ledger stays compact by design.

## Modes

| mode | how | use |
|---|---|---|
| local full stack | engine launches system Chrome | development, fastest loop |
| existing-browser attach | `--testence-cdp http://127.0.0.1:9222` to a Chrome the developer logged into | local investigation against shared environments |
| CI | headed under `xvfb-run`, artifacts `when: always`, triage from packs only | regression, zero LLM cost |

## Implementation boundary

| capability | state |
|---|---|
| pytest/DSL/Playwright execution | implemented |
| per-test evidence isolation and xdist execution | implemented |
| versioned ledger, bounded packs and HTML reports | implemented |
| Allure and CTRF export from the ledger | implemented |
| fingerprint-based heal proposal primitives | implemented |
| portable agent skills and project bootstrap | to build |
| PlanSpec and claim-to-run traceability | to build |
| agent-facing typed verdict and CLI/MCP surface | to build |
| systematic evidence redaction and repository permission policy | P0 blocker |
| intent cache or model-driven authoring escape hatch | later, explicit opt-in |

The architecture is not complete merely because the runner works. Public-alpha readiness
requires a supported coding agent to traverse the full workflow while every transition
remains inspectable.
