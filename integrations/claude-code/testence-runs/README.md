# testence-runs — a Claude Code pane for Testence runs

A Claude Code mod (a plugin of function hooks) that keeps a pane beside the chat with the newest
Testence run of a project: every selected case, queued, running with the step it is on, passed or
failed with the first line of the reason, and the run's totals. The pane opens by itself when a new
run starts, and a toast says how the run ended. It reads only `runs/<run>/run.jsonl`, the ledger every
Testence run writes, so it works for any Testence project and changes nothing in it.

## What it shows

```
r-20261102-115736-e3fe5a · dev3 · running
3/5 · ✓ 2 ✗ 1
✓ 12 drag leaves own group and joins another  test_drag.py 20.2 s
✗ 13 drag stays in group …                    test_drag.py 15.0 s
   AssertionError: assert {'green'} == {'red'}
● 14 drag single rule of group                test_drag.py
   step 7: drag П07 by its handle onto the row of П01
○ 15 reorder warning says nothing about groups test_drag.py
```

A run that wrote nothing for two minutes without `run.end` (a Ctrl+C, a killed worker) reads as
`interrupted?`.

## Setup

1. Load the mod: `claude --plugin-dir <this folder>`, or name the folder in `CLAUDE_CODE_PLUGIN_DIRS`
   (for a session the desktop app starts), or add the repository as a marketplace and install it.
2. Point it at a project's runs: `/testence-runs C:/path/to/project/runs`. The folder is kept across
   sessions. Without it the mod follows `runs/` under the session's working directory, or the
   `runsDir` option (`pluginConfigs.testence-runs.options.runsDir` in settings).
3. `/testence-runs` alone opens the pane on the newest run.

`run.jsonl` grows past what one file read of a mod takes (about 10 MB for 60 cases), so the mod
summarizes it with Python (`python` on `PATH`, or the `python` option): Testence needs Python anyway.

## How it works

`hooks/register.tsx` polls the runs folder once a second (`$.clock.every`), re-reads only when the
newest run's ledger changed size, keeps the summary in `$.state` and draws it in a `Pane`. The summary
takes `run.start` (profile), `collection.end` (the selected cases), `test.start`, `step.start` (the
current step), `test.end` (status, duration, error) and `run.end` (run status, duration).

## Checks

With a Claude Code build that has function hooks (2.1.309 or newer):

```bash
claude plugin validate integrations/claude-code/testence-runs
claude plugin test integrations/claude-code/testence-runs
```

Type-checking takes the API declarations the engine lays in `.claude-plugin/types/` once it has loaded
the mod (ignored by git): `tsc -p integrations/claude-code/testence-runs` with a `tsconfig.json` that
extends `.claude-plugin/types/tsconfig.json`.
