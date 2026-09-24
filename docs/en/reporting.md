# Reporting: exporters over the ledger

Testence produces one artifact of record per run — `runs/<run-id>/run.jsonl`
([schema `testence/2`](evidence-schema.md)). Everything a human or a platform reads is
rendered *from* it: the [HTML report](adr/0005-html-report.md), `metrics.json`, and
the reporting formats described here.

No reporting library is imported anywhere in the framework, and no test calls a
reporting API. Capture is ambient — steps carry the intent sentences the DSL already
records — so a call site cannot forget to report, and there is no second version of
what happened. The reasoning, the alternatives and the tripwires are in
[ADR-0013](adr/0013-reporting-as-export.md).

## Exporting a run

```bash
testence export --list                          # what is registered
testence export runs/r-20260827-083736-29ae2f --to allure
testence export runs/r-20260827-083736-29ae2f --to ctrf -o build/ctrf
```

Without `-o`, output lands in `<run-dir>/<name>-results`.

Export applies the run's redaction policy again to every event and text attachment
([configuration](configuration.md#redaction-and-screenshot-masks)), so a run written
before a rule existed does not leave in clear text. The run directory itself is never
rewritten. `--attachments` chooses which pack files an export ships: `full` (default,
redacted), `minimal` (no `network.jsonl`, `aria.txt` or screenshot) or `none`.

| exporter | writes | carries |
|---|---|---|
| `allure` | `<n>-result.json` per attempt, fixture containers, attachments, `environment.properties`, `categories.json` | allure-pytest-compatible identities, `@allure.*` and marker metadata, suite tree, readable redacted parameters, failed/broken status with full trace, owner/risk/requirement/issue links, nested steps and redacted evidence |
| `ctrf` | `ctrf-report.json` and `attachments/` | CTRF's own fields: steps, suite path, labels (identity, Allure labels, case ids), parameters, trace, attachments, start/stop; Testence identity and assurance in `extra` |
| `junit` | `junit.xml` and `attachments/` | one suite per file, `<failure>`/`<error>`/`<skipped>` as Allure splits failed and broken, `testence.*` identity and case-id properties, step intents and `[[ATTACHMENT\|path]]` lines in `<system-out>` ([ADR-0028](adr/0028-junit-exporter.md)) |

`pytest --junitxml=…` stays the simplest choice when a job only needs pass/fail.
`--to junit` adds what that file cannot carry: the identity, case ids, steps and
evidence. Its XML is pytest's default dialect (`junit_family=xunit1`).

### Test-management case ids

Declare the case a test implements in the systems your team reports into; the ids
travel with every export:

```python
@pytest.mark.testence(tms={"testrail": "C1042", "xray": "SHOP-12"})
def test_checkout_charges_the_card_once(ex): ...
```

| System key | JUnit property | Also |
|---|---|---|
| `testrail` (`C123` or `123`, one or more) | `test_id` — `trcli`'s property case matcher; plus `testrail_result_step` per leaf step and `testrail_attachment` per evidence file | Allure label, CTRF `labels["tms.testrail"]` |
| `xray` (one Test key, `PROJ-12`) | `test_key`, and `requirements` from the PlanSpec | Allure label, CTRF `labels["tms.xray"]` |
| any other lowercase name | `tms.<system>` | Allure label, CTRF `labels["tms.<system>"]` |

Property names follow the `trcli` and Xray JUnit documentation. `test_id` means a
TestRail case in `trcli` and a numeric issue id in Xray, so declare only the systems a
report is meant for.

## Uploading results to Allure TestOps

Two ways to feed TestOps, both writing the standard Allure *results directory*:

- **Streaming** (recommended): `--testence-allure-results DIR` (or
  `TESTENCE_ALLURE_RESULTS`) writes each result the moment its test ends, so
  `allurectl watch` shows the launch filling in and a job killed halfway keeps the
  results it finished. Files appear atomically, attachments before the result that
  references them, and the bytes equal a post-run `testence export --to allure`.
- **Post-run**: `testence export <run> --to allure`, then `allurectl upload`.

Preserve the pytest exit code explicitly: a successful upload must not turn a failed
run green. Give the run an explicit id, so parallel jobs never pick a stale directory.
When TestOps starts the job, fetch its test plan first:

```yaml
run_tests:
  script:
    - |
      export TESTENCE_RUN_ID="r-${CI_PIPELINE_ID}-${CI_JOB_ID}"
      RUN="runs/${TESTENCE_RUN_ID}"
      export ALLURE_TESTPLAN_PATH="$PWD/testplan.json"
      if [ -n "${ALLURE_JOB_RUN_ID:-}" ]; then
        allurectl job-run plan --output-file "$ALLURE_TESTPLAN_PATH"
      else
        unset ALLURE_TESTPLAN_PATH
      fi
      set +e
      allurectl watch --results "$RUN/allure-results" -- \
        pytest tests_e2e/ -q --testence-allure-results "$RUN/allure-results"
      TEST_EXIT=$?
      set -e
      exit "$TEST_EXIT"
  artifacts:
    when: always
    paths: [runs/]
```

Check the flag names against your `allurectl` version (`allurectl watch --help`). The
post-run variant replaces the `watch` line with `pytest tests_e2e/ -q`, then
`testence export "$RUN" --to allure` and `allurectl upload "$RUN/allure-results"`.

For a retryable upload with a machine receipt, keep every identity explicit. Options
for `delivery run` precede the run directory because the remaining arguments are the
uploader command:

```bash
testence delivery run \
  --run-id "$TESTENCE_RUN_ID" --project-id "$TESTENCE_PROJECT_ID" \
  --launch-id "$ALLURE_LAUNCH_ID" --job-run-id "$ALLURE_JOB_RUN_ID" \
  --artifact-dir "$RUN/allure-results" --receipt "$RUN/delivery-receipt.json" \
  --retries 2 --timeout 60 "$RUN" -- allurectl upload "$RUN/allure-results"

testence ci evaluate "$RUN" --run-id "$TESTENCE_RUN_ID" \
  --test-exit "$TEST_EXIT" --quality-mode assurance \
  --delivery-receipt "$RUN/delivery-receipt.json" \
  --ctrf "$RUN/ctrf-results/ctrf-report.json" --junit "$RUN/junit.xml" \
  -o "$RUN/ci-receipt.json"
exit $?
```

The delivery receipt is idempotent for the run/project/launch/job-run plus the exact
artifact digest. A successful receipt is reused; timeouts and nonzero uploader exits
are retried within the stated cap. `ci evaluate` records test, quality and delivery
exits separately and returns the first failing axis, so a successful upload cannot hide
a failed or incomplete run.

### Moving an allure-pytest suite

By default (`export.allure.naming: allure-pytest`) results land on the identities
allure-pytest creates: `fullName` is `package.module[.Class]#test` without parameters,
and `testCaseId`/`historyId` use allure-pytest's formulas. Existing TestOps test cases,
their history and manual-to-automated links carry over. `@allure.feature`, `story`,
`severity`, `id`, `label`, `link`, `issue`, `testcase`, `title` and `description` are
read from the marks they create, with or without allure-pytest installed. A test bound
to a PlanSpec case keeps its Testence identity, because that id survives a rename.
`export.allure.naming: nodeid` restores the identities Testence 0.1.0a1 exported.

```json
{"export": {"allure": {"naming": "allure-pytest", "parameters": "values"}}}
```

Describe a test for reports without a PlanSpec:

```python
@pytest.mark.testence(
    allure_id=1042,
    title="Paying with a saved card charges it once",
    severity="critical",
    labels={"feature": "Cart", "story": ["Pay by card"]},
    links=["https://docs.example.test/pay", {"url": "https://jira.example.test/PAY-7", "type": "issue"}],
)
def test_pay_with_saved_card(ex): ...
```

Two different tests with one `allure_id` get a warning: their results would share one
TestOps case. Running allure-pytest with `--alluredir` next to a Testence upload gets a
warning too: it would duplicate every result.

### What the card shows

- **Status.** An assertion or oracle disagreement is `failed`; a browser, network or
  timeout problem, an inconclusive oracle and an error in the test's own code are
  `broken`. `categories.json` groups them the same way.
- **Trace.** The full pytest failure, bounded and redacted, not only its first line.
- **Name and description.** An explicit title (`@allure.title` or the marker), then the
  PlanSpec scenario title, then the pytest name. An explicit description, then the
  PlanSpec claims with their statements, then the docstring.
- **Tree.** `parentSuite`/`suite`/`subSuite`, `package`, `testClass`, `testMethod` and
  `titlePath`, as allure-pytest writes them.
- **Tags.** User markers without arguments, as allure-pytest does; `parametrize`,
  `usefixtures`, `skip`, `xfail` and Testence's own marks are not tags.
- **Parameters.** Readable, redacted values; a parameter named like a secret is
  `masked`. `export.allure.parameters: digest` restores digest-only values. pytest puts
  parameter values into test ids, which every report shows: Testence warns when a
  secret-named parameter's value is in an id, so give that `parametrize` an `ids=`.
- **Attachments.** The redacted evidence pack of a failure, the screenshot also on the
  failed step, and with `evidence.screenshots: always` the passing page.
- **Fixtures, retries and plan metadata.** Setup and teardown become container
  entries; every retry is a separate result in one history; PlanSpec owner, risk,
  requirements and issues become labels and `tms`/`issue` links.

### Selecting tests from a TestOps plan

`ALLURE_TESTPLAN_PATH` (format `1.0`) is applied at collection. An entry selects by
`id` (every variant carrying that `allure_id`, so rerunning a parametrized case runs all
its variants) or by `selector`: an allure-pytest `fullName` (every variant), an exact
pytest nodeid (one variant) or `testence://<project>/<case>/<variant>`. Overlapping and
repeated entries select a test once; unknown fields are ignored with a warning.

An entry that matches no collected test (a case renamed or deleted since the plan was
built) is reported and the rest of the plan runs: a pytest warning, a
`testplan.unresolved` ledger event, `testence.testplan_unresolved` in
`environment.properties`, the CTRF summary and the CI receipt. Pipelines that must fail
instead pass `--testence-testplan-unresolved=fail` (or
`TESTENCE_TESTPLAN_UNRESOLVED=fail`), and `testence ci evaluate
--testplan-unresolved fail` turns reported entries into a quality failure. A plan in
which nothing resolves always fails before execution. An intentionally empty plan
requires `--testence-empty-testplan=noop`.

The T15 consumer check uses pinned Allure Report 3.14.3:

```bash
testence export <run-dir> --to allure -o allure-results
npx --yes allure@3.14.3 awesome allure-results -o allure-report --single-file
```

## Writing your own exporter

An exporter is a module with two symbols:

```python
name: str
export(run: LoadedRun, out_dir: Path) -> list[Path]
```

It receives the parsed, merged ledger — never raw files — and returns the paths it
wrote (callers archive exactly those). `src/testence/export/ctrf.py` is the worked
example: about forty lines of logic, stdlib only.

```python
# acme_testops/exporter.py
import json
from pathlib import Path

name = "testops"


def export(run, out_dir: Path) -> list[Path]:
    target = out_dir / "testops.json"
    target.write_text(
        json.dumps(
            {
                "run": run.run_id,
                "environment": run.fingerprint,
                "cases": [
                    {
                        "id": test.nodeid,
                        "ok": not test.failed,
                        "ms": test.duration_ms,
                        "tags": list(test.markers),
                    }
                    for test in run.tests
                ]
            }
        ),
        encoding="utf-8",
    )
    return [target]
```

Register it from your own distribution — no PR to Testence, and your dependencies stay
yours:

```toml
[project.entry-points."testence.exporters"]
testops = "acme_testops.exporter"
```

`testence export --list` will show it as an entry point, and `--to testops` will use
it. Built-in names win on conflict, so an installed package cannot silently redefine
what `--to allure` means in a pipeline that has been green for a year.

### What the model gives you

`LoadedRun` (see `src/testence/export/_model.py`) is the whole API surface:

| | |
|---|---|
| `run_id`, `testence_version`, `fingerprint` | run identity and the target environment |
| `start`, `stop`, `duration_ms` | timezone-aware datetimes; `epoch_ms()` converts |
| `tests` | list of `Test` |
| `pack_path(test, filename)` | absolute path of one evidence-pack file, or `None` |
| `events` | the raw ledger, as an escape hatch |
| `Test` | identity/parameters, owner/risk/requirements/issues, source/plan/claims, status/assurance, fixtures, steps, oracles and pack |
| `FixturePhase` | setup/teardown name, status, duration, error and `start`/`stop` |
| `Step` | `intent`, `target`, `status`, `duration_ms`, `error`, `start`/`stop`, `substeps` |

Two rules worth knowing before you format anything:

- **Steps nest.** A composite action contains its primitives and its duration already
  includes theirs, so summing every step double-counts. Walk leaves
  (`not step.substeps`) for per-interaction latency.
- **Fields are optional.** The schema grows by appending, never retroactively; a
  ledger written before a field existed must still export, with less detail rather
  than a crash. Reaching into `run.events` usually means the *ledger* is missing
  something — extend the schema (append a field, update
  [evidence-schema.md](evidence-schema.md)) instead of instrumenting test code.

### Tests you inherit

`tests/test_export.py` parametrises its contract suite over every **registered**
exporter, so installing yours into the test environment gets you: files-land-where-you-
said, determinism (same ledger in → byte-identical files out), and legacy-ledger
tolerance. Add a golden of your own the same way the built-ins have one — a static
ledger under `tests/fixtures/golden-run/` exported and compared byte-for-byte:

```bash
pytest tests/test_export.py -k golden                     # verify
TESTENCE_UPDATE_GOLDENS=1 pytest tests/test_export.py -k golden   # regenerate, then read the diff
```

The fixture ledger has fixed timestamps deliberately: one produced by `EvidenceWriter`
is stamped with the current time, which proves determinism inside a run but not across
commits. When an upstream format drifts, that diff is the review.
