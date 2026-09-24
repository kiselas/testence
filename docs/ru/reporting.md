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
| `allure` | `<n>-result.json` на attempt, fixture containers, attachments, `environment.properties`, `categories.json` | идентичности, совместимые с allure-pytest, метаданные `@allure.*` и маркера, дерево сьютов, читаемые замаскированные параметры, статус failed/broken с полным трейсом, owner/risk/requirement/issue links, steps и redacted evidence |
| `ctrf` | один `ctrf-report.json` | summary counts, tags, плоские step intents и путь pack |

JUnit XML намеренно не является exporter: `pytest --junitxml=…` уже создаёт его
корректно, в том числе под `-n`, а GitLab/Jenkins/GitHub читают его напрямую.

## Загрузка результатов в Allure TestOps

Два способа передать результаты в TestOps; оба пишут стандартный каталог *Allure results*:

- **Потоково** (рекомендуется): `--testence-allure-results DIR` (или
  `TESTENCE_ALLURE_RESULTS`) пишет каждый результат сразу после окончания теста. Тогда
  `allurectl watch` показывает, как заполняется запуск, а job, убитый на середине,
  сохраняет готовые результаты. Файлы появляются атомарно, вложения — раньше
  ссылающегося на них результата, а байты совпадают с `testence export --to allure`
  после прогона.
- **После прогона**: `testence export <run> --to allure`, затем `allurectl upload`.

Код завершения pytest нужно сохранять явно: успешная загрузка не должна делать
упавший прогон зелёным. Задайте прогону явный id, чтобы параллельные job не подобрали
чужой каталог. Если job запущен из TestOps, сначала получите его test plan:

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

Сверьте имена флагов со своей версией `allurectl` (`allurectl watch --help`). Вариант
после прогона заменяет строку с `watch` на `pytest tests_e2e/ -q`, затем
`testence export "$RUN" --to allure` и `allurectl upload "$RUN/allure-results"`.

Для повторяемой загрузки с машинной квитанцией все идентичности задаются явно. Опции
`delivery run` идут перед каталогом прогона, потому что оставшиеся аргументы — команда
загрузчика:

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

Квитанция доставки идемпотентна для run/project/launch/job-run и точного digest
артефакта. Успешная квитанция переиспользуется; таймауты и ненулевой код загрузчика
повторяются в пределах заданного лимита. `ci evaluate` записывает коды тестов, качества
и доставки отдельно и возвращает первый провал, поэтому успешная загрузка не скрывает
упавший или неполный прогон.

### Перенос набора с allure-pytest

По умолчанию (`export.allure.naming: allure-pytest`) результаты попадают на те же
идентичности, что создаёт allure-pytest: `fullName` — `package.module[.Class]#test` без
параметров, `testCaseId`/`historyId` считаются по формулам allure-pytest. Существующие
тест-кейсы TestOps, их история и связи ручных кейсов с автотестами сохраняются.
`@allure.feature`, `story`, `severity`, `id`, `label`, `link`, `issue`, `testcase`,
`title` и `description` читаются из создаваемых ими меток — с установленным
allure-pytest или без него. Тест, привязанный к кейсу PlanSpec, сохраняет идентичность
Testence: она переживает переименование. `export.allure.naming: nodeid` возвращает
идентичности, которые экспортировал Testence 0.1.0a1.

```json
{"export": {"allure": {"naming": "allure-pytest", "parameters": "values"}}}
```

Описать тест для отчётов без PlanSpec:

```python
@pytest.mark.testence(
    allure_id=1042,
    title="Оплата сохранённой картой списывает деньги один раз",
    severity="critical",
    labels={"feature": "Корзина", "story": ["Оплата картой"]},
    links=["https://docs.example.test/pay", {"url": "https://jira.example.test/PAY-7", "type": "issue"}],
)
def test_pay_with_saved_card(ex): ...
```

Если один `allure_id` стоит на двух разных тестах, выдаётся предупреждение: их
результаты делили бы один кейс TestOps. Предупреждение выдаётся и при запуске
allure-pytest с `--alluredir` рядом с загрузкой Testence: результаты задвоятся.

### Что показывает карточка

- **Статус.** Расхождение ассерта или оракула — `failed`; проблема браузера, сети или
  таймаута, неокончательный оракул и ошибка в коде самого теста — `broken`.
  `categories.json` группирует их так же.
- **Трейс.** Полный отчёт pytest о падении, ограниченный и замаскированный, а не только
  первая строка.
- **Имя и описание.** Явный заголовок (`@allure.title` или маркер), затем заголовок
  сценария PlanSpec, затем имя pytest. Явное описание, затем claims PlanSpec с
  формулировками, затем docstring.
- **Дерево.** `parentSuite`/`suite`/`subSuite`, `package`, `testClass`, `testMethod` и
  `titlePath` — как у allure-pytest.
- **Теги.** Пользовательские маркеры без аргументов, как у allure-pytest; `parametrize`,
  `usefixtures`, `skip`, `xfail` и собственные метки Testence тегами не становятся.
- **Параметры.** Читаемые замаскированные значения; параметр с именем секрета помечен
  `masked`. `export.allure.parameters: digest` возвращает значения только в виде digest.
  pytest вставляет значения параметров в id теста, который виден в каждом отчёте:
  Testence предупреждает, если значение параметра с именем секрета попало в id, —
  задайте такому `parametrize` аргумент `ids=`.
- **Вложения.** Замаскированный evidence pack падения, скриншот ещё и на упавшем шаге,
  а с `evidence.screenshots: always` — страница прошедшего теста.
- **Фикстуры, повторы и метаданные плана.** Setup и teardown становятся элементами
  container; каждый повтор — отдельный результат в одной истории; owner, risk,
  requirements и issues из PlanSpec становятся метками и ссылками `tms`/`issue`.

### Выбор тестов по плану TestOps

`ALLURE_TESTPLAN_PATH` (формат `1.0`) применяется при сборе тестов. Запись выбирает по
`id` (все варианты с этим `allure_id`, поэтому перезапуск параметризованного кейса
запускает все его варианты) или по `selector`: `fullName` в стиле allure-pytest (все
варианты), точный nodeid pytest (один вариант) или `testence://<project>/<case>/<variant>`.
Перекрывающиеся и повторяющиеся записи выбирают тест один раз; неизвестные поля
игнорируются с предупреждением.

Запись, не совпавшая ни с одним собранным тестом (кейс переименован или удалён после
сборки плана), попадает в отчёт, а остальной план выполняется: предупреждение pytest,
событие ledger `testplan.unresolved`, `testence.testplan_unresolved` в
`environment.properties`, сводка CTRF и квитанция CI. Пайплайны, которым нужно падать,
передают `--testence-testplan-unresolved=fail` (или
`TESTENCE_TESTPLAN_UNRESOLVED=fail`), а `testence ci evaluate --testplan-unresolved fail`
превращает такие записи в провал качества. План, в котором не нашлось ни одного теста,
всегда падает до выполнения. Намеренно пустой план требует
`--testence-empty-testplan=noop`.

Проверка T15 использует закреплённый Allure Report 3.14.3:

```bash
testence export <run-dir> --to allure -o allure-results
npx --yes allure@3.14.3 awesome allure-results -o allure-report --single-file
```

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
