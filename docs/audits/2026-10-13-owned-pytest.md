# Nested pytest process ownership — 13 October 2026

Continuation of [the handoff](2026-10-13-handoff.md), backlog item 1.
Base: `cff7bdb`, branch `handoff-2026-10-13`. No other open PR is merged.

## Change and claims

- `NESTED-OWN-01`: nested pytest owns its descendants on normal exit and timeout.
  Migrated 27 calls in 20 test modules to `tests/owned_pytest.py`, backed by
  `testence._process.run_owned`. The frozen `tests/test_pytest_lifecycle.py` is
  untouched, including its legacy subprocess call.
- `NESTED-OWN-02`: child environments and timeout diagnostics survive the migration.
  `run_owned` accepts an explicit environment and optional positive output limit;
  its existing 4,000/2,000-character defaults remain. The test helper retains
  12,000 characters per channel, returns `CompletedProcess`, and raises
  `TimeoutExpired` so `tests/conftest.py` keeps displaying the captured stacks.
  Existing 300-second deadlines remain; calls without a deadline now get 300 seconds.
- `tests/test_owned_pytest.py` runs actual nested pytest with a descendant holding
  both output handles and a loopback listening socket. It checks normal exit,
  timeout, inherited synthetic environment, diagnostics and socket closure.
- English/Russian changelogs document the test infrastructure fix.
- The full run exposed a separate PID-file race in `tests/test_quality.py`:
  the parent observed an existing but empty file and failed at `int(marker.read_text())`.
  The child now writes a pending file then replaces the ready marker, preserving
  the exact transaction kill point and actual worker PID. No polling retry is added.

No browser interaction is retried, no oracle is weakened, and no accepted locator
changes. This does not identify the cause of the reported macOS hangs or bound
`PlaywrightCdpEngine.stop()`. That investigation remains the next backlog step.

## Evidence and commands

Run ID: `owned-pytest-20261013`; artifacts: ignored `outputs/owned-pytest-20261013/`.
Windows, system Edge, ephemeral CDP ports. Focused run used host CPython 3.12.4;
remaining checks use existing isolated CPython 3.12.14 to avoid the documented
native crashes of the host runtime. Dependencies synced from the lockfile:

```powershell
$env:UV_PROJECT_ENVIRONMENT="$PWD/outputs/quality-venv31214"
uv sync --locked --extra dev --extra parallel --extra visual
$env:TESTENCE_BROWSER_CHANNEL='msedge'
$env:TESTENCE_DEBUG_PORT='0'
$env:PYTEST_ADDOPTS='-o faulthandler_timeout=120'
uv run ruff format --check src tests bench scripts examples
uv run ruff check src tests bench scripts examples
uv run mypy src scripts
uv run pytest -n 4 -q --basetemp=.tmp-pytest-owned-full-20261013a
uv run pytest examples -q --testence-headless --basetemp=.tmp-pytest-owned-examples-20261013a
uv run python bench/oss/run.py --repeats 1 --output outputs/owned-pytest-20261013/oss
```

Focused command (host environment):
`uv run pytest tests/test_owned_process.py tests/test_owned_pytest.py tests/test_plugin_opt_in.py -q --basetemp=.tmp-pytest-owned-focused-20261013a`:
**19 passed in 53.25 seconds**. Formatting/lint pass; mypy passes all 86 source
files. Examples: **5 passed, 1 skipped in 36.14 seconds**.

The negative probe substitutes the previous `subprocess.run(capture_output=True)`
implementation into the new normal-exit regression. It runs under an outer owned
20-second deadline: the parent pytest exits, but inherited output handles keep
the controller waiting. Result: deadline exceeded in **20.016 seconds**, retained
in `baseline.json`; the outer owner cleans the descendants. This is a synthetic
comparison of the old call pattern, not a checkout-wide run of `main`.
Initial probe failed at import (`ModuleNotFoundError: tests`); its receipt remains
`baseline-import-failure.json`. Adding the repository to `PYTHONPATH` allowed the
probe to reach the intended step.

Reproduce the probe in its preserved directory only after choosing an unused
project directory in `baseline_probe.py`:

```powershell
$env:PYTHONPATH="$PWD;$PWD/src"
uv run python -c "import sys; from pathlib import Path; from testence._process import run_owned; print(run_owned([sys.executable,'outputs/owned-pytest-20261013/baseline_probe.py'],cwd=Path.cwd(),timeout=20))"
```

First full suite: **1 failed, 897 passed, 2 skipped in 401.90 seconds**,
`full.log`. Failure: `tests/test_quality.py::test_next_public_apply_recovers_after_a_real_process_kill`,
line 431: `ValueError: invalid literal for int() with base 10: ''`.
This failed run remains evidence; a corrected run uses a new basetemp suffix `b`
and `full-after-marker.log`.
Corrected full run: **898 passed, 2 skipped in 357.06 seconds**, exit 0.
The final exact command uses `--basetemp=.tmp-pytest-owned-full-20261013b`.
[Validation receipt](2026-10-13-owned-pytest-validation.json) records the source hashes
and both full-run outcomes. The two skips require Windows symlink privileges.
Focused corrected check: `uv run pytest tests/test_quality.py::test_next_public_apply_recovers_after_a_real_process_kill tests/test_owned_pytest.py -q --basetemp=.tmp-pytest-owned-race-20261013a`:
**3 passed in 7.82 seconds**, `race.log`. Formatting and lint also pass after the change.

Live OSS corpus: **16 expected outcomes**, 14 verified and 2 expected violations,
no integrity errors. Phase times: healthy 31,499.4 ms, defect 35,293.9 ms,
restored 24,244.1 ms, harmless restyle 26,192.9 ms. One sample per phase and
concurrent local checks cannot support a performance claim. The sanitized
[receipt](2026-10-13-owned-pytest-oss.json) binds upstream revisions/license hashes,
plan/test hashes and the tested dirty source files. Raw artifacts remain under
`outputs/owned-pytest-20261013/oss/`.

Tests do not carry product PlanSpec IDs: these are framework process lifecycle claims.

## Handoff

Last failed suite step: PID parsing before the marker contained data, described above.
Negative-control failure: legacy controller waits on inherited output handles
after nested pytest's normal exit (outer timeout).
Remaining uncertainty: hosted macOS behavior, unbounded sync engine shutdown and
the frozen lifecycle helper. No release or independent-client assurance is claimed.
Next proving command after this change: the hosted CI matrix for PR #35, then
investigate an actual `stop()` stack before changing engine shutdown semantics.
