# T22 real agent clients implementation receipt

Date: 2026-09-06. Status: locally implemented and verified.

## Delivered behavior

`testence agent install` copies the packaged `testence/skill-pack/1` into the
documented project locations for Codex (`.agents/skills`) and Claude Code
(`.claude/skills`). `.testence/agents.json` records the exact pack and file hashes.
An update replaces only a file still equal to the last installed hash; a local edit is
preserved and reported as a conflict. `testence agent verify` detects missing or
changed files without repairing them. Both commands have machine-readable receipts
and separate invalid-state (`2`) and drift/conflict (`3`) exits.

Two public schemas describe the install state and command receipt. The wheel includes
the manifest, all four skills, client-neutral references and optional Codex metadata.

## Real-client consumer

[`outputs/.../t22-agent-consumer`](../../../outputs/audit-2026-09-06-followup/t22-agent-consumer/)
contains the installation receipts, exact fixture digest, two copies of one immutable
evidence pack, client outputs and validated submission receipts.

| Client | Version | Invocation boundary | Result |
|---|---:|---|---|
| OpenAI Codex CLI | `0.153.4` | ephemeral session; installed skill read under reviewed read-only commands; JSON Schema output | `real_bug`, submitted |
| Claude Code | `2.1.117` | no session persistence; no tools; project skill `/testence-triage`; JSON Schema output; USD 0.50 cap | `real_bug`, submitted |

Both verdicts bind `pack_digest`
`sha256:baae1a8fff0481aeedb60daf9b92cdf2f4f41f2f7f7b1595a030f91e20eb977e`
and the same plan/run/attempt/proof identities. Testence independently accepted both
with `testence verdict submit`; the verdict bytes may differ because summaries and
confidence are client judgments.

## Verification

| Check | Observed |
|---|---|
| Installer/contract unit subset | `36 passed` |
| Ruff | focused implementation passes |
| mypy | success, 54 source files |
| Project install/verify | 12 exact files per client; no drift |
| Real verdict validation | two `testence/verdict-submission/1` receipts |

The first diagnostic Codex run used an overly restrictive policy that rejected its
attempt to read `SKILL.md`; it was superseded by the recorded run in which Codex read
the installed skill and reference before producing the submitted verdict. External
clients were not allowed to edit product or test source.
