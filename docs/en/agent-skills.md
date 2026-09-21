# Portable Agent Skills

Testence ships one versioned skill pack inside the Python distribution. The pack is the workflow layer between a user's intent and Testence's deterministic contracts; it contains no model SDK, provider credentials, or client-specific business logic.

Current pack: `testence/skill-pack/1`, version `0.1.4`.

## The four phases

| Skill | Invoke when | Durable completion condition |
|---|---|---|
| `testence-plan` | a feature, risk, issue, or change needs coverage intent | a validated `testence/planspec/2` with reviewed claims and oracles |
| `testence-author` | an approved plan must become executable coverage | deterministic pytest code proved green → intended red → green, with claim bindings |
| `testence-triage` | a bound run failed and has an evidence pack | a claim-complete, pack-bound `testence/verdict/2` or explicit abstention |
| `testence-repair` | a validated verdict permits test maintenance | a visible minimal diff and targeted proof without weakened claims |

The phases are separate because their authority differs. Planning should not mutate code, triage should not quietly repair it, and repair must refuse to rewrite a test around a `real_bug`.

## Source of truth

The canonical files live under `src/testence/agent/skills/`; `skill-pack.json` records the pack version, public contract versions, phase inputs/outputs, and safe update policy. They are package data, so an installed wheel contains the exact same assets as a source checkout.

Client locations are installation adapters, not forks:

| Client | Project adapter |
|---|---|
| Codex | copy/link the four directories into `.agents/skills/` |
| OpenCode | reuse the same `.agents/skills/` installation |
| Claude Code | copy/link the same directories into `.claude/skills/` |
| ChatGPT or managed distribution | bundle the same directories as plugin skills |
| other clients | use an Agent Skills directory when supported, otherwise link to the public workflow docs and CLI |

`agents/openai.yaml` adds optional Codex UI metadata. Other clients ignore it; workflow behavior remains in standard `SKILL.md` plus references.

## Install and verify

Install the exact bundled pack into one or both project adapters:

```bash
testence agent install --project . --client codex --client claude --json
testence agent verify --project . --client codex --client claude --json
```

Codex receives `.agents/skills/<skill>/`; Claude Code receives
`.claude/skills/<skill>/`. Both are copied from the installed Testence distribution.
The command records the pack digest and every accepted file digest in
`.testence/agents.json`. Exit `0` means installed/valid, `2` means invalid input or
state, and `3` means a local conflict or drift.

The implemented update contract:

1. read the bundled manifest rather than download mutable prompts at runtime;
2. accepts only explicit supported clients and reports every target path in its receipt;
3. install identical skill content through thin adapters;
4. record pack version, adapter, installed paths, and SHA-256 of every installed file in `.testence/agents.json`;
5. on update, replace a file only when its current hash matches the previously installed hash;
6. preserve a locally modified file and report a repeatable conflict for manual merge;
7. write state atomically and report installed, unchanged, and conflicted files;
8. never place credentials, target URLs, user data, or generated evidence inside a skill.

Pack versions follow SemVer. Any instruction or reference change increments the pack version. Public PlanSpec, evidence, and verdict schemas retain their own versions; a breaking contract change requires a new contract version and a compatible skill-pack release.

## Release gate

Every skill release is tested with:

- direct invocation by skill name;
- indirect natural-language requests matching the description;
- incomplete input that should produce a useful gate or abstention;
- a nearby request that must not trigger the skill;
- a golden end-to-end path across plan → author → triage → repair;
- package/wheel checks proving all files and the manifest are present;
- client smoke tests for discovery and reference loading.

Metrics are task success, contract-valid output, policy violations, unnecessary tool calls, time, and tokens. Prompt polish is accepted only when these measurements improve without weakening safety gates.

## Current boundary

The portable pack, conflict-safe client installer, integrity verifier, metadata,
manifest, and wheel distribution checks are implemented. The required release receipt
must exercise the installed `testence-triage` skill with real Codex and Claude Code
clients against one immutable evidence pack, then validate and submit both verdicts.
That independent client receipt remains pending.
Broader trigger precision and the independent benchmark corpus remain release gates.

References: [OpenAI skills](https://learn.chatgpt.com/docs/build-skills), [Claude Code skills](https://code.claude.com/docs/en/skills), [OpenCode skills](https://opencode.ai/docs/skills).
