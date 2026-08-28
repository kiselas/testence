# ADR-0015: Agent-native control plane over a deterministic runner

Status: proposed (golden path pending, 2026-08-28)

## Context

Testence is intended to be operated primarily by coding agents in Claude Code,
Codex/ChatGPT, OpenCode and similar clients. A pytest API and failure report alone do not
form an agent product: the agent also needs to know when to plan, how to prove generated
tests, which evidence to inspect and when a source change requires review.

Putting one model SDK in the framework would contradict ADR-0006. Exposing every internal
function as an MCP tool would couple the public interface to implementation details.
Keeping the workflow only in prose would make outcomes depend on chat context and client.

## Options compared

1. Build and host a proprietary Testence agent.
2. Ship separate first-class integrations for every coding-agent client.
3. Define one portable workflow using Agent Skills and repository instructions, backed by
   stable CLI contracts and an optional thin MCP facade.
4. Keep Testence runner-only and leave every user to prompt their agent independently.

## Decision

Choose option 3.

Testence has three product planes:

- an agent control plane for planning, authoring, triage and maintenance proposals;
- a deterministic verification plane for browser execution, API oracles and the ledger;
- a trust/governance plane for schemas, provenance, redaction, permissions and review.

Agent Skills define workflow and ordering. Repository instructions provide the small
always-on activation rule. Stable, task-oriented CLI operations perform work and return
structured artifacts. MCP may expose those same application contracts but must not become
a second implementation. Client adapters remain thin and contain no product logic.

Every phase materializes an inspectable artifact. Accepted tests are ordinary
deterministic source code; routine CI requires no agent. Source repair is proposed,
reviewed and proved with a targeted rerun.

## Consequences

- The primary UX is a feature/risk request to an agent, not a sequence of framework
  commands a human must memorize.
- A user can change compatible agent clients without changing tests or run artifacts.
- CLI and artifact schemas must stabilize before an MCP surface is promoted.
- Agent bootstrap, PlanSpec, traceability and verdict persistence become public-alpha
  requirements rather than optional post-alpha polish.
- A small amount of client-specific installation documentation is still necessary.

## Tripwire

Re-evaluate the portable-skill approach if two supported clients cannot complete the same
golden-path corpus task with the same PlanSpec, source and verdict schemas. Add a
client-specific capability only when the missing behavior cannot be expressed through
the shared skill, repository instructions or typed tool contract.

The decision becomes accepted when at least one supported coding agent completes the
feature request → reviewed PlanSpec → live-proved deterministic test → evidence-backed
verdict workflow from a clean installation.
