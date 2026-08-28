# ADR-0006: No LLM in the execution path; vendor-neutral agent contracts

Status: accepted (2026-08-25)

## Context

Every surveyed AI test framework (Stagehand, Midscene, Shortest, Skyvern) puts a
model in the execution loop: tests are natural-language prompts, code is a cache.
That buys authoring UX and costs CI determinism, per-run money, and vendor coupling.
Testence's premise is the inverse: **agents author and judge; the machine executes.**

## Decision

1. The runner makes zero LLM calls. No model SDKs in runtime dependencies.
   Re-running a suite costs `llm_cost_per_ci_run_usd = 0` *by construction* —
   audited per release by checking the dependency tree and the absence of network
   calls to model providers.
2. Agent-facing surfaces are **contracts, not integrations**: the evidence pack is
   plain files + `pack.json`; the triage taxonomy and instructions ship as
   `TRIAGE.md` inside every pack; authoring conventions are docs/skills. Any agent
   that can read files can be the judge. Claude Code skills ship in `skills/` as the
   first-class integration — an integration, not a dependency.
3. The future `ai_step()` escape hatch (agent executes a step once, the result is
   materialized into code — the Stagehand cache pattern) runs at *authoring time*,
   never inside CI execution.

## Options rejected

- LLM-in-the-loop execution (Shortest model): ~114K tokens/test via interactive
  MCPs vs ~27K scripted (Currents, 2026); nondeterministic CI; per-run cost.
- Anthropic SDK in the core: hard vendor coupling contradicts the OSS trajectory;
  the integration belongs in skills/docs, not in the runner.

## Consequences

- CI needs no model API keys — adoptable in restricted environments.
- Verdict quality depends on evidence quality, which is measurable and improvable
  (E2–E4 ablations) instead of hidden in a vendor's agent loop.

## Verification (per release)

- Dependency audit: no `anthropic`/`openai`/model SDKs in the runtime tree.
- E6: the triage contract is exercised with a second, non-Claude model on a corpus
  subset; contract fixes (not model swaps) close any gap found.
