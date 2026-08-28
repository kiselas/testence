# Roadmap

This roadmap builds Testence as **agent-native UI verification**: a coding agent is the
primary operator, while deterministic execution, inspectable artifacts and owner-defined
policy remain the trust boundary. AI should reduce authoring and triage cost without
turning every CI action into a slow, non-deterministic model call.

## P0 — safe public alpha foundation (2–4 weeks)

### Evidence security

- Introduce one redaction pipeline for URLs, query values, cookies, authorization fields,
  form data, JSON bodies, console messages and exported artifacts.
- Default-deny body capture by content type and size; make full payload capture explicit.
- Add secret canaries and golden tests proving they never appear in ledgers, packs, HTML,
  Allure or CTRF output.
- Make cached browser sessions opt-in, permission-restricted, expiring and clearly marked
  as sensitive. Document deletion and CI behaviour.
- Add `SECURITY.md` and a threat model for evidence, CDP endpoints and retained browsers.

### Reproducible release

- Make pytest, Ruff and mypy green; pin an explicit lint rule set.
- Add CI for Windows/Linux and supported Python versions, plus editable-install and wheel
  smoke tests.
- Add build metadata, project URLs, `py.typed`, changelog/release automation and package
  installation verification in a clean environment.
- Add `CONTRIBUTING.md`, a code of conduct and a public API/schema compatibility policy.
- Add `testence doctor` for Python, browser/CDP, profile, TLS and writable-artifact checks.

### Minimum agent product

- Define versioned PlanSpec and verdict schemas with claim IDs that survive into test
  source and ledger events.
- Ship one portable Agent Skills package covering plan, author, triage and repair; keep
  client-specific instructions as thin adapters.
- Add `testence agent init` with a dry-run/file manifest, project instructions, a
  synthetic seed test and no secret copying.
- Add structured CLI operations for plan validation, scoped execution, failure-pack
  lookup and verdict validation. Their JSON contracts become the future MCP foundation.
- Define repository-owned permission policy for approved targets, seed mutations,
  evidence access and source-changing proposals.
- Prove the complete golden path in at least one coding agent: request → reviewed plan →
  generated deterministic test → live proof → evidence-backed verdict.

### Honest benchmark

- Make the synthetic SUT/corpus one-command reproducible in CI.
- Record browser, OS, hardware, corpus revision, repetitions and confidence intervals.
- Publish false-green, false-red and right-reason results beside latency; never extrapolate
  the current 200× per-step experiment into a suite-level claim.

**Gate for `0.1.0a1`:** sanitized tree, redaction tests, green quality gates, clean wheel
install, public benchmark command and one agent-operated end-to-end local example. The
agent may use the CLI directly; an MCP server is not required for this gate.

## P1 — make the agent loop portable and complete (4–8 weeks)

### Multi-client agent experience

- Validate the same portable skills in Codex/ChatGPT, Claude Code and OpenCode; publish
  thin setup adapters only where their discovery conventions differ.
- Add an optional MCP server over the stable CLI/application contracts. Keep tools
  narrow and task-oriented; do not expose every internal helper.
- Complete planner → plan review → controlled discovery → generator → live
  selector/assertion verification → deterministic test code.
- Preserve traceability from requirement and plan through generated test and ledger.
- Let a user pause after any phase, inspect its artifacts and resume with another
  compatible agent.

### Agent triage

- Group related failures, separate product failures from environment/setup failures, and
  expose uncertainty plus `blocked_on` evidence.
- Keep the runner provider-neutral: model adapters belong in an optional analysis package
  or agent tooling, not in the execution core.

### Reviewed healing

- Turn fingerprints and candidate scoring into a complete proposal UX: explanation,
  confidence, evidence, source diff, targeted rerun and accept/reject.
- Track accepted/rejected proposals and measure precision/recall on drift plus defect
  controls.
- Never silently rewrite a test during CI.

**Gate for `0.2`:** the same project and artifacts complete the golden path through
Codex/ChatGPT, Claude Code and OpenCode, including a structured failure verdict and
reviewable locator patch.

## P2 — earn the UI-testing moat (8–12 weeks)

- First-class Chromium, Firefox and WebKit projects, viewports and device profiles.
- Visual assertions/diffs and accessibility checks with evidence-pack integration.
- Trace/timeline UI connecting action intent, locator resolution, DOM/ARIA state, network,
  console, screenshot and API oracle.
- Robust iframes, shadow DOM, popups, tabs, dialogs, uploads/downloads and websocket flows.
- Multi-user and multi-session scenarios with isolated seed data.
- Auth extensions for storage state, OIDC/MFA hooks and email/SMS test adapters.
- Flake history, quarantine with expiry/ownership, repeat policies and failure clustering.

**Gate for `0.3`:** the public corpus covers these UI primitives and at least two real
open-source applications run in the cross-browser CI matrix.

## P3 — ecosystem and scale

- Stable plugin contracts for engines, auth, seed adapters, exporters, evidence filters and
  triage providers.
- Sharding, remote browser providers, Docker image and reusable CI workflows.
- Change-aware test selection and coverage mapping from product surface to specs/tests.
- Historical analytics for flakes, failure families and evidence quality.
- Migration guides from Playwright/pytest and optional adapters for Stagehand or Midscene
  during discovery, while deterministic code remains the promoted artifact.
- Independently reproducible benchmark comparisons and two or more external design
  partners using Testence on real applications.

**Gate for `1.0`:** stable public API and evidence schema, documented migrations, security
review, cross-browser support, external adopters and no critical known correctness or
privacy gaps.

## What not to build yet

- A proprietary browser/device cloud.
- A general-purpose API testing platform; API calls should serve UI seeding and independent
  oracles first.
- Silent self-healing.
- A mandatory hosted dashboard or mandatory model provider.
- Natural-language actions in the default CI path.
