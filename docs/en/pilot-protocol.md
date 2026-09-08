# R1 pilot protocol

The R1 adoption gate needs five new users across three external teams. One team must
operate three projects through one QA owner, one must complete a live TestOps selective
launch, and at least two people must independently reproduce the frozen demo. Invites,
credentials and external messages are handled by the product owner outside automation.

Each participant starts from the same candidate wheel digest and an empty working
directory. Record consent, participant/team pseudonyms, OS/Python/browser versions,
start/end times, help interventions, command exits and resulting run IDs. Never retain
credentials, production URLs, raw screenshots or personal data in the public receipt.

The session tasks are:

1. Install the wheel and Chromium; run `testence doctor --json`.
2. Run `testence demo run --project testence-demo --json` and identify why the second
   case fails.
3. Install one agent client and verify its managed skill files.
4. Add a second scenario with a requirement claim and independent oracle.
5. Inspect the run and explain one actionable result without author help.
6. For the designated teams, apply the quality pack across three repositories or run
   the TestOps selection/upload path.
7. Return during the next calendar week and repeat one useful run.

Acceptance is 4/5 users reaching trustworthy proof within 15 minutes, at least 2/3
teams adding the second scenario unaided, all required team-specific tasks completed,
two independent demo reproductions, and recorded week return. Report setup minutes, QA
review/triage minutes, accepted scenarios, gaps and overrides. A failed or abandoned
session stays in the denominator.

Use `docs/pilot/session-template.json` for each sanitized receipt. The final pilot
summary names the candidate digest and lists every receipt digest; empty or author-run
templates do not satisfy G7.
