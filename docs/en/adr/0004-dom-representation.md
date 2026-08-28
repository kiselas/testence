# ADR-0004: ARIA snapshot as the DOM evidence format

Status: proposed — default until experiment E2 (ablation) settles it

## Context

"Log the page state" needs a concrete format. It must be small enough to live inside
a token-budgeted evidence pack (≤ 8K tokens), diffable between steps, and carry
enough structure for an agent to judge failures without screenshots. Manual-run
lesson: "read texts, don't look at pictures" — text beats pixels for agent triage.

## Options (to be settled by E2 on the failure corpus)

| | ARIA snapshot (`aria_snapshot()`) | CDP DOMSnapshot | `innerText` dump | screenshot |
|---|---|---|---|---|
| Size (est.) | small–medium: semantic tree only | large: layout boxes, styles | smallest: text only | largest; tokens explode |
| Structure for judging | roles+names+states — what a user *can do* | full but noisy | none (no roles/states) | visual only |
| Diffability | YAML, line-diffable | JSON, noisy diffs | line-diffable | no |
| Stability across renders | high (semantic) | low (layout jitter) | medium | low |
| Cost to produce | 1 call, in Python API | 1 CDP call | 1 eval | 0.1–30 s (SPA renderer stalls burned us) |

## Decision (default, pending E2)

ARIA snapshot as the pack's `aria.txt` and the per-step snapshot source; screenshots
only *on failure, for humans* — agents start from text. E2 criterion
(pre-registered): ARIA stays if `verdict_accuracy` ≥ alternatives at ≤ 50% of their
token cost. E3 will additionally test between-step *diffs* vs full snapshots
(accept if ≥ 60% token cut costs ≤ 2 p.p. accuracy).

## Consequences

- Rich-canvas areas (xyflow scheme) are under-represented in ARIA → the ActionMap
  must expose canvas state via app-level reads (API oracle, DOM queries), which is
  the correct layer anyway.
- The `box` option (bounding boxes in ARIA YAML, shipped 2026 "for AI consumption")
  is available if verdicts need geometry — costed, not default.

## Tripwire

≥ 3 corpus failures where the agent's wrong verdict is attributable to missing
visual/geometry information → re-run E2 including screenshot and `box` variants.
