## What changed

<!-- Describe the user-visible or architectural outcome. -->

## Proof

- [ ] Tests cover the change and can fail for the intended reason.
- [ ] `uv run ruff format --check src tests bench scripts examples`
- [ ] `uv run ruff check src tests bench scripts examples`
- [ ] `uv run mypy src scripts`
- [ ] `uv run pytest -q`
- [ ] `uv run pytest examples -q --testence-headless`
- [ ] Relevant benchmark, evidence schema and ADR snapshots were updated.

## Review (a person checks these; an agent reports, never ticks)

- [ ] Plans and claims describe the intended behaviour, not what the code does today.
- [ ] Expected values come from the plan or the test's seed, not from an observed run.
- [ ] No claim, binding or oracle was weakened to obtain green (list in AGENTS.md).

## Risk and rollback

<!-- Note compatibility, evidence/privacy impact, and the smallest rollback. -->
