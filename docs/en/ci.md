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
        run: testence run --project . --run-id "ci-${{ github.run_id }}"
      - name: Export JUnit for the CI test view
        if: always()
        run: testence export "runs/ci-${{ github.run_id }}" --to junit -o test-results
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
- For Allure TestOps, stream results with `--testence-allure-results`
  ([reporting](reporting.md#uploading-results-to-allure-testops)); for other systems,
  export `--to ctrf`.
- GitLab CI and other runners need the same four commands: `pip install testence`,
  `python -m playwright install --with-deps chromium`, `testence run`, `testence export`.
