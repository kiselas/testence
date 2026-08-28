# Testence

[English documentation](docs/en/README.md) · [Русская документация](docs/ru/README.md)

**Agent-native UI verification for web applications.** Give a coding agent a feature,
pull request or product risk. Testence is designed to turn it into a reviewable plan,
deterministic browser tests and evidence-backed verdicts.

The agent plans, authors and maintains the tests. A deterministic runner executes them
at machine speed with no LLM in the default run path. Every failure becomes an
**evidence pack** — a bounded, structured bundle of UI state, network and console
signals, and API-oracle results that an agent can judge.

> The name combines **test** and **evidence**: the runner records evidence, the agent
> returns a *verdict* (`real_bug / behaviour_change / ui_change / flaky_timing /
> environment`) or declares what is missing, and self-healing stays a reviewable diff,
> never runtime magic.

## Why Testence

- Interactive agent clicking is useful for discovery, but repeated model-driven steps
  are slow, costly and difficult to reproduce.
- Classic e2e frameworks execute fast but humans pay for authoring and red-run triage.
- AI testing platforms often make execution, healing or model choice opaque.
- Testence splits the loop: **agent plans and writes → machine runs → agent judges →
  human or policy approves change.** Accepted tests remain ordinary code and routine
  CI is LLM-free by construction.

Testence is **agent-native, not agent-specific**. The target integration uses portable
skills, repository instructions, CLI and MCP so the same project can be operated from
Claude Code, ChatGPT/Codex, OpenCode and other tool-capable agents.

See the [product positioning](docs/en/product-positioning.md) and the transparent
[agent workflow](docs/en/agent-workflow.md).

## Product architecture

```
agent control plane       plan · author · triage · propose
        │                 skills · project instructions · CLI/MCP
        ▼
verification plane       deterministic pytest/DSL/Playwright runner
        │                 no model dependency during ordinary replay
        ▼
trust plane              run.jsonl · evidence pack · verdict · approval
                          redaction · provenance · policy
```

- `src/testence/engine/` — engine facade; Playwright is an implementation detail
  behind a protocol, never part of the public API (ADR-0001).
- `src/testence/evidence/` — append-only `run.jsonl`, versioned schema `testence/1`
  (ADR-0003), per-section token budgets.
- `src/testence/dsl/` — step primitives carrying *intent* and element *fingerprints*
  (fuel for future heal-diffs and intent caching).
- `src/testence/auth/` — pluggable login strategies (form, api-session, bearer/JWT,
  basic, attached) producing one scheme-agnostic session (ADR-0010).
- `src/testence/config.py` — targets, profiles and credentials from settings/env,
  never from code ([configuration](docs/en/configuration.md)).
- `src/testence/api.py` — stdlib JSON client that shares the browser's session, so
  oracles read the API as the same user the UI is logged in as.
- `src/testence/triage/` — evidence-pack assembly, the verdict taxonomy contract, and
  heal proposals (a reviewable diff, never a runtime rebind — ADR-0011).
- `corpus/` — failure corpus: seeded defects with ground-truth labels, so "healing
  works" and "we don't report false failures" are measured, not asserted.
- `src/testence/report/` — self-contained single-file HTML report (ADR-0005).
- `src/testence/export/` — reporting sinks rendered from the ledger (Allure results,
  CTRF); no reporting SDK is imported anywhere, and a third party registers its own
  exporter through an entry point ([reporting](docs/en/reporting.md), ADR-0013).
- `src/testence/kernels/` — pure CPU functions behind a versioned ABI, swappable for
  an optional native (Rust) backend without touching callers (ADR-0009).
- `src/testence/pytest_plugin.py` — pytest integration: per-test evidence, failure hooks.
- `docs/en/adr/` and `docs/ru/adr/` — every significant choice with the
  comparisons that justified it, in both languages.
- `bench/` — decision experiments (E1…) and the synthetic target page.

## Current developer preview

```bash
pip install -e .
python -m playwright install chromium            # browser paired with Playwright
pytest tests/                                    # framework's own suite
pytest examples/ --testence-headless              # end-to-end demo, no external app required
testence report runs/<run-id>                     # render the HTML report
testence metrics runs/<run-id> ...                # aggregate metrics.json
```

Point it at an application by copying `.env.example` → `.env.local` and
`testence.example.json` → `testence.json`, then:

```bash
TESTENCE_PROFILE=staging pytest tests_e2e/
```

To cover a feature with a suite, follow
[docs/en/testing-a-feature.md](docs/en/testing-a-feature.md) —
the working order, the seeding discipline for a shared environment, and common traps.

The full agent-operated bootstrap, PlanSpec and typed triage workflow are the target for
the public alpha and are not all implemented yet. The exact proposed lifecycle and the
current/target capability boundary are documented in
[docs/en/agent-workflow.md](docs/en/agent-workflow.md).

For the current engineering assessment, market comparison and release sequence, see the
[project audit](docs/en/project-audit.md),
[competitive landscape](docs/en/competitive-landscape.md),
[product positioning](docs/en/product-positioning.md) and [roadmap](docs/en/roadmap.md).

Project integration is three things: an auth scheme (config, not code — see
[docs/en/auth.md](docs/en/auth.md)), a `SeedAdapter` for deterministic data, and a project
`ActionMap` built on `testence.dsl.Actions`.

## Status

Pre-alpha, foundation stage. Design decisions and measurable acceptance criteria live
in the ADRs (`docs/en/adr/`, mirrored in `docs/ru/adr/`). The public API,
configuration schema and evidence schema may
still change before the first stable release.

Do not run the current pre-alpha against sensitive production data: systematic evidence
redaction and session-cache hardening are P0 release gates.

## License

Apache-2.0. Runtime dependencies are restricted to permissive licenses; the runner
contains no LLM SDKs and makes no network calls to model providers (ADR-0006, ADR-0007).
