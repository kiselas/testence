# I3 baseline: interactive clicking vs the runner

Same page, same six steps (open → click → assert → type → click → assert), measured
once per arm on 2026-08-25.

| arm | wall-clock | per step |
|---|---|---|
| agent clicking via browser MCP | 70.6 s | 11 760 ms |
| `testence` runner (script) | 0.353 s | 59 ms |
| **ratio** | **200×** | |

## What the MCP arm included

Nine tool calls for six steps, and that gap is the finding rather than sloppiness:
two `read_page` calls to learn the refs, a viewport resize, and two clicks that
failed outright because the pane opened at 0×0. The manual playbook describes the
same friction in different words ("the canvas eats clicks", "screenshots time out")
— it is the normal cost of putting a model in the execution path, not an artifact
of this measurement.

## Reading the number honestly

**200× is the measured per-step overhead on this synthetic scenario, not the speed-up
of a real suite.** Application latency does not shrink: a target that takes 1.5 s to
return a page takes 1.5 s in both arms. End-to-end speed-up must therefore be measured
on a public, reproducible suite before it is used as a product claim.

Two further caveats. The scenario is synthetic and simple, so the MCP arm is
*flattered*: a real application means larger snapshots and more deliberation per
step. And the script arm excludes browser launch (~1.7 s), which is paid once per
suite rather than per case.

Raw numbers: `i3_baseline.json`, `i3_baseline_script.json`.
