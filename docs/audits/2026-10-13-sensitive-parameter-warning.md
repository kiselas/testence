# Sensitive parameter warning regression

Pilot contract PILOT-03. Baseline: `c7a7949652758160c244e0be2f2a5ed5e02487e8`.

An actual pytest subprocess reproduced a Testence warning containing the synthetic
password from its parameter ID. The regression failed on baseline with
`SYNTH-CANARY-41` in the warning. The fix prints the test location without its parameter
suffix and also detects pytest's Unicode-escaped parameter values. It does not rewrite
pytest IDs, Allure identities, or suppress the warning.

Proof on Windows, CPython 3.12.12:

```powershell
uv sync --locked --extra dev --extra parallel --extra visual
uv run pytest -q tests/test_sensitive_parameter_warning.py -x --basetemp=.tmp-pytest-warning-before
uv run pytest -q tests/test_sensitive_parameter_warning.py tests/test_allure_compat.py tests/test_identity.py --basetemp=.tmp-pytest-warning-after --junitxml=outputs/warning-focused.xml
uv run ruff format --check src tests bench scripts examples
uv run ruff check src tests bench scripts examples
uv run mypy src scripts
```

The baseline run failed for the intended reason. After the patch, 26 focused tests
passed in 20.25 seconds; formatting, lint and type checks passed. The five new cases
cover a password, numeric PIN, Unicode with quotes, a safe explicit ID, and ordinary
non-sensitive data. Every subprocess must complete successfully; warning records are
captured through pytest's real warning hook rather than inferred from source text.

Full-suite and installed-distribution evidence belong to the accepting CI run and
candidate build, and must be checked before release. A passing focused check does not
establish that every reporter removes parameter values: standard pytest output may
still contain its original ID. Use non-sensitive explicit `ids` for credentials.

This patch is based on current main and does not depend on the unmerged PR 32. Its
diagnostic-only change should be reconciled with PR 32 if that branch is integrated.
The source-string traceback case PILOT-04 is separate and remains open.
