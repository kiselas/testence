# Authoring readiness handoff — 14 September 2026

Status: implemented and locally verified on `codex/authoring-readiness`. Base revision:
`e2ef53b416fb40cb7591b88c8ce98d54cfcec276`.

## Outcome

`testence plan prepare <plan> --project <root> --profile <profile> --json` now performs
a browser-free readiness pass before discovery. It loads the selected PlanSpec and
profile, compares scenario capabilities with the backend, checks every required
assertion's oracle adapter, executes shared read-only prerequisites once, and returns a
versioned per-scenario `ready` or `blocked` report with phase and check timings.

The profile's `readiness` object supports:

- environment-variable presence without reading values into the report;
- project-relative file presence;
- GET-only HTTP status and optional JSON Pointer/value checks;
- explicit `api`, `custom`, `a11y`, and `visual` oracle adapters;
- scenario-to-check mappings, strict by default.

An absent readiness object is a valid blocked report so an agent gets actionable output
instead of a configuration exception. Invalid fields, unknown check references, unsafe
file paths and malformed URLs fail configuration with exit 2. Valid blockers exit 3.
The portable author skill now requires this gate before browser discovery.

Follow-up commit adds opt-in project-owned fix recipes. `--apply-fixes` invokes a bounded
argument array directly without a shell, never records stdout/stderr, and reruns the
failed check. The report distinguishes command execution from the resulting readiness;
a zero exit code alone cannot make a scenario ready.

Follow-up validation:

```text
uv run pytest tests/test_readiness.py tests/test_agent_skills.py tests/test_contracts.py -q --basetemp=.tmp-pytest-readiness-fixes-0914b
45 passed in 2.95s

uv run ruff format --check src tests bench scripts
164 files already formatted

uv run ruff check src tests bench scripts
All checks passed

uv run mypy src scripts
Success: no issues found in 68 source files

uv run pytest -q --basetemp=.tmp-pytest-readiness-fixes-full-0914
439 passed, 2 skipped in 164.77s
```

## Scope and evidence

This is framework infrastructure and has no new PlanSpec or claim ID. It was motivated
by `nextdish.qr_menu.ui` and `nextdish.admin.ui`. Against their current unconfigured
profiles, the command classified all eight scenarios in each plan in about 140 ms and
134 ms respectively. It named the missing `api`, `custom`, and `a11y` adapters and the
missing scenario mappings before a browser was opened.

Focused validation:

```text
uv run pytest tests/test_readiness.py tests/test_agent_skills.py tests/test_contracts.py -q --basetemp=.tmp-pytest-readiness-0914e
43 passed in 2.89s

uv run ruff format --check src/testence/readiness.py src/testence/cli.py tests/test_readiness.py tests/test_contracts.py tests/test_agent_skills.py
5 files already formatted

uv run ruff check src/testence/readiness.py src/testence/cli.py tests/test_readiness.py tests/test_contracts.py tests/test_agent_skills.py
All checks passed

uv run mypy src/testence/readiness.py src/testence/cli.py
Success

uv run ruff format --check src tests bench scripts
164 files already formatted

uv run ruff check src tests bench scripts
All checks passed

uv run mypy src scripts
Success: no issues found in 68 source files

uv run pytest -q --basetemp=.tmp-pytest-authoring-readiness-full-0914
437 passed, 2 skipped in 172.83s
```

No browser run ID was created because the new command intentionally stops before
browser startup. No product or external state was mutated.

## Changed files

- `src/testence/readiness.py`
- `src/testence/cli.py`
- `src/testence/contracts/versions.py`
- `src/testence/contracts/__init__.py`
- `src/testence/contracts/schemas/readiness-report.schema.json`
- `src/testence/agent/skill-pack.json`
- `src/testence/agent/skills/testence-author/SKILL.md`
- `src/testence/agent/skills/testence-author/references/proof-gates.md`
- `tests/test_readiness.py`
- `tests/test_contracts.py`
- `tests/test_agent_skills.py`
- `README.md`, `docs/en/agent-workflow.md`, `docs/ru/agent-workflow.md`
- `docs/en/CHANGELOG.md`, `docs/ru/CHANGELOG.md`

The existing untracked NextDish PlanSpecs, tests, reports and `testence.json` were not
added to this framework change.

## Remaining uncertainty and next proof

This slice removes wasted browser starts and makes blockers machine-readable. It does
not create application-specific seeds, infer whether arbitrary API/custom oracle code
exists, or repair the environment. Those remain explicit project-adapter work.

After NextDish adds its readiness mappings and adapters, the next proving commands are:

```powershell
uv run testence plan prepare specs/nextdish-qr-menu-ui.md --project . --profile nextdish-qr-local --json
uv run testence plan prepare specs/nextdish-admin-ui.md --project . --profile nextdish-admin-local --json
```

Only scenarios returned as `ready` should proceed to discovery and authoring.
