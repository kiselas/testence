# Glossary

The words Testence's reports and commands use, in the order you meet them.

| term | meaning |
|---|---|
| `ex` | the test fixture that drives the browser: recorded steps, exact checks, already logged in |
| `Target` | how a step names an element: role and accessible name first, then label, test id, CSS |
| step | one recorded action or check with an `intent` sentence |
| run | one `testence run` or pytest session; `runs/<id>/` holds its ledger and packs |
| ledger | `run.jsonl`, the append-only record of the run ([evidence schema](evidence-schema.md)) |
| evidence pack | what a failed attempt leaves: page snapshot, API traffic, console, proposed fix |
| oracle | an independent observation that proves a result, usually the API read as the same user |
| PlanSpec | an optional file of claims and assertions a test can be bound to |
| claim | one sentence a test proves: subject, action, observable result |
| assertion | a check bound to a claim (`assertion_id`, `claim_id`) so the proof is countable |
| `verified` | every required assertion bound to the test passed |
| `violated` | an assertion failed: the product disagrees with the claim |
| `inconclusive` | the evidence could not decide (login lost, API unreachable, an empty or non-JSON answer) |
| `unverified` | the test ran but no assertion was bound to a claim; not a failure |
| mocked | a request answered by `ex.route`; it never reached the server and proves nothing about it |
| actor | another user in the same test (`testence_actor`) with its own session |
| heal proposal | a reviewable suggestion for a selector that no longer matches; never applied silently |
| skill | an instruction file an agent client loads (`testence agent install`) |
