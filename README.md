<p align="center">
  <img src="docs/assets/testence-mark.svg" width="96" alt="Testence logo">
</p>

<h1 align="center">Testence</h1>

<p align="center">
  <strong>Agent-first browser testing with evidence-backed verdicts.</strong><br>
  Agents author and investigate. A deterministic runner proves what happened.
</p>

<p align="center">
  <a href="https://github.com/kiselas/testence/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/kiselas/testence/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="Python 3.10+" src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&amp;logoColor=white">
  <a href="LICENSE"><img alt="Apache 2.0" src="https://img.shields.io/badge/License-Apache--2.0-6C63FF"></a>
  <img alt="Status: pre-alpha" src="https://img.shields.io/badge/status-pre--alpha-F59E0B">
</p>

<p align="center">
  <a href="docs/en/README.md">English docs</a> ·
  <a href="docs/ru/README.md">Документация на русском</a> ·
  <a href="docs/en/demo-spec.md">Demo contract</a> ·
  <a href="docs/en/benchmark/launch-protocol.md">Benchmark protocol</a>
</p>

The machine-readable [support matrix](support.json) is the source of truth for the
declared Python, operating-system and dependency floors. Hosted receipts for the exact
clean candidate are still required before a platform is called release-verified.

---

Testence turns a product claim into a reviewable `PlanSpec`, deterministic browser
test, structured evidence pack and typed verdict. Routine replay contains no LLM call
and no provider lock-in. The agent does the work that benefits from reasoning; the
runner does the work that must be fast and reproducible.

```text
feature or risk
      │
      ▼
agent plans ──► writes ordinary pytest ──► deterministic replay
                                                   │
                                                   ▼
human/policy ◄── reviewable repair ◄── evidence pack + verdict
```

## Why Testence

| | Traditional E2E | Interactive browser agent | Testence |
|---|---|---|---|
| Authoring | Human-heavy | Agent-driven | Agent-driven |
| Routine replay | Deterministic | Model-driven | Deterministic |
| Failure output | Logs and screenshots | Conversation | Versioned evidence pack |
| Healing | Manual or opaque | Session-local | Reviewable proposed diff |
| Model dependency in CI | None | Usually required | None |
| Verdict contract | Ad hoc | Prose | Typed and evidence-bound |

The key distinction is not “AI writes tests.” Many tools can do that. Testence makes
the complete agent workflow auditable: plan, claim, evidence, verdict and repair are
explicit contracts that another agent, a reviewer or policy can verify.

## Quick start

```bash
git clone git@github.com:kiselas/testence.git
cd testence
uv sync --locked --extra dev --extra parallel
uv run playwright install chromium

uv run testence plan validate examples/specs/target-page.md --json
uv run pytest examples -q --testence-headless
```

For a wheel-only onboarding check in a new or existing project:

```bash
testence doctor --json
testence init . --json
testence run --project . --run-id r-onboarding
testence inspect runs/r-onboarding --json
```

Or run the complete portable green/failure demo and render both local reports with one
command:

```bash
testence demo run --project testence-demo --json
```

The scaffold lives under `.testence/` and is not added to the existing pytest suite;
the default `testence run` selects it explicitly. Every generated file is bound by a
scaffold manifest, and conflicting user files are left untouched.

Every failed test produces a bounded evidence pack containing the relevant UI state,
network and console signals, intent-bearing steps, independent oracle observations and
a verdict template. Render a standalone report with:

```bash
uv run testence report runs/<run-id>
```

To integrate a real application, define a target profile in `testence.json`, keep
credentials in environment variables or `.env.local`, and run ordinary pytest:

```bash
TESTENCE_PROFILE=staging uv run pytest tests_e2e -q
```

Follow [Testing a UI feature](docs/en/testing-a-feature.md) for the full workflow.

## Fast agent authoring

Keep the authenticated browser alive and attach short runs over CDP:

```bash
# terminal 1
uv run python -m testence.dev_browser --profile staging

# terminal 2: rerun on save without restarting Python or pytest
uv run testence watch --warm \
  -w tests_e2e -w src -- \
  python -m pytest tests_e2e/test_widget.py -k created_widget \
  --testence-profile staging-attached -q
```

Warm mode retains the Playwright/CDP engine connection while creating a new pytest
session, fixtures, auth context, run id and evidence writer on every iteration. Fresh
processes remain the required path for CI and release validation.

On the maintained production-built React profile, warm engine reuse reduced bootstrap
p50 from **2,808 ms to 447 ms** (−84.1%) and whole-run p50 from **3,447 ms to
1,133 ms** (−67.1%). See the
[result snapshot](bench/results/warm_runner_latency.md),
[machine-readable budget](bench/budgets/warm_runner_latency.json) and
[ADR-0018](docs/en/adr/0018-warm-authoring-runner.md). Numbers are local engineering
evidence, not a cross-machine performance promise.

## Evidence, not runtime magic

A verdict is a versioned document bound to the plan, claims and captured run:

```json
{
  "schema": "testence/verdict/2",
  "project_id": "widgets",
  "case_id": "create-widget",
  "variant_id": "default",
  "attempt_id": "attempt-controller-1",
  "run_id": "r-20260906-120000-abc123",
  "proof_id": "proof-0123456789abcdef0123",
  "plan_digest": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "test_digest": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "policy_digest": "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
  "pack_digest": "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
  "plan_id": "widgets.create",
  "verdict": "real_bug",
  "test_id": "test_created_widget_is_visible",
  "confidence": 0.96,
  "summary": "POST succeeded, but the new row never appeared in the UI",
  "claim_results": [
    {
      "claim_id": "widgets.create.persisted",
      "status": "failed",
      "reason": "The persisted row is absent from the rendered collection",
      "evidence": ["oracle.json#/0"]
    }
  ]
}
```

When evidence is insufficient, the agent must abstain and state what is missing.
Locator healing follows the same rule: it creates a proposed patch with provenance and
confidence; it never silently changes the selector during execution.

## Agent-native by design

The package ships portable skills for four bounded jobs:

- `testence-plan` — turn a feature or risk into claims and a PlanSpec;
- `testence-author` — create deterministic tests and independent oracles;
- `testence-triage` — classify failures from bounded evidence;
- `testence-repair` — propose a reviewable change and prove it safely.

The same versioned skill pack is designed for Codex/ChatGPT, Claude Code, OpenCode and
other Agent Skills clients. Client adapters stay thin; the contracts remain portable.
See [Agent Skills](docs/en/agent-skills.md) and the
[agent workflow](docs/en/agent-workflow.md).

## Architecture

```mermaid
flowchart LR
    A[Agent control plane<br/>plan · author · triage · repair]
    V[Verification plane<br/>pytest · DSL · Playwright/CDP]
    T[Trust plane<br/>ledger · evidence · verdict · policy]
    A -->|versioned contracts| V
    V -->|append-only events| T
    T -->|reviewable proposal| A
```

- `src/testence/contracts` — PlanSpec and verdict schemas with claim traceability;
- `src/testence/engine` — replaceable execution protocol and Playwright/CDP backend;
- `src/testence/dsl` — intent-bearing actions and exact-by-default assertions;
- `src/testence/evidence` — append-only `testence/2` ledger and bounded artifacts;
- `src/testence/triage` — evidence packs, verdicts and reviewable healing proposals;
- `src/testence/agent` — packaged, versioned, client-neutral skills;
- `bench` and `corpus` — real-React latency gates and seeded correctness defects.

Important decisions are recorded as bilingual ADRs with measurable tripwires:
[English](docs/en/adr/README.md) · [Русский](docs/ru/adr/README.md).

## Proof before claims

Testence keeps benchmark inputs, budgets and raw result snapshots in the repository.
The current proof surface includes:

- a production-built React latency gate for navigation, controlled inputs and mutation
  synchronization;
- a shared-browser and warm-runner benchmark for the authoring loop;
- a seeded mutation corpus for false-green, false-red and healing quality;
- a competitive replay protocol with frozen scenarios and environment disclosure.

Start with the [launch protocol](docs/en/benchmark/launch-protocol.md) and
[benchmark corpus](docs/en/benchmark/corpus.md). A number without its command,
environment and failure criteria is deliberately not treated as a product claim.

## Project status

Testence is a **pre-alpha developer preview**. PlanSpec propagation, verdict validation,
portable skills, deterministic execution and evidence packs are implemented. Public
agent bootstrap and managed verdict submission are still alpha work; APIs may change.

Do not use the current preview against sensitive production data. Systematic evidence
redaction and the remaining security review are release gates. API credentials are
origin-bound and the opt-in session cache has TTL and identity checks, but the complete
canary/path/retention matrix from the release specification is not yet accepted. See
[SECURITY.md](SECURITY.md), [CONTRIBUTING.md](CONTRIBUTING.md) and the
[roadmap](docs/en/roadmap.md).

## License

[Apache-2.0](LICENSE). Runtime dependencies are restricted to permissive licenses. The
runner contains no LLM SDK and makes no call to a model provider during ordinary replay.
