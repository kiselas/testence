# Running Testence in CI

A GitHub Actions workflow for a project made by `testence init`. It installs Testence and
Chromium, runs the tests without any model, exports JUnit for the CI test view and keeps
the evidence (`runs/`) as an artifact, also when a test failed. The repository's own CI
runs this file's steps as written against a fresh `testence init` project.

The file: [`docs/examples/github-actions.yml`](../examples/github-actions.yml).

```yaml
# Copy to .github/workflows/e2e.yml in your project; `testence init` writes the rest.
name: e2e

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  e2e:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    env:
      # Only for an app behind a login; unset secrets are empty and ignored by auth: none.
      TESTENCE_USER: ${{ secrets.TESTENCE_USER }}
      TESTENCE_PASSWORD: ${{ secrets.TESTENCE_PASSWORD }}
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: "3.12"
      - name: Install Testence and Chromium
        run: |
          python -m pip install testence
          python -m playwright install --with-deps chromium
      - name: Run the tests
        # Strict mode (opt-in, one more run per declared control): replace this command
        # with `testence prove --project . --run-id "ci-${{ github.run_id }}"`.
        run: testence run --project . --run-id "ci-${{ github.run_id }}"
      - name: Export JUnit for the CI test view
        if: always()
        run: testence export "runs/ci-${{ github.run_id }}" --to junit -o test-results
      - name: Summarize what the run proved
        if: always()
        run: testence ci summary "runs/ci-${{ github.run_id }}" >> "$GITHUB_STEP_SUMMARY"
      - name: Keep the evidence
        if: always()
        uses: actions/upload-artifact@v7
        with:
          name: testence-evidence
          path: |
            runs/
            test-results/
```

- An app behind a login reads `TESTENCE_USER` and `TESTENCE_PASSWORD` from the
  repository's secrets; `auth: none` ignores them ([auth](auth.md)).
- `testence run` fails the job when a test fails; the export and the artifact still run
  (`if: always()`), so the failure pack of every failed attempt is in `runs/`.
- `testence ci summary` writes what the run proved into the job summary: required
  claims backed by verified assertions, tests whose proof is not verified, flaky tests,
  and the pass count last, labelled as no argument. It reads the run only and always
  exits 0 for a readable run, so it never decides the job.
- For Allure TestOps, stream results with `--testence-allure-results`
  ([reporting](reporting.md#uploading-results-to-allure-testops)); for other systems,
  export `--to ctrf`.
- GitLab CI and other runners need the same four commands: `pip install testence`,
  `python -m playwright install --with-deps chromium`, `testence run`, `testence export`.

## Requiring proof that tests can fail

`ci evaluate --quality-mode assurance` (the default) requires every test to be
`verified`. A test whose expected value was copied from the product is `verified` too.
The opt-in `proven` mode also requires, for every required claim, a run with a
[negative control](configuration.md#negative-controls) in which the same test failed
an assertion bound to that claim ([ADR-0033](adr/0033-negative-proof.md)):

```bash
testence prove --project . --run-id "ci-${GITHUB_RUN_ID}"
```

`testence prove` is the whole strict mode in one command:

1. the green run, `runs/ci-<id>`; when it is not green the command stops with its exit
   code and runs nothing else, because a test that fails without a defect proves nothing;
2. one run per declared control, `runs/ci-<id>-<control>`, or only the ones named with
   `--control NAME` (repeat the option for several);
3. the evaluation, as `ci evaluate --quality-mode proven` with every control run as a
   `--negative-run`, and one receipt, `runs/ci-<id>.receipt.json` (`-o` moves it).

The exit code is the one `ci evaluate` gives: 0 when every required claim has a negative
proof, 10 when proof is missing. Tests and pytest options go after `--`, as for
`testence run`; without them the onboarding test runs. Every control run executes the
same selection as the green run. Control runs never repeat, so `TESTENCE_RERUNS` is
ignored there and `--testence-reruns` is refused. `--json` prints one document on
stdout and sends pytest's output to stderr.

The command is the short form of what a job can also spell out, for example to run the
controls in parallel jobs:

```bash
testence run --project . --run-id "ci-${GITHUB_RUN_ID}"
testence run --project . --run-id "ci-${GITHUB_RUN_ID}-drop-save" --control drop-save || true
testence ci evaluate "runs/ci-${GITHUB_RUN_ID}" --run-id "ci-${GITHUB_RUN_ID}" \
  --test-exit 0 --quality-mode proven \
  --negative-run "runs/ci-${GITHUB_RUN_ID}-drop-save" -o ci-receipt.json
```

A negative run is expected to fail, so its exit code is not the job's (`prove` knows
this). The summary step of the template reads one control run per `--negative-run`:
`testence ci summary "runs/ci-${GITHUB_RUN_ID}" --negative-run "runs/ci-${GITHUB_RUN_ID}-drop-save"`.
The receipt's
`quality.negative_proof` lists each claim with one outcome:

| outcome | meaning |
|---|---|
| `proven` | the test failed on this claim with the control active |
| `stayed_green` | the test passed with the control active: it cannot detect this defect |
| `wrong_reason` | the test failed, but on other claims |
| `inconclusive` | the test did not run, was repeated, or failed outside an assertion |
| `stale` | the test or its plan changed between the two runs |
| `no_control` | no supplied control targets the claim |

`testence ci summary RUN_DIR --negative-run DIR` adds the claims with a negative proof
to the job summary. To post the summary as a pull request comment instead, give the
job `pull-requests: write` and run
`testence ci summary RUN_DIR > summary.md && gh pr comment "$PR" --body-file summary.md --edit-last --create-if-none`.

Failures of claims a control does not target are listed as `collateral_claims`. When
more than half of the claims that failed in a control run are collateral, `testence
prove`, `ci summary` and the receipt (`quality.negative_proof.controls`, `blunt: true`) warn that the control may be too
blunt for `proven` to say much ([ADR-0033](adr/0033-negative-proof.md#tripwire)); the
warning does not change the exit code. Each control costs one more run, and some
claims have no honest control, so `proven` is a stricter level for the claims that matter most, not the default.
