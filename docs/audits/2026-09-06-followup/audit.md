# Testence: повторный аудит выполнения R1

Дата: 6 сентября 2026. Проверенный HEAD: `7be8d025f81d9116ab267c59d440e14b377cfce7`.
Версия продукта: `0.1.0.dev0`, schema `testence/1`. База сравнения: `493d81fa6475d4d12b7f66236a4f0af20a0f0090`.

Предыдущее [ТЗ R1 v1.0](../2026-09-06/release-spec.md), [исходный аудит](../2026-09-06/audit.md). Новый этап описан в [ТЗ v1.1](release-spec.md); исполнимая очередь — в [backlog](backlog.md).

## 1. Решение

**NO-GO для заявленного публичного QA alpha R1.** Основа продукта работает, а обычный lifecycle pytest стал существенно точнее. Однако сквозное доверие к результату ещё не обеспечено: после падения worker отчёт может показать все тесты зелёными, отдельные случаи сливаются, required proof не проверяется. Подтверждены небезопасное пересылание auth и чтение артефакта вне run.

Следующий крупный этап — **«Доверенный QA workflow и OSS release candidate»**, то есть доведение R1 до приёмки. Назвать его web beta/R2 означало бы пропустить невыполненные требования предыдущего ТЗ. Наличие исходников, LICENSE и зелёного unit suite не заменяет готовность QA workflow.

В этом аудите не вычисляется процент готовности: требования имеют разную стоимость, а многие зависят от внешней приёмки. **Ни один из G1–G8 пока нельзя признать полностью принятым по доступным свидетельствам.** Это оценка доступных доказательств, а не утверждение, что вся предыдущая работа бесполезна.

## 2. Что изменилось с предыдущего ТЗ

Между базой и HEAD — один коммит `Implement complete pytest lifecycle evidence`: 7 файлов, 705 добавленных и 150 удалённых строк. Изменены plugin, event kinds, модель экспорта, Allure/CTRF, HTML и добавлены три consumer integration tests. Auth, oracle, verdict, corpus grader, CLI и CI workflow этим коммитом не менялись.

Положительный результат подтверждён повторно:

- `setup` и `teardown` failures теперь `broken`, а не `pass`;
- skip/xfail отражаются как `skipped`; обычные pass/fail и non-strict xpass учитываются;
- тест без `ex`, в том числе с PlanSpec marker, получает lifecycle events;
- collection error, collection skip и zero collection записываются;
- нормальный xdist запуск на двух workers не теряет восемь уникально названных параметризованных случаев;
- программный `KeyboardInterrupt` даёт `aborted` для уже начатого теста;
- Allure/CTRF отображают основные новые execution statuses; потребительский тест сравнивает их с JUnit, который генерирует штатный pytest.

Это реальный прогресс по R01 и части R13/R15. Полное выполнение R01 не подтверждено: crash reconciliation и неисполненный остаток scope остаются открыты. JUnit-проверка не означает наличия самостоятельного JUnit exporter Testence.

## 3. Метод и ограничения

Исследованы diff от базы, текущая структура через CodeGraph, затронутые функции и читатели их контрактов. Предыдущие выводы о неизменённых модулях перенесены с указанием основания; ключевые рискованные случаи воспроизведены заново.

Использованы Windows, отдельное locked окружение Python 3.12.12, pytest 9.1.1, pytest-xdist 3.8.0, Playwright 1.62.0, Ruff 0.16.5. Проверки запускались локально. Дополнительные consumer probes не используют браузер, реальные credentials или внешние сервисы. `os._exit(7)` исполняется только в собственном pytest worker. Проверка auth перехватывает вызов HTTP до отправки.

На старте уже существовали незакоммиченные изменения в индексах docs и прежние материалы аудита. Они сохранены. Runtime-код в ходе этого аудита не редактировался. Соседний `testence_wiki` доступен: его vision/roadmap содержат исторические имя Exhibit, этапы и результаты. Они не являются актуальными release receipts.

**Не проверены заново:** Linux/Python minimum matrix, весь browser conformance/corpus, React/warm performance benchmark, два внешних OSS приложения, живой Allure UI/TestOps tenant, внешние агенты и пилоты, настройки GitHub security, права на все данные/ассеты, секреты во всей Git history, dependency vulnerability inventory. Старые численные performance/adoption claims не переаттестованы.

## 4. Проверки

Артефакты и команды: [verification README](../../../outputs/audit-2026-09-06-followup/README.md).

| Проверка | Результат | Что доказывает |
|---|---|---|
| Locked pytest, extras `dev,parallel` | **166 passed, 69.51 s** | Текущий локальный штатный suite; не release acceptance |
| Ruff format | **FAIL: 2 files**, 89 уже отформатированы | `pytest_plugin.py`, `test_pytest_lifecycle.py` нарушают текущий CI gate |
| Ruff lint | PASS | Настроенные lint rules |
| mypy | PASS, 40 source files | Область проверки, принятая CI |
| wheel + sdist build | PASS | Обе дистрибуции собираются |
| Wheel-only venv, consumer cwd вне checkout, Python `-I` | PASS | Импорт из site-packages, CLI, 2 schemas, 4 skills, 1 pytest test, HTML generation |
| Повтор прежних probes | См. таблицу ниже | Lifecycle улучшен; остальные ключевые блокеры сохраняются |
| Новые lifecycle probes | Найдены crash/scope/identity gaps | Реальное выполнение pytest с синтетическими тестами |
| Reader compatibility probes | Найдены corpus и flake regressions | Синтетические входы текущих readers; не полноценный benchmark |

Первый запуск через обычный `uv run` выбрал Python 3.13.11 и пересоздал локальную `.venv` без optional extras: 165 passed, 1 failed из-за отсутствия xdist; Ruff/mypy были недоступны. Этот результат не записан как дефект runtime. Основная проверка повторена в отдельном locked окружении с extras по CONTRIBUTING/CI. При этом README quickstart устанавливает только `dev`, а новый штатный test требует `parallel` — документационные пути стоит согласовать.

## 5. Подтверждённые проблемы

P0 означает блокировку заявленной приёмки продукта, а не CVSS. F-ID относятся к этому повторному аудиту; A-ID — к предыдущему.

### F01 · P0 · Worker crash по-прежнему превращается в зелёный экспорт

**Воспроизведение:** два синтетических теста на `xdist -n 2`, один делает `os._exit(7)`, второй проходит. Pytest exit=1; записан `worker.crash`; терминальное событие есть только у второго теста. `LoadedRun` и CTRF показывают **2 tests / 2 passed / 0 failed**.

Причина: [Test.status](../../../src/testence/export/_model.py) по умолчанию `passed`; отсутствие `test.end` не снижает статус. [pytest_testnodedown](../../../src/testence/pytest_plugin.py) записывает сообщение о worker, но не восстанавливает результат конкретной начатой попытки. Контроллер и workers создают свои `run.end`; их counts не превращаются в один reconciled manifest.

Это подтверждает, что R01 нельзя закрыть отдельно от R02/R03 и export reconciliation. Данные: `crash-consumer` в [lifecycle-results.json](../../../outputs/audit-2026-09-06-followup/lifecycle-results.json). Связь: A03 → R01/R03/R13/R15.

### F02 · P0 · Два разных теста становятся одним successful result

В настоящем consumer-проекте `a/test_a.py::test_save` падает, `b/test_b.py::test_save` проходит. Ledger содержит два terminal events, run.end правильно считает 1 failed + 1 passed. Но export model группирует по короткому `test`, и CTRF показывает **1 passed / 0 failed**.

[Plugin `_test_id`](../../../src/testence/pytest_plugin.py) явно оставляет `item.name` до R02; [LoadedRun.from_events](../../../src/testence/export/_model.py) использует этот ключ. Полный nodeid в start event не предотвращает слияние. Нужна единая identity во всех consumers, а не только в ledger. Данные: `duplicate-consumer`. A02 → R02/R03/R13.

### F03 · P0 · Неисполненная часть выбранного scope исчезает

После `pytest -x` выбраны 3 теста, выполнен только первый; `run.end.not_run=0`, CTRF показывает один тест. При KeyboardInterrupt из 2 выбранных записан один aborted, второй отсутствует. Сам pytest возвращает корректный ненулевой exit, но отчёт не объясняет полноту scope.

[`_close_lifecycle`](../../../src/testence/pytest_plugin.py) финализирует только `state.items`, которые появляются при старте теста; collection inventory не участвует в reconciliation. Нужен явный остаток selected scope и единый session summary. A03 → R01/R03/R15.

### F04 · P0 · Смена spelling статусов сломала измеритель correctness

В [bench/corpus/run.py](../../../bench/corpus/run.py) `run_item` считает failure любой status, отличный от `pass`. Новый plugin пишет `passed`. Синтетический вход из 10 успешных cases с exit=0 превращается в 10 failed claims, healthy control оценивается как red.

Это **новая регрессия интеграции после lifecycle-коммита**, а не повтор старого false-green дефекта grader. Одновременно прежний дефект сохраняется: empty healthy control с exit=2 и 0/10 claims получает `outcome_ok=true, observed=green` с warning. Нужны normalizer и независимая проверка completeness/exit/ground truth. F04/A09 → R03/R18/R19.

Дополнительно [metrics.aggregate](../../../src/testence/metrics.py) для одного и того же теста/code digest со статусами `pass` и `passed` сообщает `interaction_flake_rate=1.0`. Это миграционный артефакт, а не наблюдённый флейк приложения. Данные: [consumer-results.json](../../../outputs/audit-2026-09-06-followup/consumer-results.json). → R17/R20.

### F05 · P0 · Claims и verdict ещё не обеспечивают proof

Тест с required API claim и телом `pass` имеет `passed`, 0 oracle events. Отдельной assurance axis и enforcement required assertions нет. Это не доказывает ошибочность самого pytest pass; это доказывает отсутствие требуемого quality gate.

Verdict с `oracle.json#/999/nonexistent` принимается, если файл существует, хотя сам pointer не существует. `diff_views({}, {})` и сравнение одинаковых старых значений возвращают пустой diff: сравнение двух представлений не проверяет ожидаемый бизнес-результат само по себе.

Данные: [probe-results.json](../../../outputs/audit-2026-09-06-followup/probe-results.json). Исходники: [contracts](../../../src/testence/contracts/verdict.py), [oracle](../../../src/testence/oracle.py), [writer](../../../src/testence/evidence/writer.py). A04/A05/A13 → R04/R05/R09.

### F06 · P0 · Auth и артефакты ещё небезопасны для публичного workflow

Повторены три независимых синтетических случая:

1. [ApiClient](../../../src/testence/api.py) добавляет Authorization и Cookie trusted HTTPS-сессии к абсолютному URL другого HTTP-origin. Реальная отправка перехвачена mock.
2. Note-canary без изменений попадает в ledger: централизованная redaction перед persist отсутствует.
3. `pack.dir='../external'` позволяет Allure exporter скопировать специально созданный файл вне run. Исследован только task-owned synthetic файл.

Это не сообщение об обнаружении реальных секретов в репозитории. Полный tree/history scan ещё нужен. A06/A07/A08 → R06/R07/R08.

### F07 · P0 · Allure JSON пока не обеспечивает TestOps-сценарий

При `ALLURE_TESTPLAN_PATH`, выбирающем один тест, plugin исполняет все восемь синтетических тестов. До исправления lifecycle один из них был невидим — теперь видимы все восемь, но выбор scope не работает.

Экспортёр имеет steps/attachments/status mapping и historyId от nodeid; устойчивые case/variant/attempt IDs, fixture containers и полный metadata mapping ещё требуют R02/R13. Live TestOps round trip не проверен. Документация TestOps прямо относит чтение testplan к runtime adapter; upload сам по себе не выполняет выбор. [Официальный контракт allurectl](https://docs.qameta.io/reference/ecosystem/allurectl/).

В [EN](../../en/reporting.md) и [RU](../../ru/reporting.md) остаётся рецепт `pytest ... || true` без восстановления test exit. После успешного export/upload такой рецепт способен скрыть провал job. A10/A11 → R13/R14/R15/R20.

### F08 · P1 · Миграция lifecycle и release hygiene не завершены

- Strict XPASS даёт failed, что правильно для execution, но отдельный `xpass` отсутствует в terminal event воспроизведения. Требуемая семантика xpass/reason ещё неполна.
- Новые статусы используются при прежнем `testence/1`; не все readers совместимы — см. F04. Нужна документированная migration, общий normalizer и compatibility corpus.
- Ruff format gate падает на двух изменённых файлах. Это конкретный blocker текущего quality job по локально воспроизведённой команде; remote CI не проверялся.
- README verdict не проходит собственную схему: отсутствует обязательный `plan_id`.
- LICENSE, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, CODEOWNERS, templates и pinned CI actions уже есть. Однако SECURITY предлагает условный приватный канал «when available»; наличие действующего канала не подтверждено.

Не следует заново ставить «создать CI/LICENSE/skills» как работу с нуля: нужно завершить и проверить существующие механизмы. → R01/R19/R20/R24.

## 6. Матрица выполнения предыдущего ТЗ

«Частично» означает реализованную основу, а не приёмку. «Нет целевого контура» означает отсутствие требуемого пользовательского пути в доступной реализации. «Не подтверждено» не равно доказанному отсутствию внешней деятельности.

| R-ID | Статус на HEAD | Что уже есть | Остаток до приёмки |
|---|---|---|---|
| R01 | Частично, существенный прогресс | Hooks, phases, collection, no-ex, основные статусы | F01/F03, strict XPASS, consumer parity, полная interruption matrix |
| R02 | Частично | run ID, nodeid как metadata | Устойчивые project/case/variant/attempt IDs, коллизии F02 |
| R03 | Частично | collection/run events, shard files | Manifest reconciliation, recovery, fail-closed readers, selected remainder |
| R04 | Частично | PlanSpec/1, marker binding, JSON schema | Assertion evidence, digests, assurance и required proof |
| R05 | Частично | UI/API helper, diff, save-and-verify | Expected predicate, operation binding, polling/deadline, typed oracle failures |
| R06 | Частично, P0 открыт | Auth strategies, config, session cache | Origin/cookie/redirect safety, role lifecycle, TTL/identity isolation |
| R07 | Нет целостного safety boundary | Ограничения отдельных путей/проверок | Redaction до записи, все sinks, containment, image policy |
| R08 | Частично | JSONL, packs, section budgets | Bounded acquisition, complete manifest, recovery, retention, portable refs |
| R09 | Частично | Verdict validator, proposed heal | Pointer resolution, run/digest binding, safe apply/proof, reasoned abstention |
| R10 | Частично | Serial/xdist, attached/warm режимы | Test context/data isolation, ownership/cleanup, CI profiles |
| R11 | Частично | Semantic targets, exact text, waits | Strict cardinality, expected state, correlation, fast-profile semantics |
| R12 | Частично | Chromium backend и базовые web actions | Доказанная матрица frames/shadow/popup/files/dialog/keyboard |
| R13 | Частично, статусы улучшены | Allure JSON/steps/attachments | Identity/attempts/fixture mapping, реальный consumer acceptance |
| R14 | Нет целевого контура | Возможность экспортировать результаты | Testplan selection, namespaces, live TestOps round trip |
| R15 | Частично | CTRF, pytest-native JUnit | Exit integrity, completion quality gate, безопасные CI recipes |
| R16 | Частично | CLI, 4 packaged skills, plan/verdict validation | doctor/init/update, typed services, managed submit, 2 client receipts |
| R17 | Частично | Исторические perf samples/budgets, metrics | Новый профиль, resources/flake correctness, raw samples и RC receipts |
| R18 | Частично, grader не пригоден как gate | Seeded corpus, controls | F04, independent evaluator, 40 cases, 2 OSS SUT, external reproduction |
| R19 | Частично | Windows/Linux CI matrix, lock, build | Format fix, wheel/browser consumer CI, minimum deps, scans/SBOM/provenance |
| R20 | Частично | Большая EN/RU документация, migration идеи | Validated snippets, HTTPS onboarding, актуальные единые claims/support |
| R21 | Нет целевого контура | Project profiles и концепция quality policy | Versioned shared pack, 3 repos, conflict/rollback, actionable QA queue |
| R22 | Частично | Engine protocol, exporter separation | Platform-neutral contracts, capability negotiation, fake-engine conformance |
| R23 | Не подтверждено | Предыдущий план пилота | 3 внешние команды, 5 onboarding, 2 independent reproduction, повторное использование |
| R24 | Частично | Apache-2.0 и community files | Реальные security/rights receipts, release manifest, доступная demo, owner decision |

Для R05–R12/R16–R24 существенная часть оценки опирается на исходный аудит и отсутствие изменений соответствующих модулей между commits. Это не новый полный security/performance/UX audit каждого такого модуля.

## 7. Продуктовый вывод

Сохранить pytest-native тесты, Playwright backend, намерения действий, переносимые skills, локальное evidence и независимый export. Переписывание runtime, свой TMS, SaaS dashboard или mobile drivers сейчас не решают подтверждённые проблемы.

Нужна одна законченная пользовательская цепочка: **QA определяет проверяемый риск → разработчик/агент добавляет тест → независимый oracle доказывает expected state → CI сообщает полный исход → QA разбирает actionable failure в привычной инфраструктуре → repair принимается с proof**.

Для OSS первый успех должен быть доступен без SSH credentials и доступа к внутреннему стенду; первое осмысленное падение с объяснением столь же важно, как green demo. Продуктовая полезность измеряется временем review/triage и повторным использованием, а не числом кликов, test count или числом документов.

Новый [backlog](backlog.md) начинает с воспроизведённых ошибок и переводит оставшиеся R01–R24 в конечные этапы с проверяемыми receipts. В ходе аудита packages не публиковались, внешние команды не получали сообщений, настройки remote repository не менялись.
