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

| exporter | writes | carries |
|---|---|---|
| `allure` | `<n>-result.json` per attempt, fixture containers, attachments, `environment.properties` | case/history/result identities, parameters, owner/risk/requirement/issue links, nested steps and redacted evidence |
| `ctrf` | one `ctrf-report.json` | summary counts, tags, flattened step intents, pack path |

JUnit XML is deliberately **not** an exporter: `pytest --junitxml=…` already emits it
correctly, including under `-n`, and GitLab/Jenkins/GitHub parse it natively.

## Uploading results to Allure TestOps

`allure` writes the *results directory* format, not the SDK's in-process model, and
`allurectl` can upload that directory. Preserve the pytest exit code explicitly: a
successful export or upload must not turn a failed or incomplete test run green. Give
the run an explicit id as well, so parallel jobs never select a stale directory.

```yaml
run_tests:
  script:
    - |
      export TESTENCE_RUN_ID="r-${CI_PIPELINE_ID}-${CI_JOB_ID}"
      set +e
      pytest tests_e2e/ -q
      TEST_EXIT=$?
      set -e
      RUN="runs/${TESTENCE_RUN_ID}"
      testence export "$RUN" --to allure
      allurectl upload "$RUN/allure-results"
      exit "$TEST_EXIT"
  artifacts:
    when: always
    paths: [runs/]
```

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
a failed or incomplete run. Missing attachments, wrong project, stale run identity and
CTRF/JUnit inventory drift fail before the job becomes green.

The exporter preserves these consumer identities and dimensions:

- **Marker names.** Markers become Allure tags verbatim. Saved filters, dashboards and
  dashboards and saved filters key on those strings, so renaming them would quietly
  empty someone's filter.
- **Identity and retries.** `testCaseId` follows `(project, case)`; `historyId` adds the
  variant; result UUID adds run and attempt. Every retry remains a separate result in
  one history instead of replacing the earlier attempt.
- **Plan metadata.** PlanSpec `owner`, scenario `risk`, requirements and issues become
  labels and standard Allure `tms`/`issue` links. Digest-only parameters remain safe to
  group without exporting raw secrets.
- **Fixtures.** Pytest setup and teardown phases become deterministic Allure container
  entries with their status, timing and error.

The T15 consumer check uses pinned Allure Report 3.14.3:

```bash
testence export <run-dir> --to allure -o allure-results
npx --yes allure@3.14.3 awesome allure-results -o allure-report --single-file
```

Testence consumes the standard `ALLURE_TESTPLAN_PATH` format at collection time. The
plan version must be `1.0`; entries select by exact pytest `fullName`, `allure_id`, or
`testence://<project>/<case>/<variant>`. Invalid, unresolved, ambiguous and empty plans
fail before test execution. An intentionally empty plan requires
`--testence-empty-testplan=noop`, which produces a successful zero-test run manifest.
The offline selector is verified; a real TestOps tenant select/upload/history round trip
remains an external acceptance gate. Results appear at export time, not streamed during the run
(`allurectl watch` has nothing to watch). For suites that finish in seconds to minutes
this may be acceptable; if it blocks adoption, ADR-0013's tripwire calls for
incremental export on each `test.end` rather than for an SDK.

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
