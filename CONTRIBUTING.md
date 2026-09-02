# Contributing to Testence

Testence is pre-alpha. Contributions are welcome when they strengthen its central
contract: agents may plan, author and judge, while ordinary replay stays deterministic,
reviewable and independent of any model provider.

## Before opening code

1. Search existing issues and ADRs.
2. For a new capability, open a proposal that states the user pain and measurable
   acceptance criteria.
3. For an architectural change, record the alternatives and a tripwire in an ADR.
4. Never include credentials, browser profiles, private target URLs or unredacted
   production evidence.

Small bug fixes can go directly to a pull request. Large features should agree on the
proof contract first.

## Development setup

```bash
git clone git@github.com:kiselas/testence.git
cd testence
uv sync --locked --extra dev --extra parallel
uv run playwright install chromium
uv run pytest -q
```

The supported development platforms are Windows and Linux with Python 3.10 or newer.

## Required checks

```bash
uv run ruff format --check src tests bench
uv run ruff check src tests bench
uv run mypy src/testence bench/react_latency.py bench/warm_runner_latency.py
uv run pytest -q
```

Run the narrowest relevant benchmark when changing waits, engine behaviour, evidence
capture or runner lifecycle. Do not improve a number by weakening the scenario or its
oracle. Update the checked-in result, command and environment together.

## Design rules

- Tests express user intent; engines remain replaceable behind the protocol.
- No LLM call belongs in ordinary execution.
- Evidence is append-only, bounded, versioned and safe to inspect.
- Healing produces a proposed diff, never a silent runtime rebind.
- New dependencies need a clear benefit and a permissive license.
- Warm authoring optimizations must agree with fresh-process validation.

## Pull requests

Keep commits reviewable and explain the outcome before implementation details. A pull
request should include tests that demonstrate the failure mode, the verification
commands actually run, and any compatibility or privacy consequences.
