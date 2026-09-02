## What changed

<!-- Describe the user-visible or architectural outcome. -->

## Proof

- [ ] Tests cover the change and can fail for the intended reason.
- [ ] `uv run ruff format --check src tests bench`
- [ ] `uv run ruff check src tests bench`
- [ ] `uv run mypy src/testence bench/react_latency.py bench/warm_runner_latency.py`
- [ ] `uv run pytest -q`
- [ ] Relevant benchmark, evidence schema and ADR snapshots were updated.

## Risk and rollback

<!-- Note compatibility, evidence/privacy impact, and the smallest rollback. -->
