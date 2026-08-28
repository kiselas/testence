# Reporting: exporters over the ledger

Testence produces one artifact of record per run — `runs/<run-id>/run.jsonl`
([schema `testence/1`](evidence-schema.md)). Everything a human or a platform reads is
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
| `allure` | `<n>-result.json` per test, attachments, `environment.properties` | nested steps, markers as tags, evidence pack as attachments, environment fingerprint |
| `ctrf` | one `ctrf-report.json` | summary counts, tags, flattened step intents, pack path |

JUnit XML is deliberately **not** an exporter: `pytest --junitxml=…` already emits it
correctly, including under `-n`, and GitLab/Jenkins/GitHub parse it natively.

## Keeping an existing Allure TestOps pipeline

`allure` writes the *results directory* format, not the SDK's in-process model, and
`allurectl` uploads such a directory without caring what produced it. That is what
makes a migration cheap: **the test command changes, the pipeline does not.** Endpoint,
project id and token stay exactly as they are.

```yaml
run_tests:
  script:
    # a red suite still has results worth uploading
    - pytest tests_e2e/ -q || true
    - RUN=$(ls -dt runs/r-* | head -1)
    - testence export "$RUN" --to allure
    - allurectl upload "$RUN/allure-results"
  artifacts:
    when: always
    paths: [runs/]
```

Two things that survive the swap because they were designed to:

- **Marker names.** Markers become Allure tags verbatim. Saved filters, dashboards and
  scheduled selective runs key on those strings, so renaming them would quietly empty
  someone's filter.
- **History.** `historyId` is a hash of the test's nodeid and nothing else, so TestOps
  trends follow the test across runs instead of showing unrelated one-shot results.

One thing that does not: results appear at export time, not streamed during the run
(`allurectl watch` has nothing to watch). For suites that finish in seconds to minutes
this is a non-issue; if it ever blocks adoption, ADR-0013's tripwire calls for
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
| `Test` | `name`, `nodeid`, `file`, `markers`, `status`, `duration_ms`, `start`/`stop`, `error`, `steps`, `oracles`, `pack_dir` |
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
