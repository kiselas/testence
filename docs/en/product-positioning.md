# Product positioning

## Category

**Agent-native UI verification.**

Testence is the verification layer between a coding agent and a web application. The
agent plans, authors and maintains the tests; Testence replays them deterministically
and returns structured evidence the agent can judge.

This is deliberately narrower and more defensible than "AI testing platform":

- **agent-native**, because the primary operator is Claude Code, Codex/ChatGPT,
  OpenCode or another tool-capable coding agent;
- **UI verification**, because real browser journeys are the main product surface;
- **verification layer**, because Testence supplies execution, evidence and policy
  contracts rather than another general-purpose autonomous agent.

"Agent-first" describes **who operates the product and owns the workflow**. "AI-first"
describes **where judgment is applied**. Public messaging should lead with
*agent-native*: "AI-first testing" is broad and easily confused with natural-language
steps or an LLM inside every run, both of which are outside Testence's default model.

## Product promise

> Give your coding agent a feature. Get a reviewable test plan, deterministic UI tests
> and evidence-backed verdicts.

Short form:

> **Plan with AI. Replay with certainty. Judge by evidence.**

The input can be a feature request, bug report, pull request or product-risk statement.
The durable output is not an agent conversation. It is a set of repository and run
artifacts: a plan, executable test code, an evidence ledger, a verdict and—when
appropriate—a reviewable change proposal.

## Who the product is for

| Role | Responsibility |
|---|---|
| coding agent | primary operator; plans coverage, explores the UI, writes tests, runs them, interprets evidence and proposes maintenance |
| developer or QA owner | supplies intent, risk and policy; reviews plans and sensitive or source-changing actions |
| CI | replays accepted tests without an LLM and retains portable artifacts |
| Testence | enforces the deterministic execution, evidence, schema and approval contracts shared by all three |

Agent-first does not mean human-free. Humans own intent and policy; agents do the
high-frequency work; deterministic software decides what was actually executed and
recorded.

## The problem

Coding agents can already produce application code, but UI verification still breaks
their loop in three places:

1. Browser agents can explore a UI, but repeated model-driven clicking is slow,
   expensive and difficult to reproduce in CI.
2. Traditional test runners execute quickly, but their authoring conventions and
   failure artifacts were designed primarily for human operators.
3. AI-native test products often hide execution, healing or model choices behind a
   hosted platform, reducing ownership and auditability.

Testence makes exploration disposable and verification durable. AI is used where
judgment has value; accepted behavior is compiled into ordinary deterministic code.

## Product model

Testence has three explicit planes:

### 1. Agent control plane

- project instructions say when Testence should be used;
- versioned skills teach planning, authoring, triage and maintenance workflows;
- a small CLI/MCP surface exposes high-level, typed operations;
- adapters make the same contract discoverable in different agent clients.

This plane may use an LLM. It is provider-neutral and replaceable.

### 2. Deterministic verification plane

- pytest test code and an intent-bearing UI DSL;
- Playwright-backed browser execution and same-session API oracles;
- a versioned event ledger, bounded evidence packs and report exporters;
- repeatable local and CI execution with no model call in the default run path.

This plane is the trusted source of execution truth.

### 3. Trust and governance plane

- schemas and provenance connect intent, plan, generated code, run and verdict;
- redaction and retention policies protect captured application data;
- permission gates separate observation, execution and source changes;
- healing is a proposal with evidence and a targeted rerun, never a silent mutation.

This plane makes agent autonomy reviewable rather than opaque.

## Product principles

1. **The agent is the primary UX.** A user should be able to describe a feature or
   risk instead of learning framework internals first.
2. **Every phase leaves an inspectable artifact.** Important state must not exist only
   in chat context or model memory.
3. **No mandatory LLM at replay time.** Accepted tests run locally and in CI as
   deterministic code.
4. **No hidden self-healing.** A changed selector or assertion is a proposed source
   diff with cause, confidence and evidence.
5. **Provider-neutral by contract.** Agent integrations use portable skills,
   repository instructions, CLI and MCP—not a model SDK in the runner.
6. **UI-first, API-supported.** APIs seed state and provide independent oracles; the
   browser journey remains the subject under test.
7. **Uncertainty is data.** An agent may abstain by declaring `blocked_on` evidence; it
   must not manufacture certainty.
8. **Policy belongs to the owner.** Humans choose what can run or change
   automatically, not every individual click.

## Jobs to be done

- "Agent, cover this feature with durable UI tests."
- "Agent, prove this pull request did not break our critical journeys."
- "Agent, explain why this run is red and show the supporting evidence."
- "Agent, update tests safely after an intentional UI change."

These are the public product workflows. Individual locators, screenshots and pytest
hooks are implementation details inside them.

## What Testence is not

- not a general-purpose browser-use agent;
- not a recorder or low-code test editor;
- not an API-first testing platform;
- not a proprietary browser/device cloud;
- not a hosted dashboard that owns the user's tests;
- not a runtime natural-language action engine in ordinary CI;
- not an autonomous healer allowed to rewrite tests without review.

## Competitive wedge

Playwright Test Agents make "runner plus coding-agent workflow" the baseline. Testence
must therefore win on the quality of the verification contract, not on test generation
alone:

- portable, bounded evidence designed as an agent input;
- traceability from product claim to verdict;
- independent UI/API agreement checks;
- explicit permission and review boundaries;
- measurable false-green, false-red and wrong-reason rates;
- local-first tests and provider-neutral agent integrations.

The moat is **trusted closure of the agent development loop**: the agent can move from
request to proof without turning verification into an opaque model session.

## Messaging hierarchy

**Homepage category:** Agent-native UI verification.

**Headline:** UI verification built for coding agents.

**Subhead:** Give Claude, ChatGPT/Codex, OpenCode or another coding agent a feature.
Testence turns it into a reviewable plan, deterministic browser tests and
evidence-backed verdicts—without model calls in routine CI.

**Proof points:**

- deterministic replay at test-runner speed;
- structured evidence instead of a screenshot dump;
- UI actions checked against independent API state;
- reviewable repair proposals, never silent healing;
- open artifacts and no mandatory model provider.

## Success criterion

The product is agent-native when a new user can give a supported coding agent a feature
request and, without manually learning Testence's internals, receive:

1. a plan they can understand and approve;
2. a deterministic test they own;
3. a reproducible run with a complete evidence trail;
4. a typed verdict on failure;
5. a reviewable patch when maintenance is appropriate.
