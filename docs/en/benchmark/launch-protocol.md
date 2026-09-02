# Launch Benchmark Protocol

Status: **pre-registered protocol**. Version: `0.1`. Snapshot: 2026-08-28.
Owner: Product Owner together with the benchmark maintainer.

This protocol must be frozen before comparative execution. After freeze, changes require
a new version and explanation; an inconvenient result is not a reason to rewrite the
rules.

Related documents: [Launch Thesis](../launch-thesis.md),
[DemoSpec](../demo-spec.md), the [current competitive benchmark](competitive.md), and
the [corpus](corpus.md).

## Decision the benchmark must support

The launch benchmark does not ask “who clicks faster?” It asks:

> **Does Testence help a coding agent reach correct, reviewable, maintainable proof of a
> user outcome faster without masking defects?**

The evaluation order is fixed:

1. correctness and safety;
2. correct reason;
3. time to accepted proof;
4. cost and human intervention;
5. replay performance;
6. usability and portability.

An arm that fails the correctness gate cannot win on speed.

## Pre-registered hypotheses

| ID | Hypothesis | Primary metric | Kill criterion |
|---|---|---|---|
| `H1` | Testence finds more plausible false greens for the right reason than a UI-only baseline | false-green rate and right-reason rate on paired cases | No improvement, or any known false green on a launch-critical case |
| `H2` | Testence reduces the time from requirement to review-accepted trustworthy proof compared with Playwright Test Agents | paired median TTTP | No improvement, or the gain disappears after review time is included |
| `H3` | The proposal workflow distinguishes safe drift from product bugs without masking defects | unsafe-repair rate and repair precision | Any automatically accepted unsafe repair |
| `H4` | The accepted result is portable across agent clients | portability completion rate | Any required client needs a fork of the core workflow logic |
| `H5` | The evidence pack accelerates triage without losing material signals | verdict accuracy, time, and tokens | A bounded pack reduces accuracy versus raw artifacts by more than 5 percentage points |

`H2`, `H4`, and user value remain Hypotheses until the complete protocol is run. Current
replay/corpus results are engineering baselines only.

## Compared arms

### Required

1. **Testence Trustworthy Proof Loop** — canonical skill pack, Testence CLI, PlanSpec,
   deterministic test, evidence/verdict, and proposal policy.
2. **Playwright Test + Playwright Test Agents** — official planner/generator/healer,
   regular Playwright artifacts, and the best publicly documented practices.

Playwright is a strong code-first baseline, not an intentionally weakened “manual
test.” Its agent definitions are regenerated for the installed version as required by
the [official documentation](https://playwright.dev/docs/test-agents).

### Diagnostic baseline

3. **UI-only accepted test** — the minimum visible-outcome check without an independent
   oracle. It demonstrates the false-green class but receives no overall product score.

### Optional commercial arms

Momentic and other hosted products may participate only after a hands-on run on the same
SUT and requirement. `Documented` or `Vendor claim` does not become a measured zero and
is never mixed with local arms in one ranking.

## Task set

The benchmark has three layers. No layer substitutes for another.

### L0 — Synthetic Conformance

Purpose: a fast deterministic regression floor.

Launch minimum is at least 30 independent truth cases:

- at least 12 `real_bug`, including at least 6 API-only/optimistic false greens;
- at least 5 `ui_change`;
- at least 3 `flaky_timing` or `environment`;
- at least 10 healthy/harmless controls;
- at least 6 cases where retry/reload can hide the defect;
- at least 4 ambiguous cases where the correct outcome is `blocked_on`, not a confident
  verdict.

Every case contains human-readable metadata and machine-readable truth:

```yaml
id: D-acknowledged-not-persisted
requirement: blocker.create.persisted
stratum: api-only
truth: real_bug
expected_claims: [blocker.create.persisted]
forbidden_repairs: [remove-api-oracle, retry-create, weaken-persistence]
control_pair: C-create-persisted
```

The structure borrows conformance discipline from
[web-platform-tests](https://web-platform-tests.org/writing-tests/index.html) and
[Test262](https://github.com/tc39/test262/blob/main/CONTRIBUTING.md): plan before broad
implementation, metadata, positive/negative cases, a local runner, and mandatory lint.

### L1 — Testence Verified

Purpose: prove that the advantage is not confined to our SUT.

Launch minimum:

- two public OSS web applications using different stacks;
- three tasks per application: creation/persistence, filter/search, and update/delete;
- for every task, one healthy commit, one real-bug patch, and one harmless change;
- ground truth independently reviewed by two people;
- a task is rejected if the requirement is ambiguous, the application is unstable
  without the patch, or the evaluator knows the seed through a hidden side channel.

Two practices come from [SWE-bench](https://github.com/SWE-bench/SWE-bench): a
human-verified subset and an isolated reproducible environment with raw logs. A small
verified set is enough for launch; representativeness cannot be simulated with a large
number of weak synthetic cases.

### L2 — Agent Authoring and Maintenance

For all six L1 tasks, every required arm completes:

1. requirement → plan;
2. authoring → first runnable test;
3. live proof → review-accepted test;
4. run on the healthy control;
5. run on the real bug;
6. harmless drift and reviewable repair;
7. deterministic replay without the agent session.

There are at least three independent sessions for every `arm × task` pair. A headline
TTTP comparison requires at least 18 completed authoring sessions per arm. If the budget
does not allow this, the result is labeled a pilot and does not become a general
percentage claim.

## Unit of evaluation and timing boundaries

**Time to trustworthy proof (TTTP)** starts when the agent receives the requirement and
a clean checkout. It ends only when all of the following are true:

- PlanSpec passes schema and policy validation;
- the created test is runnable and repo-owned;
- every required claim has evidence;
- the verdict matches ground truth or correctly abstains;
- a reviewer accepts the test diff and proof with no blocking comment.

Also record:

- `time_to_first_runnable`;
- `time_to_first_green`;
- `time_to_first_correct_verdict`;
- `human_review_time`;
- `targeted_repair_time`.

A green test with a missing required claim or wrong verdict does not stop TTTP.

## Metrics

### Correctness

| Metric | Definition |
|---|---|
| false-green rate | real-bug cases receiving green/accepted proof divided by all real-bug cases |
| false-red rate | healthy/harmless controls receiving an incorrect red verdict divided by all controls |
| outcome accuracy | cases with the expected outcome divided by all graded cases |
| right-reason rate | detected failures with the correct truth class and required failed claims divided by all detected failures |
| abstention quality | ambiguous cases with correct `blocked_on` and no invented verdict |
| claim coverage | required PlanSpec claims with independent proof divided by all required claims |

### Repair safety

| Metric | Definition |
|---|---|
| unsafe-repair rate | proposals/changes that hide a real bug or weaken a required claim |
| repair precision | accepted safe repairs divided by all proposed repairs |
| repair recall | repairable UI changes receiving a correct proposal |
| review burden | review time and blocking comments before acceptance |

### Agent economics

- TTTP and its phases;
- agent turns, browser/tool calls, retries, and manual interventions;
- input/output tokens and disclosed model cost;
- changed/created files and review-diff size;
- share of tests accepted without manual rewriting;
- tokens per correct verdict, not per arbitrary answer.

### Replay and portability

- fresh-process median/p95 and steady-state test latency;
- flake rate across five consecutive repeats;
- absence of model/provider network calls during deterministic replay;
- completion of one golden workflow in Codex/ChatGPT, Claude Code, and OpenCode;
- client-specific workflow-logic line count;
- canary leakage count across every artifact.

## Experimental rules

### Environment

- record OS, hardware, browser binary, Python/Node, package versions, and commit SHA;
- freeze `uv.lock` and browser revision and use the locked environment;
- execute L1 tasks in a resettable container or equivalent immutable image;
- give paired arms identical, documented network access;
- use one worker for the latency baseline; parallel execution is a separate experiment.

[uv](https://docs.astral.sh/uv/guides/projects/) is used as the existing lock/sync
mechanism rather than replaced by a custom installer.

### Agent sessions

- identical requirement, SUT, starting commit, acceptance criteria, and permissions;
- fresh sessions with no context transfer between arms;
- the same model family/snapshot and reasoning setting where clients allow it;
- publish system/client overhead and do not subtract it after the fact;
- randomize paired-arm order using a fixed seed;
- no author intervention except predeclared permission prompts;
- set wall-clock, turn, and cost caps before execution;
- count a timeout as a failure rather than silently excluding the sample.

### Stop rules and review

The reviewer uses a checklist and does not see the truth label before deciding:

- are all required claims covered?;
- is the oracle genuinely independent?;
- can the test replay without an agent session?;
- does any retry or repair hide the defect?;
- are evidence and provenance sufficient?;
- are secrets absent?

If the reviewer requires a change, time continues. An optional style comment does not
block acceptance.

## Statistics

- publish every raw sample; never publish a median without `n`;
- report latency and TTTP with median, IQR, and bootstrap 95% CI;
- report proportions with Wilson 95% CI;
- pair L2 comparisons by task and compute the interval for the paired difference;
- mark p95 as exploratory at small `n`;
- do not remove outliers automatically;
- exclude only for a predeclared infrastructure reason and publish the sample;
- include failed/timeout sessions in completion rate;
- prioritize practical effect size over a binary `p < 0.05`.

The headline `X% faster to trustworthy proof` is allowed only after the correctness
gate, at least 18 completed sessions per arm, a positive paired effect, and no worsening
of review burden or unsafe repair.

## Correctness and security gates

Before any overall advantage is calculated, a required arm must:

- have `false_green_rate = 0` on launch-critical L0/L1 cases;
- have `unsafe_repair_rate = 0`;
- pass every healthy control correctly;
- lose no required claim;
- emit no canary secret in ledger, pack, HTML, CTRF, or Allure;
- replay the accepted test without an LLM.

If a gate fails, publish the result and failure analysis, but make no speed claim.

## Published bundle

Every release benchmark includes:

```text
benchmark-release/
├── PROTOCOL.md
├── environment.json
├── tasks/                 # requirement, truth metadata, patches, controls
├── prompts/               # exact user/system inputs where licensing allows
├── sessions/              # transcripts, tool logs, cost, timing
├── outputs/               # plans, tests, diffs, evidence, verdicts, reports
├── results.json
├── results.csv
├── analysis.ipynb-or-script
├── checksums.txt
└── LIMITATIONS.md
```

One command must reproduce deterministic L0/L1 grading. Agent authoring may require
credentials, but the evaluator, gold truth, and published outputs do not.

## Independent reproduction

Before launch:

- one external participant reproduces all of L0 and at least one L1 task;
- a second participant reviews the hero case and article claims;
- disagreements remain as issues and enter the limitations;
- `independently reproduced` applies only to the exact protocol, corpus, product, and
  environment versions.

Later, external cases arrive through small reviewable pull requests containing truth
metadata, a healthy control, defect patch, expected claims, and license. CI runs lint,
gold tests, canary scan, and determinism checks.

## Allowed launch claims

| Data | Allowed wording |
|---|---|
| Current synthetic corpus only | “On open synthetic corpus version X…” |
| L0 + L1 protocol | “Across N frozen cases from two OSS applications…” |
| L2 paired sessions | “In this protocol, median TTTP changed by X with 95% CI…” |
| Three client gates | “One workflow reproduced in the listed client versions…” |
| External rerun | “Version X was independently reproduced…” |

Forbidden generalizations include “has no false greens,” “200× faster testing,” “best
AI testing framework,” and rankings of unmeasured commercial products.

## Current baseline and gap to freeze

As of 2026-08-28, the project has measured:

- 7 replay samples after warm-up: Testence median `1,743.5 ms`, Playwright Test
  `2,404.6 ms`, a `-27.5%` difference on one synthetic fresh-process scenario;
- 51 synthetic item-runs: outcome accuracy `1.0`, false green/red `0`, right reason
  `1.0`, and heal recall `1.0`;
- authoring time, review time, cross-client portability, and L1 real-app breadth have not
  been measured.

The PlanSpec/verdict-schema and claim-propagation foundation is complete. Before protocol
freeze:

1. expand L0 to the launch minimum and add ambiguous abstention cases;
2. select two OSS applications and create licensed reproducible patches;
3. implement a clean evaluator command and environment manifest;
4. pin model/client versions, caps, and the reviewer checklist;
5. run one pilot, fix only harness defects, and then declare freeze.

Pilot data is not merged into the frozen run.
