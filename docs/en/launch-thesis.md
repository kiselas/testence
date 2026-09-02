# Launch Thesis

Status: **execution decision**. Version: `0.1`. Snapshot: 2026-08-28.
Owner: Product Owner. Review: after the first external benchmark and five observed
activations.

Related artifacts: [DemoSpec](demo-spec.md) and
[Launch Benchmark Protocol](benchmark/launch-protocol.md).

## Decision

Testence will not enter the market as “another AI testing framework.” We are creating
and claiming a narrower category:

> **Testence is the trust layer for coding agents. The agent is not done until it has
> proved that the user outcome was actually achieved.**

The public entry point into this category is one expensive, easily demonstrated
problem:

> **The UI test passed. The data was not saved. Testence caught it.**

The first product wedge is a complete **Trustworthy Proof Loop**:

```text
requirement → PlanSpec → deterministic test → live proof
            → evidence → typed verdict → reviewed repair
```

Until this path works, we will not expand into a device cloud, visual platform,
universal MCP server, low-code editor, or hosted dashboard.

## User and expensive job

The primary user is a developer or small product team already using a coding agent to
change a web application. They do not want to become experts in another test runner.
Their job is:

> “After a code change, prove that the critical user journey works, the outcome was
> persisted, the green test is not lying, and any failure is explained for the right
> reason.”

Today they choose among four unsatisfactory alternatives:

1. trust compilation, unit tests, and a visual inspection of the page;
2. ask a coding agent to click through a browser interactively;
3. write a regular Playwright test and investigate traces manually;
4. delegate testing to a hosted AI platform and accept its ownership, healing, and data
   retention model.

Testence must win through lower **time to trustworthy proof**, not through the number of
tests generated, while reducing the risk of false greens and hidden repair.

## Why now

| Basis | Evidence level | Implication |
|---|---|---|
| Playwright already ships planner, generator, and healer agents for several coding-agent clients | Documented | Test generation and agent definitions are a baseline, not a differentiator |
| Agent Skills standardize `SKILL.md`, progressive disclosure, and portable resources | Documented | One canonical skill pack is more realistic than separate prompts for every client |
| Testence already has append-only evidence, a UI/API oracle, verdict types, bounded packs, and proposals instead of runtime healing | Hands-on | The technical foundation matches the trust wedge, although the end-to-end product is not assembled yet |
| The current replay benchmark measured a 1,743.5 ms median versus 2,404.6 ms on one synthetic scenario | Measured | Runtime does not appear to be the bottleneck, but this does not prove faster authoring or market superiority |
| 51 synthetic item-runs completed with `false_green=0`, `false_red=0`, and `right_reason=1.0` | Measured | The taxonomy and harness work as a smoke floor; the sample is too small and synthetic for a strong public claim |
| Coding-agent users will spend attention on independent proof of outcomes | Hypothesis | This is the central market hypothesis; it must be falsified through observed activations, not interviews without use |

Current measurements live in the [competitive benchmark](benchmark/competitive.md) and
[corpus report](benchmark/corpus.md). They are baselines, not the launch headline.

## Promise and result contract

The input is a requirement, pull request, bug, or product risk. The durable output is
five repo-owned artifacts:

1. a **PlanSpec** with stable product-claim IDs, risks, test data, and independent
   oracles;
2. a **deterministic test** that runs locally and in CI without a model;
3. an **evidence ledger and bounded pack** that connect actions, UI, network, and API
   observations to claim IDs;
4. a **typed verdict** with a reason, confidence, evidence references, and the ability to
   abstain;
5. a **reviewable proposal** when the test genuinely needs a change, plus the smallest
   proving rerun.

The product is not agent-first until a new user can obtain all five outcomes through a
coding agent without manually learning the internal DSL.

## Advantages to amplify

| Advantage | User value | How we prove it | What makes it defensible |
|---|---|---|---|
| Same-session UI + API oracle | Finds plausible false greens where the interface shows success but the system did not change | Share of seeded API-only defects found for the right reason | A growing catalog of oracle patterns and truth cases |
| End-to-end claim IDs | Makes it clear which product promise was proved or violated | Claim coverage and traceability completeness | An open PlanSpec → code → evidence → verdict contract |
| Deterministic replay without an LLM | Fast, inexpensive, reproducible CI | Replay latency, flake rate, and absence of model calls | Compatibility with existing test infrastructure |
| Bounded evidence for agents | Faster triage with fewer tokens and no artifact dump | Verdict accuracy, tokens, and time to accepted diagnosis | A versioned evidence schema and a corpus of real failures |
| Healing as a proposal | Repairs do not hide defects and remain reviewable | Unsafe-repair rate and accepted-proposal rate | Decision history, policy, and proving reruns |
| Provider-neutral skills | Teams are not locked to one coding agent | One golden workflow in Codex/ChatGPT, Claude Code, and OpenCode | Canonical skill pack, compatibility suite, and update protocol |
| Open truth corpus | Public claims can be independently falsified or confirmed | Independent reproductions and external cases | Reputation as a trustworthy standard, not a closed leaderboard |

The first three public proofs must be:

- Testence caught a false green that passed a UI-only check;
- Testence explained the reason through claim-linked evidence rather than merely making
  a test red;
- the accepted test replayed in CI without a model.

## What we borrow and what remains ours

We use established mechanics wherever novelty adds no user value.

| Source | Borrow | Testence adaptation | Do not copy |
|---|---|---|---|
| [Playwright Test Agents](https://playwright.dev/docs/test-agents) | Plan/generate/heal separation, seed tests, `init-agents`, and regenerated definitions on upgrades | One proof loop where plan and verdict have schemas and repair requires evidence plus a rerun | Treating an automatic repair as proof of correctness by itself |
| [Agent Skills specification](https://agentskills.io/specification) | `SKILL.md`, `scripts/`, `references/`, `assets/`, progressive disclosure, and the standard validator | A canonical skill pack with thin client adapters | Long monolithic prompts and separate business logic per client |
| [OpenCode Agent Skills](https://opencode.ai/docs/skills) | `.agents/skills` compatibility, permissions, and metadata-based discovery | The generic adapter installs the standard path first; a client adapter adds only the required shim | Making the core workflow depend on OpenCode configuration |
| [OpenAI Skills API](https://developers.openai.com/api/reference/go/resources/skills) | Immutable versions and a separate default pointer as a lifecycle pattern | A local manifest pins an exact version; the stable channel moves separately | A required hosted registry or OpenAI API dependency at runtime |
| [SWE-bench](https://github.com/SWE-bench/SWE-bench) | A verified subset, isolated evaluator, raw logs, and reproducible tasks | `Testence Verified`: real OSS applications plus public seeded patches | A single leaderboard percentage without false-green/right-reason decomposition |
| [web-platform-tests](https://web-platform-tests.org/writing-tests/index.html) and [Test262](https://github.com/tc39/test262/blob/main/CONTRIBUTING.md) | A locally runnable conformance corpus, metadata, positive/negative cases, and lint-before-contribution | Every truth case carries a claim, ground truth, stratum, expected verdict, and control | A huge browser matrix before the beachhead is proven |
| [uv](https://docs.astral.sh/uv/guides/projects/) | Lockfiles, one-command execution, and verifiable builds | A frozen benchmark environment and clean wheel installation | A custom dependency manager |

The governing rule is: **skills teach the process; schemas and CLI enforce
correctness**. Anything that can be validated programmatically must not exist only in
Markdown.

## Canonical skill pack and updates

### Delivery model

Source and wheel contain one canonical version:

```text
agent-pack/
├── manifest.json
├── skills/
│   ├── testence-plan/SKILL.md
│   ├── testence-author/SKILL.md
│   ├── testence-triage/SKILL.md
│   └── testence-repair/SKILL.md
├── references/        # PlanSpec, verdict, and policy contracts
└── adapters/          # discovery paths and instruction shims only
```

Skills follow the open Agent Skills format. Every material operation invokes the
structured Testence CLI. Client adapters do not duplicate workflow logic.

### User lifecycle

Target interface:

```bash
testence agent init --client codex --dry-run
testence agent init --client codex
testence agent status
testence agent update --check
testence agent update
```

`init` and `update` create a repo-owned lock manifest containing:

- Testence, schema, and agent-pack versions;
- the selected adapter and actual target paths;
- the SHA-256 of every installed file;
- base version, local modification state, and available version;
- update channel (`stable` or an explicitly selected prerelease).

Updates are safe by construction:

1. produce a manifest and diff before writing;
2. never overwrite a locally modified file;
3. apply clean changes atomically;
4. create a proposal/patch and return a non-zero exit code on conflict;
5. retain the previous pack for exact rollback;
6. run a discovery smoke test for the selected client after the update.

The first release ships the pack inside the wheel and needs no network. A registry or
HTTP catalog may later accelerate distribution, but a remote pack is accepted only with
a digest, provenance, and explicit update. Unreviewed automatic updates are forbidden.

### Client matrix

| Client | Canonical content | Thin adapter | Gate |
|---|---|---|---|
| Codex / ChatGPT | the same Agent Skills pack | supported plugin/skill package and a bounded `AGENTS.md` block | discovery, explicit invocation, complete golden path |
| Claude Code | the same pack | `.claude/skills` or plugin plus a bounded `CLAUDE.md` | the same three checks |
| OpenCode | preferably `.agents/skills`, which the client already discovers | `AGENTS.md` and permissions where required | the same three checks |
| Generic | `.agents/skills` | manual connection instructions | schema/CLI contract tests |

A platform is supported only after a CI discovery smoke test and an observed complete
scenario. The presence of a copied `SKILL.md` is not compatibility.

## Launch gates

Public launch is allowed only when all of the following are true:

- the complete killer demo reproduces from a clean checkout with one command, no signup,
  and no required cloud;
- four of five new users reach their first trustworthy proof within 15 minutes without
  hints from the author;
- the frozen corpus has no known false green or unsafe repair;
- canary secrets are absent from the ledger, pack, HTML, and exporters;
- the same workflow is proved in Codex/ChatGPT, Claude Code, and OpenCode;
- the launch benchmark runs through one documented command and publishes raw data;
- at least two external people reproduce the demo independently, including one
  skeptical reviewer of the launch article;
- README, wheel, CI, `SECURITY.md`, contribution guidance, and compatibility policy are
  ready for an external user.

Stars, views, and generated-test counts do not replace these gates.

## Public claims

Allowed message progression:

1. **Now:** “Testence is exploring an evidence-first approach; current numbers apply to
   an open synthetic corpus.”
2. **After a protocol run:** exact correctness and time-to-proof results with intervals,
   raw artifacts, and limitations.
3. **After independent reproduction:** “External participants reproduced the result.”
4. **Only after real-app breadth:** a comparative product-advantage claim.

The current `27.5%` replay result and `200×` operation-level experiment are not launch
headlines. They answer narrow engineering questions, not how quickly users reach a
trustworthy outcome.

## Distribution

One technical fact anchors every asset, with a channel-specific angle:

- Habr: a technical case, “Why the UI test passed when the data was not saved”;
- vc.ru: the cost of false confidence and the product-decision story;
- Show HN: a working repository that runs without registration;
- an English technical article: an open trust contract, false greens, and a
  reproducible benchmark;
- short video/X: the visual moment from green UI-only to a red evidence-backed verdict.

Publication rolls out over 72 hours rather than all at once so the team can respond,
fix onboarding, and direct discussion toward the reproducible artifact.

## Risks and kill criteria

We revisit the strategy if any of the following is confirmed:

- fewer than three of five target developers consider the trust problem painful after
  hands-on use;
- same-session API oracles require enough project-specific glue that first value
  consistently takes over 30 minutes;
- Testence does not improve correctness or time to trustworthy proof over well-configured
  Playwright Test Agents on identical tasks;
- the advantage appears only on our synthetic SUT;
- users experience evidence and PlanSpec as a tax and systematically bypass them;
- a Python runtime repels web teams more strongly than the trust contract attracts them.

When these criteria trigger, we do not expand the feature set. The preferred pivot is an
open evidence/verdict layer on top of existing runners, not a broader standalone
framework.

## Execution order

1. Freeze the [DemoSpec](demo-spec.md) and scenario truth.
2. Implement the Trustworthy Proof Loop for one client, including security/redaction.
3. Extract the canonical skill pack and safe update lifecycle.
4. Run the frozen [Launch Benchmark Protocol](benchmark/launch-protocol.md).
5. Fix onboarding based on five observed users.
6. Prepare the launch wave and widen compatibility only after the gates pass.

A new feature can move ahead of this order only if it closes a launch gate, improves the
central metric, or makes the public proof more honest.
