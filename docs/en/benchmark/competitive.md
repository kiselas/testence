# Competitive benchmark

Method snapshot: 2026-08-28. This benchmark keeps three questions separate instead of
collapsing them into one marketing number:

1. **Replay:** how quickly and reliably an accepted test runs in CI.
2. **Authoring:** the agent and human-review cost of reaching an accepted test.
3. **Workflow:** how well requirement → plan → test → proof → triage → reviewed repair
   is supported and which artifacts survive each phase.

## Cohorts

| cohort | products | comparison |
|---|---|---|
| Direct agent-native | Testence, Playwright Test Agents, Virtuoso Touchstone, Leapwork Play, Functionize Studio, Applitools Autonomous, Momentic, KaneAI, BrowserStack Agentic Low Code, Reflect | End-to-end UI test authoring, execution, evidence and maintenance |
| AI/low-code alternatives | mabl, testRigor, Katalon, Autify, ACCELQ, Testim, Tosca | Another ownership and authoring model competing for the same outcome |
| Code-first baselines | Playwright Test, Cypress, WebdriverIO, SeleniumBase, Robot Framework Browser | Runner speed, code portability and mature engineering workflow |
| Adjacent components | Stagehand, Midscene.js, Playwright MCP/CLI, Chrome Recorder, browser clouds, reporting and visual tools | One phase only; excluded from an overall product ranking |

QA Wolf is a separate managed-service track because it sells maintained coverage and an
outcome; its labor economics are not directly comparable to a DIY framework.

## Completed replay measurement

`bench/competitive/run.py` runs Testence and Playwright Test against the same static SUT
and six intent-bearing steps. Each sample is a fresh runner process including discovery,
Chromium launch, test execution, reporting and shutdown; SUT startup is excluded. Arms run
serially with one worker, no retries, trace or video, and one discarded warm-up.

On Windows 11, Playwright Chromium 151.0.7922.34, Python 3.12.13 and Node 22.22.0,
seven measured repeats gave:

| arm | median | p95 | scenario source |
|---|---:|---:|---:|
| Testence | 1,743.5 ms | 1,812.3 ms | 13 meaningful lines |
| Playwright Test | 2,404.6 ms | 2,462.7 ms | 21 meaningful lines |

Testence's median was **27.5% lower** (ratio `0.725`). This is fresh-process replay on
one host, not a real-suite speed claim. Source size is a transparent proxy, not authoring time. Raw samples,
versions and the method revision are in `bench/results/competitive-replay.json`.

The seeded-behaviour corpus was also run three times: 51 item-runs with
`outcome_accuracy=1.0`, `false_green_rate=0.0`, `false_red_rate=0.0`,
`right_reason_rate=1.0` and `heal_recall=1.0`. It remains a saturated smoke floor until
the A stratum and realistic multi-page/concurrent scenarios exist.

## Authoring protocol

Every product receives the same requirement, SUT repository, starting point and
acceptance suite. Coding-agent arms use fresh isolated sessions with no context carried
between products. Hosted arms disclose plan, model, region and enabled AI/healing modes.

Measure time to first green and to a review-accepted diff, agent turns, tool calls,
retries, human interventions, disclosed tokens, changed files/meaningful lines,
independently verified acceptance claims and human review time. Run at least three
independent sessions per arm and publish prompts, outputs and exclusions. LOC never
substitutes for elapsed authoring time.

## Maintenance and healing protocol

Run the accepted test against harmless restyle/reorder, accessible-name drift, a true
behavioral defect and timing instability. Measure diagnosis time, false heals, false
reds, right reason, diff size and required approval. Interaction retries remain disabled
where they erase the defect signature.

A heal succeeds only when the change is visible, explained, linked to evidence, proven
by a targeted rerun and not silently applied. Runtime rebinding to a similar element is
not a successful repair without that audit trail.

## Workflow reading

Score intake, planning, discovery, authoring, live proof, deterministic replay,
evidence/triage, repair/review and portability separately. Publish the scale and weights;
unknown capabilities remain `not measured` rather than guessed as zero.

Current documentation-based, non-hands-on reading:

- best open repo-first baseline: [Playwright Test Agents](https://playwright.dev/docs/test-agents);
- closest enterprise assurance workflows: [Virtuoso Touchstone](https://www.virtuosoqa.com/) and [Leapwork Play](https://leapwork.com/leapwork-play/), both documenting review/governance, evidence and deterministic execution;
- strong local/repository natural-language UX: [Momentic](https://momentic.ai/docs);
- managed outcome: [QA Wolf](https://docs.qawolf.com/qawolf/Welcome-to-QA-Wolf);
- most transparent locally measured trust/replay layer in this study: Testence, while its complete agent workflow is not shipped yet.

There is no overall winner yet because the commercial arms have not run the same SUT
under the same plan.

## Implication for Testence

“AI plans, a deterministic runner executes” is no longer unique. [Virtuoso](https://www.virtuosoqa.com/)
documents reviewable diffs, traceability and evidence; [Leapwork](https://leapwork.com/blog/leapwork-announces-continuous-validation-platform/)
documents deterministic-by-design governance; [Functionize](https://www.functionize.com/)
documents generative intent with a deterministic core; and [Applitools Autonomous](https://applitools.com/platform/autonomous/)
documents a deterministic language model.

Testence's defensible wedge is now narrower: open/local/provider-neutral ownership; a
public seeded corpus measuring false-green, false-red and right-reason; same-session
UI/API oracles; an open versioned evidence schema with bounded agent packs; and a
reviewable source diff instead of hidden runtime healing.

The P0 gaps are the complete requirement-to-repair agent loop, redaction/security,
portable skills/CLI, broader cross-browser proof and a reproducible authoring benchmark.
Visual/a11y, a trace viewer, failure grouping and complex browser flows remain P1.
