# ADR-0016: PlanSpec and verdict as versioned proof contracts

Status: superseded by ADR-0019 (the `/1` contract remains a compatibility input)

## Context

An agent-first workflow must preserve requirement meaning across clients and runs. A
prose plan is readable but cannot let pytest validate claim coverage. A marker alone does
not retain product context or scenarios. An unstructured triage answer cannot be safely
bound to one PlanSpec, test and evidence pack.

At the same time, ADR-0006 requires the execution path to remain provider-neutral and
free of LLM or JSON-Schema SDK dependencies.

## Options compared

1. YAML front matter plus free-form Markdown sections.
2. Standalone JSON/YAML files with no human document.
3. Markdown containing one fenced JSON block, with standalone JSON also accepted.
4. Store claims only in Python decorators/markers.
5. Accept a free-text verdict and extract structure after the model responds.

## Decision

Choose option 3 for PlanSpec and strict JSON for verdicts.

- A PlanSpec contains exactly one `testence-planspec` block with schema
  `testence/planspec/1`; surrounding Markdown remains human context.
- A public JSON Schema draft 2020-12 ships in the wheel. The runtime validator uses the
  standard library and additionally enforces cross-object invariants: unique IDs,
  required-claim coverage and scenario references.
- The pytest marker `testence(plan=..., claims=[...])` binds a test to a
  repository-relative PlanSpec. Collection rejects external paths and unknown claims.
- The evidence writer attaches `plan` and `claims` to every bound-test event. The same
  fields reach the pack index, exporter model and HTML report.
- A failure pack creates `verdict.template.json`. The agent saves a completed
  `testence/verdict/1` as `verdict.json`; validation requires an exact plan, test and
  full-claim-set match plus evidence files that exist inside the pack.
- Abstention is data: `verdict: null` is valid only with non-empty `blocked_on`. The
  runner produces evidence and a template but never makes a model judgment.

## Consequences

- A claim ID is the stable join key across requirement, source, ledger, pack, report and
  agent decision.
- The contract is identical for Codex/ChatGPT, Claude Code, OpenCode, CLI and future MCP.
- JSON inside Markdown is more verbose than YAML, but it adds no runtime dependency,
  parses unambiguously and matches tool transport formats.
- Changing required fields or semantics requires a new schema version; additive optional
  ledger fields remain compatible with `testence/1`.
- Verdict persistence/signing and policy approvals remain a separate next layer.

## Tripwire

Revisit the PlanSpec representation if, across at least 30 golden-path tasks, more than
10% cannot express critical context without duplicating it in prose, or median time to
repair schema errors exceeds two minutes. Revisit marker binding if any accepted test in
a corpus of 1,000 bound runs loses its plan or claim in the ledger, pack or report.
