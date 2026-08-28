# Competitive landscape

Snapshot: 2026-08-28. This review uses product documentation rather than vendor
benchmarks or marketing speed claims.

## Market shape

The market is splitting into three groups:

1. test runners with agent-assisted planning, generation and repair;
2. managed AI-native testing platforms;
3. browser-agent SDKs that can be embedded in a test system but are not complete test
   runners by themselves.

Testence sits at the boundary of the first and third groups, but proposes a more precise
category: **agent-native UI verification**. The coding agent is the primary operator;
Testence supplies the portable, deterministic execution and evidence contract beneath it.
That agent loop is still a design contract rather than a finished user workflow.

## Direct competitors

| Product | Model | Strongest capabilities | Implication for Testence |
|---|---|---|---|
| [Virtuoso Touchstone](https://www.virtuosoqa.com/) | Commercial enterprise assurance workflow | Requirements and documents become reviewable diffs and traceable tests; execution is described as deterministic, publishing requires approval, and decisions leave evidence | The closest competitor to the new trust/evidence framing. Testence must prove an advantage through openness, local-first ownership, same-session oracles and a public correctness corpus |
| [Leapwork Play](https://leapwork.com/leapwork-play/) | Commercial agentic continuous-validation platform | Planning and generation from code/requirements, deterministic TypeScript/Playwright, governance, reporting, approvals and self-healing | Agentic authoring plus deterministic execution is now an enterprise baseline; open artifacts and portability must be measured Testence differences |
| [Functionize Studio](https://www.functionize.com/) | Commercial autonomous testing agent | Plain-language authoring, root-cause analysis, healing and a proprietary generative-intent/deterministic-core architecture | Competes on the same reasoning/execution boundary with a hosted knowledge layer; Testence must win on auditability without a closed model learning on every run |
| [Applitools Autonomous](https://applitools.com/platform/autonomous/) | Commercial no-code E2E platform | Plain-English authoring, a deterministic language model, Visual AI, API and cross-browser checks | Makes visual evidence and deterministic natural-language replay expected; missing visual/a11y support in Testence is a product gap, not optional polish |
| [BrowserStack Agentic Low Code](https://www.browserstack.com/docs/low-code-automation/test-recording/browserstack-ai/agentic-testing) | Agentic authoring on a browser/device cloud | Generate → refine → automate → validate → heal, real devices, full version history and intent-aware healing | Sets the self-validation and scale bar; Testence need not own a cloud but needs a clean remote-provider contract and a complete decision history |
| [SmartBear Reflect](https://support.smartbear.com/reflect/docs/en/recording) | Commercial AI/no-code platform | Recording and natural-language steps, API/visual/email/SMS flows, reusable segments and runtime adaptation | A strong benchmark for manual-QA UX. Testence should preserve explicit code and review instead of hidden adaptation without conceding important web E2E breadth |
| [Playwright Test Agents](https://playwright.dev/docs/test-agents) | Open-source runner plus planner, generator and healer definitions for coding agents | Human-readable plans, executable test generation, live selector/assertion verification and a repair loop, with setup for VS Code, Claude, Codex and OpenCode; the underlying runner already has cross-browser execution, traces, parallelism and a mature ecosystem | The default comparison. Testence cannot win on "Playwright plus an agent" alone; it needs a sharper evidence, safety and deterministic-replay story |
| [Momentic](https://momentic.ai/docs) | Commercial AI-native platform; readable YAML stored with the project | Natural-language authoring, web/iOS/Android, local/CI execution, agent maintenance, step caching, reports, videos and traces | Sets the usability bar for authoring and maintenance; Testence can differentiate with local-first code, provider neutrality and no model calls during replay |
| [QA Wolf](https://docs.qawolf.com/qawolf/Welcome-to-QA-Wolf) | Managed testing service backed by Playwright/Appium code | AI-assisted coverage creation, managed execution and maintenance, web/mobile coverage and broad workflow integrations | Competes on outcome and service, not only framework features. Testence should remain developer-owned and composable rather than imitate a managed QA service |
| [mabl](https://help.mabl.com/hc/en-us/articles/31649455424660-Create-tests-with-generative-AI) | Commercial low-code testing platform | Prompt-based browser, mobile and API test creation, visual assertions and semantic auto-healing | Raises expectations for visual testing and low-friction creation; Testence should keep healing reviewable and measurable instead of silently mutating tests |
| [testRigor](https://testrigor.com/docs/language/) | Commercial natural-language test platform | Plain-English tests across web, mobile, desktop and API, with integrations for common real-world workflows | Shows the breadth expected by enterprise QA. Testence should first win a narrower UI-first developer niche rather than chase every platform |
| [KaneAI](https://www.lambdatest.com/video/product-update-july-2024) | Commercial agentic authoring on a cloud test platform | Natural-language planning, authoring and evolution tied to large-scale browser/device execution | Testence needs clean CI/sharding contracts and portable artifacts even if it deliberately avoids owning a device cloud |

## Adjacent open-source projects

| Product | What it is | Relationship to Testence |
|---|---|---|
| [Midscene.js](https://midscenejs.com/) | Vision-driven UI automation with natural-language actions, assertions and extraction, plus Playwright/Puppeteer integrations | A candidate optional authoring/discovery backend and a competitor for AI-native UI interaction. Testence should not require vision or a model in ordinary CI |
| [Stagehand](https://docs.stagehand.dev/v3/first-steps/introduction) | Browser automation SDK combining code with `act`, `extract`, `observe` and autonomous agents | More an automation primitive than a test framework. Its cached/replayable actions validate Testence's split between AI discovery and deterministic execution |

## Where Testence is already differentiated

See the [competitive benchmark](benchmark/competitive.md) for the method and current
local results. Vendor-documented capabilities are not treated as measured until the
corresponding arm runs against the shared SUT.

- **AI compiles; the runner replays.** Test execution is deterministic and has no model
  SDK or model-provider call in its normal path.
- **Evidence is a product surface.** A versioned append-only ledger, bounded evidence
  packs, UI state, console/network signals and same-session API oracles are designed for
  both humans and agents.
- **Healing is reviewable.** A proposed locator change is a diff and supporting evidence,
  not a hidden runtime rebind.
- **Correctness is measurable.** The synthetic corpus includes defects and harmless
  controls so false greens, false reds and failures for the wrong reason can be scored.
- **Local-first and provider-neutral.** Users own Python tests and can choose the coding
  or triage agent independently of the runner.

The category and concise positioning are:

> **Agent-native UI verification.** Testence is the verification layer between a coding
> agent and a web application: the agent plans, authors and maintains tests; Testence
> replays them deterministically and returns structured evidence it can judge.

The public promise is: **give your coding agent a feature; get a reviewable test plan,
deterministic UI tests and evidence-backed verdicts.**

## Material gaps

### Must close before a public alpha

- There is no complete agent bootstrap → PlanSpec → discovery → generation → proof →
  triage → reviewed-repair workflow yet.
- There are no portable Agent Skills or stable, typed agent-facing CLI/MCP contracts.
- Network request/response bodies and local session state lack a documented redaction and
  secret-handling policy. Evidence collection is unsafe for sensitive applications until
  this is fixed.
- Static quality gates are not green, and there is no public CI/release matrix.
- Only a narrow Chromium/CDP path is proven; Firefox/WebKit and managed browser lifecycle
  are not first-class.
- The public benchmark is useful engineering evidence, but still synthetic and too small
  for comparative product claims.

### Expected UI-testing breadth

- visual comparison and accessibility assertions;
- trace/timeline viewing and failure grouping;
- iframes, shadow DOM, downloads/uploads, dialogs, popups and multi-tab workflows;
- responsive/device profiles and cross-browser projects;
- multiple users/sessions, email/SMS/MFA hooks and richer test-data lifecycle;
- test selection, sharding, quarantine and flake history.

### Strategic restraint

Testence should not compete by putting natural-language actions directly into every CI
step. That discards its speed, reproducibility and auditability advantages. Agentic or
vision-driven actions can be offered as an authoring-time compiler or an explicit opt-in
fallback whose resolved action is cached, inspected and promoted to deterministic code.
