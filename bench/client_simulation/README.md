# Installed-client and visual-regression simulation

This is a reproducible engineering simulation: two client adapter layouts, four
isolated projects, one scripted actor. It does **not** claim independent Claude,
Codex, human or customer acceptance. The source-generated Northstar fixture is
synthetic, local and contains no third-party assets or backend service.

## Run

Build a wheel, create a new virtual environment and install that exact wheel with
the `visual` extra. Example on Windows (use `bin/python` on Linux):

```powershell
uv build --wheel --out-dir outputs/client-visual/dist
uv venv outputs/client-visual/venv
uv pip install --python outputs/client-visual/venv/Scripts/python.exe 'outputs/client-visual/dist/testence-0.1.0.dev0-py3-none-any.whl[visual]'
outputs/client-visual/venv/Scripts/python.exe -m playwright install chromium
outputs/client-visual/venv/Scripts/python.exe -I bench/client_simulation/run.py --distribution outputs/client-visual/dist/testence-0.1.0.dev0-py3-none-any.whl --output outputs/client-visual/new-attempt --repeats 2
outputs/client-visual/venv/Scripts/python.exe -I bench/client_simulation/report.py outputs/client-visual/new-attempt
```

Output must not exist. Keep earlier attempts. The harness verifies installed
package bytes against the wheel and creates project-local pytest configuration,
without inheriting developer Testence settings or Python import paths. Each project
installs/verifies the selected packaged skills and validates the PlanSpec before
creating digest-pinned baseline candidates on the healthy fixture. Review the
baseline PNGs as part of the engineering result; unattended capture alone is not
independent baseline acceptance.

## Frozen test and controls

The accepted test knows only the target, state and pinned baseline. Mutation labels
and expected outcomes live in the harness, outside the copied client test. Both the
overview and dialog run at 1280×900 and 390×844, with Codex and Claude skill layouts:

| Phase | Expected visual result |
|---|---|
| healthy | verified |
| shift main content 28 px | violated; buttons/headings still work |
| make metric values transparent | violated; DOM content still exists |
| force mobile page to 760 px | violated on mobile, verified on desktop |
| change button ID/add inert data attribute | verified |
| restore | verified |

Two repeats produce 48 fresh pytest processes and 96 cases. Readiness is a separate
bound semantic assertion; only the visual assertion may produce the expected failure.
The grader rejects missing tests, skips, errors, wrong reasons, unverified assurance,
integrity failures, and source/baseline changes. The first unexpected outcome stops
the experiment and preserves a failed receipt. A deadline is recorded, not retried.

For each proved defect, a fresh `judge.py` process reads only the pack and applies
the fixed visual-contract policy, then submits a validated bound verdict through
the public CLI. It receives no mutation/expected-outcome argument and makes no root
cause claim. This is a scripted judge, not independent model reasoning. It must be
replaced by an actual client trial before claiming independent client acceptance.

`result.json` retains distribution/source hashes, bootstrap timings, each fresh
replay and each judgment/submission time. PNGs, ledgers, JUnit, logs and verdicts
remain in the output projects. Replay time excludes install, baseline authoring,
agent reasoning and triage. The suite is supplemental; it does not replace the
frozen R1/holdout corpus. No baseline generation occurs inside accepted replay.
