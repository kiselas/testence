# ADR-0020: Explicit, manifest-backed application CLI

Status: accepted (2026-09-06)

## Context

The library exposed low-level pytest and contract helpers, but onboarding and agent
clients had to infer paths, select the latest run, or copy files directly. Those
shortcuts make run identity ambiguous and turn an update or verdict submission into an
unreviewable filesystem mutation.

## Options compared

We compared shell recipes, an interactive wizard, and small application services behind
stable CLI commands. Shell recipes differ across Windows and Linux and cannot emit one
contract. A wizard is difficult for agents to replay and inspect.

## Decision

The stable application surface is:

- `testence doctor --root <project> --json` checks Python, settings, packaged schemas,
  Chromium and workspace access without printing credentials;
- `testence init <project> --json` creates only missing scaffold files and binds their
  exact bytes in `testence/scaffold-manifest/1`; conflicting files fail;
- `testence run --project <project> --run-id <id> -- [pytest args]` executes an explicit
  scope. With no pytest arguments it runs only the hidden synthetic proof;
- `testence inspect <run-dir> --json` requires an explicit run directory and reports the
  reconciled execution, assurance and integrity state;
- `testence verdict submit <candidate> --plan <plan> --pack <pack> --json` validates all
  bindings, atomically writes `verdict.json`, and records
  `testence/verdict-submission/1`. A different existing verdict is never overwritten.

Machine JSON goes to stdout and user errors return exit 2 without a traceback. `init`
does not edit pytest configuration or add the hidden example to existing test paths.

## Consequences

The same commands work from a wheel on Windows and Linux, and agent clients can inspect
manifests before changing files. Every operation names its project, run, plan or pack;
there is no "latest" lookup. Agent skill installation and update remain a separate
manifest-backed layer.

## Tripwire

Revisit the command grouping if two independent agent clients cannot complete the same
wheel-only workflow, or if a scaffold update cannot be expressed as a reviewed
manifest diff without overwriting user changes.
