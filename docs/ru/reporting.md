# Отчётность: экспортёры поверх журнала

Testence создаёт один authoritative artifact на запуск —
`runs/<run-id>/run.jsonl` ([схема `testence/1`](evidence-schema.md)). Всё, что читают
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

| Exporter | Что пишет | Что переносит |
|---|---|---|
| `allure` | `<n>-result.json` на тест, attachments, `environment.properties` | вложенные steps, markers как tags, evidence pack как attachments, fingerprint окружения |
| `ctrf` | один `ctrf-report.json` | summary counts, tags, плоские step intents и путь pack |

JUnit XML намеренно не является exporter: `pytest --junitxml=…` уже создаёт его
корректно, в том числе под `-n`, а GitLab/Jenkins/GitHub читают его напрямую.

## Сохранение существующего Allure TestOps pipeline

`allure` пишет формат **каталога результатов**, а не in-process модель SDK.
`allurectl` загружает такой каталог независимо от производителя. Поэтому миграция
дешева: **меняется test command, pipeline не меняется**. Endpoint, project id и token
остаются прежними.

```yaml
run_tests:
  script:
    # красный suite всё равно содержит результаты для загрузки
    - pytest tests_e2e/ -q || true
    - RUN=$(ls -dt runs/r-* | head -1)
    - testence export "$RUN" --to allure
    - allurectl upload "$RUN/allure-results"
  artifacts:
    when: always
    paths: [runs/]
```

Две вещи сохраняются благодаря проектным решениям:

- **Имена markers.** Они переходят в Allure tags без изменений. Saved filters,
  dashboards и scheduled selective runs зависят от этих строк, поэтому переименование
  незаметно опустошит чужой filter.
- **История.** `historyId` — hash только nodeid теста, поэтому trends в TestOps
  следуют за тестом между запусками, а не создают несвязанные одноразовые результаты.

Не сохраняется streaming: результаты появляются при export, а не во время запуска,
поэтому `allurectl watch` нечего наблюдать. Для suite длительностью от секунд до минут
это не проблема. Если streaming станет блокером adoption, tripwire ADR-0013 требует
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
| `Test` | `name`, `nodeid`, `file`, `markers`, `status`, `duration_ms`, `start`/`stop`, `error`, `steps`, `oracles`, `pack_dir` |
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
