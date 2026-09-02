# Agent workflow

This document defines the public Testence workflow. PlanSpec, pytest claim binding,
ledger/evidence-pack propagation, verdict validation and the portable skill pack are
implemented. Bootstrap, controlled discovery and MCP remain target parts of the current
pre-alpha.

## The transparent pipeline

```text
human intent / PR / risk
          │
          ▼
   PlanSpec (reviewable claims and scenarios)
          │
          ▼
   controlled UI discovery ──► deterministic Python test + ActionMap
          │                                  │
          └──────── discovery log            ▼
                                      Testence runner (no LLM)
                                              │
                                              ▼
                                  run.jsonl + evidence pack
                                              │
                                              ▼
                                      typed agent verdict
                                              │
                            ┌─────────────────┴────────────────┐
                            ▼                                  ▼
                     product failure                 maintenance proposal
                                                               │
                                                               ▼
                                                     review + targeted rerun
```

The rule is simple: every arrow crosses a file or a versioned protocol. The user can
stop after any phase, inspect its output and continue with another compatible agent.

## Actors and authority

The human defines the mission, acceptable risk and permission policy. The coding agent
coordinates the workflow. Testence owns deterministic execution and evidence integrity.
CI replays already accepted tests.

An agent may be autonomous inside an approved boundary, but it is never the source of
truth for whether a browser step ran or an oracle passed. The ledger is.

## End-to-end lifecycle

| Phase | Agent action | Durable artifact | Default gate |
|---|---|---|---|
| 0. Bootstrap | detects the project, validates the environment and loads the Testence workflow | project config, agent instructions, doctor result | user approves installation/config writes |
| 1. Plan | converts the feature or risk into explicit claims, scenarios, data and oracles | `specs/<feature>.md` PlanSpec | plan review for new coverage |
| 2. Prepare | checks auth, seed isolation, target safety and artifact policy | preflight result and seed references | destructive/shared-environment writes require approval |
| 3. Discover | explores a controlled browser to learn the real UI and validate candidate actions | bounded discovery log and fingerprints | navigation/actions inside approved target are automatic |
| 4. Compile | writes deterministic pytest/DSL code and project ActionMap changes | source diff with plan/claim IDs | source changes remain reviewable |
| 5. Prove | runs the new test live and verifies selectors, assertions and independent oracles | ledger, evidence and generation report | a test is not accepted only because code was generated |
| 6. Replay | runs accepted tests locally or in CI without an LLM | `run.jsonl`, summary and reports | governed by normal test permissions |
| 7. Judge | reads a bounded, redacted failure pack and classifies the result | `verdict.json` | read-only by default; uncertainty is allowed |
| 8. Propose | prepares a locator/assertion/test change when evidence indicates drift | explanation, patch and rerun scope | never applied silently |
| 9. Review | applies an accepted proposal and reruns the smallest proving scope | review decision and linked run | human or repository policy decides |
| 10. Learn | updates traceability, fingerprints and aggregate quality metrics | coverage/maintenance history | no opaque model-memory dependency |

## 1. Bootstrap

The target command is `testence agent init`. It should detect supported clients, install
portable workflow assets and avoid copying secrets into agent configuration.

The installed contract consists of:

- a short repository instruction that tells an agent when to invoke Testence;
- portable Agent Skills for `plan`, `author`, `triage` and `repair`;
- optional client adapters where discovery conventions differ;
- an Testence project config and a synthetic seed test;
- `testence doctor`, which validates Python, browser/CDP access, writable artifact paths,
  profile selection and sensitive-data settings.

The bootstrap report must list every file it created or changed.

## 2. Plan before browsing

A PlanSpec is human-readable Markdown with machine-readable identifiers. It records:

- the feature, user and business risk;
- testable claims and their priority;
- preconditions and deterministic seed data;
- positive, negative and permission paths;
- the intended UI observation;
- an independent oracle where one is available;
- exclusions, uncertainty and required approvals.

The first machine-readable version stabilizes only `id`, `title`, `source`, oracle-typed
claims, and risk-bearing scenarios. Preconditions, seed/cleanup and approvals remain in
the surrounding Markdown until the authoring corpus justifies additive schema fields.

The Markdown file contains exactly one `testence-planspec` JSON block; surrounding prose
remains free-form context for humans and agents:

```testence-planspec
{
  "schema": "testence/planspec/1",
  "id": "checkout.discount",
  "title": "Apply an eligible discount",
  "claims": [
    {
      "id": "checkout.discount.total",
      "statement": "The UI and cart API expose the same discounted total.",
      "oracles": ["ui", "api"],
      "required": true
    }
  ],
  "scenarios": [
    {
      "id": "eligible-code",
      "title": "Apply an eligible code",
      "claims": ["checkout.discount.total"],
      "risk": "false green from an optimistic UI"
    }
  ]
}
```

Validate the plan before execution and bind tests only to declared claim IDs:

```bash
testence plan validate specs/checkout-discount.md --json
```

```python
@pytest.mark.testence(
    plan="specs/checkout-discount.md",
    claims=["checkout.discount.total"],
)
def test_discount_total(ex):
    ...
```

The PlanSpec is the semantic anchor. Pytest rejects an invalid path or unknown claim at
collection, and Testence adds `plan` plus `claims` to every bound-test event, its failure
pack and the HTML report.

## 3. Discover, then compile

UI discovery is an authoring-time activity. The agent may use a browser or another
discovery backend to inspect the application and validate selectors, actions and
assertions. The result is then compiled into ordinary Python plus Testence's
intent-bearing DSL.

Discovery decisions must be inspectable: target candidates, chosen accessible identity,
rejected ambiguities and relevant fingerprints. Raw model-driven actions are not the
artifact promoted to CI.

## 4. Prove generated tests

Generated code is only a hypothesis. Before proposing it for acceptance, the agent must:

1. execute the exact generated code against the declared target;
2. confirm each planned claim has an assertion or oracle;
3. confirm seed data is isolated and repeatable;
4. exercise the intended failure when a seeded defect or negative control exists;
5. rerun green from a clean seed;
6. report uncovered claims and unresolved ambiguity.

This prevents a plausible-looking test from being mistaken for verified coverage.

## 5. Replay without an agent

Once accepted, the test runs through the current Testence/pytest runner. Routine CI has
no model dependency. Its stable outputs are the versioned ledger and renderings derived
from it; an agent can be invoked later only when judgment is useful.

This separation is what makes the economics predictable and the result reproducible.

## 6. Judge from evidence

On failure, the agent receives the smallest redacted pack that can support a decision and
fills in its `verdict.template.json`. The verdict contract is:

```json
{
  "schema": "testence/verdict/1",
  "plan_id": "checkout.discount",
  "test_id": "tests/test_checkout.py::test_discount_total",
  "verdict": "real_bug",
  "confidence": 0.91,
  "summary": "The UI showed the discount, but the cart API returned the old total.",
  "claim_results": [
    {
      "claim_id": "checkout.discount.total",
      "status": "failed",
      "reason": "The UI and authoritative API disagree.",
      "evidence": ["oracle.json#/0", "network.jsonl"]
    }
  ],
  "blocked_on": []
}
```

Allowed `verdict` values are `real_bug`, `test_bug`, `behaviour_change`, `ui_change`,
`flaky_timing` and `environment`. `test_bug` means that the product and current PlanSpec
agree while the test implementation contradicts them. `blocked_on` is the explicit
abstention channel:
it names missing evidence rather than inventing a sixth causal class. A `null` verdict
requires at least one blocker; a `passed`/`failed` claim requires references to files that
actually exist in the pack. Validation binds the verdict to the exact plan, test and
claims:

```bash
testence verdict validate runs/<run>/<test>/pack/verdict.json \
  --plan specs/checkout-discount.md --json
```

## 7. Propose; never silently heal

When the evidence points to `ui_change` or an accepted `behaviour_change`, the agent
may create a maintenance proposal.
It includes:

- the affected claim and step;
- the old and proposed target/assertion;
- fingerprint and candidate evidence;
- a cause explanation and confidence;
- the exact source diff;
- the smallest rerun that can validate it.

Applying the patch is a separate permissioned action. Acceptance or rejection is stored
as quality feedback, but never as hidden runtime behavior.

## Integration contract

The portable core should follow the open Agent Skills convention and remain usable from
the CLI. Client-specific packaging is intentionally thin:

| Client | Discovery and instruction surface | Testence integration |
|---|---|---|
| Codex / ChatGPT | project `AGENTS.md`, skills and an optional plugin/MCP server | universal skills plus typed Testence tools |
| Claude Code | `CLAUDE.md`, Agent Skills, plugins and MCP | the same skills, a thin instruction shim and the same MCP contract |
| OpenCode | `AGENTS.md`, `.agents/skills` and MCP | the same skills and MCP contract |
| other agents | Agent Skills when supported, otherwise repository docs and CLI | no runner or artifact-format fork |

Skills define **when and in what order** to use Testence. MCP or CLI tools perform
**bounded actions** and return structured data. They should not duplicate business
logic from the runner.

The initial MCP surface should be small and task-oriented:

- `project_status` — inspect configuration, capabilities and safety state;
- `plan_validate` — validate a PlanSpec and traceability IDs;
- `session_start` — create a controlled authoring session;
- `run` — execute a declared scope and return run/artifact references;
- `failure_pack_get` — return a bounded pack for a failed test;
- `verdict_submit` — validate and store a typed verdict;
- `repair_propose` — produce a reviewable proposal and targeted rerun scope.

Source mutation should initially remain an ordinary agent edit governed by the host
client's permissions. Testence does not need a privileged generic file-editing tool.

## Permission model

| Action class | Suggested default |
|---|---|
| read project config, plans and redacted evidence | allow |
| validate a plan or inspect project status | allow |
| browse and run against an explicitly approved local/test target | allow for that target |
| create isolated seed data through a declared adapter | allow when reversible |
| write plans or generated tests | produce a visible diff |
| change an accepted assertion or locator | require proposal plus proving rerun |
| touch shared/production data, weaken an oracle or expose unredacted evidence | explicit approval or deny |

The policy belongs in repository configuration so the same boundaries survive a change
of agent client.

## What exists today

| Capability | Current pre-alpha state |
|---|---|
| deterministic pytest/Playwright execution | implemented |
| intent-bearing steps and element fingerprints | implemented |
| versioned event ledger and evidence packs | implemented |
| same-session API oracles | implemented |
| verdict taxonomy and reviewable heal-proposal primitives | implemented |
| HTML, Allure and CTRF rendering from the ledger | implemented |
| PlanSpec schema, pytest binding and traceability through ledger/pack/report | implemented |
| portable `plan`, `author`, `triage` and `repair` skills | implemented and packaged |
| cross-client bootstrap and safe skill updates | to build |
| verdict schema, pack template and CLI validation | implemented |
| managed verdict persistence and agent-facing MCP | to build |
| systematic redaction and permission policy | P0 release blocker |

The public alpha is not agent-native until one supported agent can complete the entire
golden path from feature request through evidence-backed result using this contract.

## Why this shape is portable

The major coding-agent ecosystems already distinguish durable workflow instructions
from callable tools. OpenAI describes skills as repeatable workflows and MCP as typed
tool access; Claude Code exposes the same combination of instructions, Agent Skills and
MCP; OpenCode discovers portable skills and project instructions. Testence can therefore
ship one workflow and one tool protocol instead of embedding a proprietary agent.

References:

- [OpenAI plugin architecture](https://developers.openai.com/plugins/concepts/plugins)
- [OpenAI skills](https://developers.openai.com/plugins/concepts/skills)
- [OpenAI MCP servers](https://developers.openai.com/plugins/concepts/mcp-server)
- [OpenAI project instructions with AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
- [Claude Code extension overview](https://code.claude.com/docs/en/features-overview)
- [OpenCode skills](https://opencode.ai/docs/skills)
- [OpenCode project instructions](https://opencode.ai/v2/docs/instructions)
- [Playwright Test Agents](https://playwright.dev/docs/test-agents)
