# DemoSpec: “Green test, false outcome”

Status: **implementation contract**. Version: `0.1`. Snapshot: 2026-08-28.
Owner: Product Owner together with the demo-repository maintainer.

This document defines one launch demo. Any scenario change must preserve the central
causal chain and remain compatible with the [Launch Thesis](launch-thesis.md) and
[Launch Benchmark Protocol](benchmark/launch-protocol.md).

## Goal

Within the first 90 seconds, the viewer must see and understand three facts:

1. a regular UI-only check is green;
2. the user outcome was not actually achieved;
3. Testence finds the mismatch, connects it to a product claim, and returns a reviewable
   verdict.

After the extended demo, the viewer should also know that the accepted test replays
without an LLM and that test changes are never applied invisibly.

## Audience and desired reaction

The main audience is a developer using Codex/ChatGPT, Claude Code, or OpenCode. They may
know Playwright at the level of ordinary end-to-end tests but need no Testence knowledge.

Desired reaction:

> “I also treated the toast and card as enough proof. This is a concrete class of false
> green, and the report shows not just a failure but why the outcome is false.”

Undesired reaction:

> “The authors deliberately wrote a poor Playwright test to beat Playwright.”

The UI-only test is therefore called a baseline pattern, not a “competitor test.” Its
code, requirement, and constraints are shown in full.

## Application scenario

The public demo repository contains a small **Release Board** application:

- a user creates a blocker with a title and severity;
- the UI optimistically adds a card and shows `Blocker created`;
- the browser sends `POST /api/blockers`;
- independent truth is available through `GET /api/blockers/:id` in the same session;
- the application has explicit, versioned defect patches and a healthy control.

The main seeded defect is `acknowledged-but-not-persisted`:

1. `POST` returns success and an ID;
2. the UI keeps the card in client state and shows a toast;
3. the record is absent from authoritative storage;
4. `GET` for the same user returns `404` or a list without the ID.

This is a plausible model of optimistic UI, a failed transaction, an asynchronous
write, or disagreement between write and read paths. The defect is a minimal public
patch, not hidden benchmark-harness logic.

## Requirement and PlanSpec

One user request is used for the video, live demo, and benchmark:

> “Verify release-blocker creation. After save, the card must appear in the UI, the
> record must exist for the current user, and it must remain available on a fresh read.
> Produce a durable test and prove the outcome.”

Minimum PlanSpec claims:

| ID | Claim | Evidence source |
|---|---|---|
| `blocker.create.requested` | the browser sent the agreed create request | network event |
| `blocker.create.visible` | the new card is visible to the user | semantic UI snapshot/assertion |
| `blocker.create.persisted` | the record exists in authoritative storage | same-session API oracle |
| `blocker.create.consistent` | UI and API values agree | UI/API diff |

The agent may add scenarios, but it may not remove `persisted` or replace it with only a
toast check. Plan review makes that loss visible before test generation.

## Two lines of proof

### UI-only baseline

The public baseline checks form submission, the toast, and the card. It must pass
reliably on the main defect. This demonstrates a limitation class, not a product ranking.

### Testence proof

The test performs the same user journey and also:

- records intent and claim IDs;
- confirms that the create request left the browser;
- reads the API as the same user;
- compares ID, title, and severity with the UI;
- builds a bounded evidence pack on mismatch;
- returns `real_bug` rather than retrying the click or weakening an assertion.

Both lines use the same target, state, browser family, and test data.

## Storyboard

### Hero cut — 90 seconds

| Time | Screen | Content |
|---:|---|---|
| 0–10 s | Requirement | One coding-agent request: produce a durable proof of blocker creation |
| 10–22 s | PlanSpec | Four claim IDs, highlighting `persisted` and the independent API oracle |
| 22–35 s | Split view | UI-only baseline is green; the application shows a toast and card |
| 35–48 s | Truth reveal | API/read storage has no record; the exact defect patch is shown |
| 48–68 s | Testence report | Red Proof Card: failed claim, UI state, request, API `404`, diff, and `real_bug` |
| 68–82 s | Agent action | The agent changes product code, not the test, and runs the smallest scope |
| 82–90 s | Final proof | All claims are green; “Plan with AI. Replay deterministically. Judge by evidence.” |

The edit must not hide waits or retries. Accelerated sections are labeled, and an
uninterrupted real-time recording is available alongside the cut.

### Live demo — 5–7 minutes

1. Clone a clean demo repository and show the one-command bootstrap.
2. Run `testence agent init --client <client>` and show the created-file manifest without
   manually reading the files.
3. Give the agent the requirement and approve a short PlanSpec.
4. Show the generated repo-owned test and claim IDs.
5. Run the baseline and Testence on the frozen defect.
6. Open the local report from a link in structured CLI output.
7. Ask the agent to fix the cause and show the application diff.
8. Run a targeted rerun, then execute the same test without the agent using the ordinary
   CI command.

Target bootstrap interface, not yet implemented:

```bash
uv sync --locked
uv run testence doctor
uv run testence agent init --client codex
uv run testence demo run --scenario acknowledged-but-not-persisted
```

If the launch package offers a shorter safe command, it may replace the first two lines,
but the locked environment and diagnostics must remain available.

### Extended proof — 12–15 minutes

After the main fix, activate `accessible-name-changed`:

- application behavior is correct, but the button's semantic name intentionally changed;
- Testence classifies the failure as `ui_change`;
- repair is a source proposal with evidence, confidence, and target scope;
- the user accepts the diff;
- Testence performs a targeted rerun linked to the proposal.

This episode proves the distinction between a real bug and safe UI drift. It stays out of
the first 90 seconds so it does not dilute the primary false-green moment.

## Proof Report as the visual hero

The main frame is not a terminal or chatbot. It is a local self-contained report with
three synchronized areas:

```text
┌──────────────────── Proof Card ────────────────────┐
│ real_bug · high confidence · claim persisted      │
├──────────────┬──────────────────┬──────────────────┤
│ User intent  │ Evidence timeline│ Independent truth│
│ create item  │ click → POST 201 │ GET → 404        │
│ UI: visible  │ toast → UI card  │ diff: missing ID │
├──────────────┴──────────────────┴──────────────────┤
│ Next safe action: fix product · rerun 1 test      │
└────────────────────────────────────────────────────┘
```

Required properties:

- one screen answers “what was promised, what happened, and why this verdict?”;
- the claim ID remains visible from PlanSpec through final proof;
- evidence has provenance and timestamps;
- redaction status is visible and canary values never appear;
- the report opens locally without an account or external network;
- raw JSONL and the machine-readable verdict sit alongside it rather than being hidden.

## Demonstration truth and honesty

The demo is invalid if any of the following is true:

- the baseline and Testence receive different state or requirements;
- the defect is enabled only for the baseline arm or hidden from the published repo;
- the verdict is hard-coded to the scenario name;
- the video shows a different run than the attached raw artifacts;
- Testence changes the assertion so a real defect becomes green;
- the failure is found only because Testence knows the seed flag;
- secrets or user data appear in the report.

Every public run publishes its commit SHA, scenario ID, environment manifest, PlanSpec,
source diff, test, ledger, verdict, and report checksum.

## Demo assets

Before launch, there must be:

- a separate public demo repository;
- one healthy control and two small reviewable defect patches;
- one run command on Windows, Linux, and macOS, or an honestly stated matrix;
- a recorded real-time run and a 90-second cut;
- a static Proof Card screenshot for the README and articles;
- an ASCII/text terminal fallback;
- a raw artifact bundle with checksums;
- a script that repeats only the deterministic portion without a coding agent;
- a “limitations and how this demo can mislead” section.

## Acceptance criteria

The demo is ready when:

- five consecutive frozen runs produce the same outcome and right reason;
- the baseline is green and Testence red on the main defect, while both are green on the
  control;
- a new user reproduces the scenario in at most 10 minutes without signup;
- a coding agent reaches the first trustworthy proof in at most 15 minutes;
- Testence becomes green after the product fix without weakening claims;
- the extended drift produces a proposal but no hidden change;
- the canary scan of every artifact is green;
- two external people reproduce the demo from the README;
- the entire hero cut can be checked against one published run ID.

## Out of scope for the launch demo

- comparing ten commercial platforms;
- a cross-browser matrix as the main story;
- visual regression, mobile device cloud, or an accessibility audit;
- generating dozens of tests;
- MCP as a requirement;
- a hosted dashboard;
- `200× faster` or “zero false greens in general” claims.

These capabilities may appear in a deep dive only when already proved, but must not
distract from the one message: **a green UI is not yet proof of the achieved outcome**.

## Implementation order

1. Freeze the demo repository, requirement, claims, and two truth patches.
2. **Done:** implement PlanSpec/verdict schemas and claim propagation.
3. Assemble one complete flow in one coding agent.
4. Build the Proof Card and redaction gate.
5. Add the baseline runner and frozen demo command.
6. Complete five internal and two external reproductions.
7. Record the final hero cut only after that.
