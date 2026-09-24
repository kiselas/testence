# Отчётность: экспортёры поверх журнала

Testence создаёт один authoritative artifact на запуск —
`runs/<run-id>/run.jsonl` ([схема `testence/2`](evidence-schema.md)). Всё, что читают
люди или платформы, рендерится **из него**: [HTML-отчёт](adr/0005-html-report.md),
`metrics.json` и описанные здесь форматы.

Фреймворк нигде не импортирует reporting library, а тесты не вызывают reporting API.
Capture является ambient: шаги уже несут intent, записываемый DSL, поэтому call site
не может забыть об отчёте и не возникает второй версии событий. Обоснование,
альтернативы и tripwires находятся в [ADR-0013](adr/0013-reporting-as-export.md).

## Экспорт запуска

```bash
testence export --list
testence export runs/r-20260827-083736-29ae2f --to allure
testence export runs/r-20260827-083736-29ae2f --to ctrf -o build/ctrf
```

Без `-o` результат записывается в `<run-dir>/<name>-results`.

Экспорт повторно применяет политику маскировки прогона к каждому событию и текстовому
вложению ([настройки](configuration.md#маскировка-секретов-и-маски-скриншотов)), поэтому
прогон, записанный до появления правила, не уходит наружу в открытом виде. Сам каталог
прогона не переписывается. `--attachments` выбирает, какие файлы pack попадут в экспорт:
`full` (по умолчанию, замаскированные), `minimal` (без `network.jsonl`, `aria.txt` и
скриншота) или `none`.

| Exporter | Что пишет | Что переносит |
|---|---|---|
| `allure` | `<n>-result.json` на attempt, fixture containers, attachments, `environment.properties` | case/history/result identities, parameters, owner/risk/requirement/issue links, steps и redacted evidence |
| `ctrf` | один `ctrf-report.json` | summary counts, tags, плоские step intents и путь pack |

JUnit XML намеренно не является exporter: `pytest --junitxml=…` уже создаёт его
корректно, в том числе под `-n`, а GitLab/Jenkins/GitHub читают его напрямую.

## Загрузка результатов в Allure TestOps

`allure` пишет формат **каталога результатов**, а не in-process модель SDK, и
`allurectl` может загрузить этот каталог. Исходный код завершения pytest нужно сохранить
явно: успешный export/upload не должен делать failed или incomplete run зелёным. Run ID
тоже задаётся явно, чтобы параллельный job не выбрал старый каталог.

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

Для retryable upload с машинным receipt все identity задаются явно. Options команды
`delivery run` идут перед каталогом запуска, потому что остаток arguments является
командой uploader:

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

Delivery receipt идемпотентен для run/project/launch/job-run и точного artifact digest.
Успешный receipt переиспользуется; timeout и ненулевой uploader exit повторяются внутри
заданного лимита. `ci evaluate` отдельно записывает test, quality и delivery exits и
возвращает первую упавшую ось, поэтому успешный upload не скрывает failed или incomplete
run. Missing attachment, wrong project, stale run identity и расхождение CTRF/JUnit
inventory отклоняются до зелёного статуса job.

Exporter сохраняет consumer identities и dimensions:

- **Имена markers.** Они переходят в Allure tags без изменений. Saved filters,
  dashboards и saved filters зависят от этих строк, поэтому переименование незаметно
  опустошит чужой filter.
- **Identity и retries.** `testCaseId` следует за `(project, case)`, `historyId`
  добавляет variant, а UUID результата — run и attempt. Каждый retry остаётся отдельным
  результатом в одной истории и не заменяет предыдущую попытку.
- **Метаданные плана.** `owner` PlanSpec, `risk` scenario, requirements и issues
  становятся labels и стандартными Allure links типов `tms`/`issue`. Digest-only
  parameters позволяют группировку без публикации исходных секретов.
- **Fixtures.** Pytest setup и teardown становятся детерминированными Allure container
  entries со статусом, временем и ошибкой.

Consumer-проверка T15 использует закреплённый Allure Report 3.14.3:

```bash
testence export <run-dir> --to allure -o allure-results
npx --yes allure@3.14.3 awesome allure-results -o allure-report --single-file
```

Testence читает стандартный формат `ALLURE_TESTPLAN_PATH` во время collection. Версия
plan обязана быть `1.0`; entries выбирают по точному pytest `fullName`, `allure_id` или
`testence://<project>/<case>/<variant>`. Invalid, unresolved, ambiguous и пустой plan
завершаются ошибкой до запуска тестов. Намеренно пустой plan требует
`--testence-empty-testplan=noop` и создаёт успешный manifest запуска с нулём тестов.
Offline selector проверен; select/upload/history round trip настоящего TestOps tenant
остаётся внешним gate. Streaming отсутствует: результаты появляются при export, а не во время запуска,
поэтому `allurectl watch` нечего наблюдать. Для короткого suite это может быть допустимо.
Если streaming станет блокером adoption, tripwire ADR-0013 требует
incremental export на каждый `test.end`, но не SDK.

## Собственный exporter

Exporter — модуль с двумя symbols:

```python
name: str
export(run: LoadedRun, out_dir: Path) -> list[Path]
```

Он получает разобранный объединённый ledger, а не raw files, и возвращает записанные
paths, чтобы caller архивировал именно их. `src/testence/export/ctrf.py` — рабочий
пример примерно из сорока строк stdlib-only логики.

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

Зарегистрируйте его из собственного distribution: PR в Testence не нужен, ваши
dependencies остаются вашими.

```toml
[project.entry-points."testence.exporters"]
testops = "acme_testops.exporter"
```

`testence export --list` покажет его как entry point, а `--to testops` использует.
Встроенные names имеют приоритет при конфликте, поэтому установленный package не может
скрыто переопределить `--to allure` в давно работающем pipeline.

### Модель данных

`LoadedRun` из `src/testence/export/_model.py` — вся поверхность API:

| | |
|---|---|
| `run_id`, `testence_version`, `fingerprint` | идентичность запуска и target environment |
| `start`, `stop`, `duration_ms` | timezone-aware datetimes; `epoch_ms()` конвертирует |
| `tests` | список `Test` |
| `pack_path(test, filename)` | абсолютный путь к файлу evidence pack либо `None` |
| `events` | raw ledger как escape hatch |
| `Test` | identity/parameters, owner/risk/requirements/issues, source/plan/claims, status/assurance, fixtures, steps, oracles и pack |
| `FixturePhase` | setup/teardown name, status, duration, error и `start`/`stop` |
| `Step` | `intent`, `target`, `status`, `duration_ms`, `error`, `start`/`stop`, `substeps` |

Перед форматированием важно знать два правила:

- **Steps вложены.** Composite action содержит primitives, а его duration уже включает
  их. Сумма всех steps считает время дважды. Для per-interaction latency обходите
  leaves с `not step.substeps`.
- **Поля необязательны.** Схема растёт добавлением и не переписывается задним числом.
  Старый ledger обязан экспортироваться с меньшей детализацией, а не падать. Обращение
  к `run.events` обычно означает, что данных не хватает **в ledger**: расширьте схему,
  добавив поле и обновив [evidence-schema.md](evidence-schema.md), вместо instrumentation
  тестового кода.

### Унаследованные тесты

`tests/test_export.py` параметризует contract suite по каждому
**зарегистрированному** exporter. Установка вашего exporter в test environment
автоматически проверяет каталог файлов, детерминизм — один ledger даёт byte-identical
output — и совместимость со старыми ledgers. Добавьте собственный golden по образцу
встроенных: статический ledger из `tests/fixtures/golden-run/` экспортируется и
сравнивается byte-for-byte.

```bash
pytest tests/test_export.py -k golden
TESTENCE_UPDATE_GOLDENS=1 pytest tests/test_export.py -k golden
```

Fixture ledger намеренно имеет фиксированные timestamps. Ledger от `EvidenceWriter`
получает текущее время и доказывает детерминизм внутри запуска, но не между commits.
Когда upstream format изменится, этот diff станет предметом review.
