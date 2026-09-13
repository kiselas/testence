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
uv sync --locked --extra dev --extra parallel --extra visual
uv run playwright install chromium
uv run pytest -q
```

The supported development platforms are Windows and Linux with Python 3.10 or newer.

## Required checks

```bash
uv run ruff format --check src tests bench scripts
uv run ruff check src tests bench scripts
uv run mypy src scripts
uv run pytest -q
```

Run the narrowest relevant benchmark when changing waits, engine behaviour, evidence
capture or runner lifecycle. Do not improve a number by weakening the scenario or its
oracle. Update the checked-in result, command and environment together.

External application authoring/replay checks are described in
[bench/oss/README.md](bench/oss/README.md). On Windows, an inaccessible system pytest
temp directory can be bypassed with a fresh `--basetemp=.tmp-pytest-<unique-run>`.
Do not reuse a directory containing artifacts you need: pytest clears basetemp.

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

All contributions are accepted under Apache-2.0. Contributors must have the right to
submit every source file, fixture and dataset in their change, identify third-party
material in the pull request, and add attribution or NOTICE text when its license
requires it. Synthetic fixtures are preferred. The maintainer `@kiselas` owns release,
security triage and final review until additional maintainers are named.
