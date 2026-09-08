# Testence: аудит перед публичным релизом

Дата: 6 сентября 2026. Исследованный commit: `493d81fa6475d4d12b7f66236a4f0af20a0f0090`.
Версия: `0.1.0.dev0`. Статус: аудит и предлагаемое ТЗ, не выполненный релиз.

Читать вместе с [конечным ТЗ](release-spec.md), [планом принятия продукта](adoption.md) и [реестром работ](backlog.md).

## Вывод

У Testence есть подходящая основа для продукта: обычный pytest, быстрый Playwright runtime, намерения действий, API-oracles, переносимые skills и независимые от runner экспортёры. Переписывать это ядро на другой язык или строить собственный браузерный движок сейчас не обосновано.

Однако публичный релиз для QA-команд блокирует **достоверность результата**. Воспроизведены случаи, когда журнал сообщает об успехе при setup/teardown error, объединяет разные тесты и считает незавершённое выполнение успешным. Уязвим и измеритель качества: пустой аварийный запуск healthy control оценивается как корректный green. Это важнее очередной оптимизации клика.

Вторая проблема — разрыв между экспортом Allure JSON и полноценной интеграцией с TestOps. Для пользователя, который ведёт несколько проектов, важны сохранение case identity, управляемый выбор тестов, попытки, владельцы, параметры, связи с требованиями и корректный статус CI.

Рекомендуемая продуктовая цель: **QA задаёт стандарт качества для нескольких проектов; разработчики и агенты создают и поддерживают проверяемые тесты; Testence обеспечивает исполнение, доказательства и интеграцию с существующей тестовой инфраструктурой.** Число проектов на одного QA — гипотеза для пилота, а не обещание сократить штат.

## Что исследовано и как

- Код: runner/plugin, DSL, engine, auth/API, oracle, contracts, evidence, triage, metrics, report, Allure/CTRF, CLI и упаковка.
- Документы: README, EN/RU audit/positioning/roadmap, architecture, reporting, skills/workflow, demo, launch protocol, benchmark/corpus и ADR.
- Автоматические проверки: штатный pytest, Ruff, mypy, сборка sdist/wheel, установка wheel в отдельное окружение, React latency gate.
- Изолированные воспроизведения: настоящий pytest plugin с подменённым браузерным fixture; синтетические журналы, verdict и credentials. Реальные приложения и реальные секреты не использовались.
- Рынок/интеграции: актуальные первичные документы Playwright, Allure Report/TestOps, Stagehand, Midscene, Appium, TestRail и Xray. Возможности из документации не считаются измеренной совместимостью Testence.

Не проверялись: live Allure TestOps tenant, hosted TMS, реальные внешние приложения, Linux/macOS execution, повтор всего mutation corpus, независимые агентные сессии и проникновение в реальные системы. Каталог `D:/Projects/exhibit_wiki` в момент аудита отсутствовал. Remote CI run и настройки private vulnerability reporting не проверялись; исследован workflow в репозитории.

### Результаты проверок

| Проверка | Результат | Ограничение |
|---|---|---|
| `uv run pytest -q --basetemp=outputs/audit-2026-09-06/pytest-main --tb=short` | **163 passed, 57,86 s** | Windows, Python 3.12.14; один процесс |
| Штатный `uv run pytest -q` | 92 passed, 71 setup errors | Причина: WinError 5 на системном pytest temp-каталоге; это ограничение окружения, не 71 дефект Testence |
| `uv run ruff format --check src tests bench` | 90 files already formatted | Текущая конфигурация |
| `uv run ruff check src tests bench` | passed | Текущий набор правил |
| `uv run mypy src/testence bench/react_latency.py bench/warm_runner_latency.py` | 40 source files, passed | Не полная строгая типизация всех тестов/bench |
| `uv build --out-dir outputs/audit-2026-09-06/dist` | wheel и sdist собраны | Сборка сама по себе не доказывает UX установки |
| Чистое venv + установка собранного wheel | import, CLI, 2 schemas, 4 skills, plan validation passed | Python 3.13.11, pytest 9.1.1, Playwright 1.62.0; browser E2E из этого venv не запускался |
| `uv run python bench/react_latency.py --repeats 3 --port 18854 --check --output outputs/audit-2026-09-06/react-latency.json` | budget passed | Один локальный production-built React SUT; n=3 — диагностика, не сравнительная статистика |

Синтетические проверки: [скрипт](../../../outputs/audit-2026-09-06/probes.py), [результаты JSON](../../../outputs/audit-2026-09-06/probe-results.json), [pytest lifecycle log](../../../outputs/audit-2026-09-06/lifecycle.log). Повтор: `uv run python outputs/audit-2026-09-06/probes.py`. Скрипт фиксирует текущее поведение, а не утверждает, что оно правильно.

## Подтверждённые блокеры

P0 здесь означает блокировку заявленного публичного сценария. Это приоритет продукта, не CVSS-оценка уязвимости.

### A01 · P0 · Setup, teardown, skip и xfail превращаются в pass

Источник: [pytest_plugin.py](../../../src/testence/pytest_plugin.py), `ex`, строки 350–449; [CTRF](../../../src/testence/export/ctrf.py), [Allure](../../../src/testence/export/allure.py).

`ex` читает только `reports['call'].failed` в финализаторе fixture. Ошибка setup после создания `ex`, skip/xfail и ошибка другого teardown не превращают это значение в fail. Финальный teardown report в этот момент ещё может не существовать. Тесты, не использующие `ex`, вообще не образуют полноценную запись выполнения.

Воспроизведение: pytest сообщил `skip`, `xfail`, ошибку setup и ошибку teardown; все четыре получили `test.end.status=pass`. Отдельный тест с PlanSpec, но без `ex`, отсутствует в журнале. Сам pytest вернул ненулевой код — дефект находится в слое Testence evidence/reporting, а не в pytest.

Следствие: QA и агент могут получить зелёную картину в Allure, несовместимую с фактическим выполнением. Нужна фиксация состояния через lifecycle hooks, включая collection, три фазы и завершение сессии. → R01, R03, R13.

### A02 · P0 · Разные тесты и попытки теряют идентичность

Источник: `pytest_plugin.ex` использует `request.node.name`; [LoadedRun.from_events](../../../src/testence/export/_model.py) группирует по `doc['test']`; [EvidenceWriter.test_dir](../../../src/testence/evidence/writer.py) нормализует и обрезает имя до 80 символов.

Воспроизведение: `a/test_a.py::test_save=fail` и `b/test_b.py::test_save=pass` превратились в **один passed result**. Полный nodeid в payload не спасает: ключ группировки остаётся коротким именем. Нормализация имён директорий дополнительно допускает коллизии; shard-файлы решают запись между процессами, но не identity теста/попытки.

Нужны независимые project/case/variant/run/attempt IDs, устойчивые связи с TMS и digest в пути артефакта. → R01, R02, R13, R14.

### A03 · P0 · Незавершённый журнал выглядит успешным

Источник: [Test.status и LoadedRun.from_events](../../../src/testence/export/_model.py), default `pass`; [parse_ledger](../../../src/testence/kernels/reference.py) напрямую вызывает `json.loads` для каждой строки.

Воспроизведение: один `test.start` без `test.end` даёт passed test. Отдельно по исходникам: оборванная JSON-строка вызывает исключение, recovery валидного префикса не реализован.

Нужны explicit incomplete/aborted, сверка expected/collected/executed и обработка повреждённого хвоста без молчаливого игнорирования повреждений посередине. → R01, R03, R08.

### A04 · P0 · Связь с claim ещё не доказывает claim

Источник: [PlanSpec](../../../src/testence/contracts/plan.py), `EvidenceWriter.bind_test`, `pytest_plugin.ex`.

Claims автоматически прикрепляются к событиям теста, но это membership, а не доказательство выполнения assertion. Воспроизведение: тест с обязательным API oracle в PlanSpec, тело `pass`, получил pass при **нуле oracle events**.

Нельзя выдавать «все привязанные claims доказаны» на основании этой связи. Нужны отдельные observation/assertion events с expected/actual, explicit claim IDs, типом oracle и проверкой полноты required claims. Legacy pytest pass может оставаться pass исполнения, но assurance должен быть `unverified`. → R04, R05.

### A05 · P0 · Валидатор принимает несуществующую точку evidence

Источник: [verdict._validate_against_pack](../../../src/testence/contracts/verdict.py), `_evidence_path`.

Проверяется безопасный путь и существование файла, но JSON fragment отбрасывается. Воспроизведение: `oracle.json=[]`, ссылка `oracle.json#/999/nonexistent` принята. Verdict не содержит обязательного run/attempt ID и digest pack/plan/test-кода.

Валидный JSON не гарантирует правильность диагноза модели. Программно можно и нужно проверять существование адресованного события, run/attempt binding и непротиворечивость статусов. Semantic truth дополнительно проверяется corpus и человеком/политикой. → R04, R09.

### A06 · P0 · Нет единой защиты содержимого evidence

Источник: [EvidenceWriter.emit](../../../src/testence/evidence/writer.py), [engine taps](../../../src/testence/engine/playwright_cdp.py), [assemble_pack](../../../src/testence/triage/pack.py), `AuthContext.describe`.

Записываются произвольные note/oracle данные; сохраняются request bodies и mutation/error responses, URL, console, ARIA и screenshots. `AuthContext.describe` включает `user` целиком. Обрезка pack может сохранять полный оригинал в `full-*`; это ограничение агентного контекста, а не приватности.

Воспроизведение: синтетический canary попадает в ledger без redaction. Это не утверждение об обнаруженных реальных секретах в Git — полный secret/history scan не выполнялся.

Нужны редактирование до записи, allowlist capture, отдельная политика изображений/trace, retention, canary gate для всех представлений и предсказуемая деградация evidence. → R07, R08, R17.

### A07 · P0 · API-клиент пересылает auth на другой origin

Источник: [ApiClient.request](../../../src/testence/api.py), [AuthContext.cookie_header](../../../src/testence/auth/base.py).

Абсолютный `http…` URL разрешён, к нему добавляются все headers/cookies сессии. Domain/path/secure cookie semantics не учитываются. Воспроизведение с перехватом HTTP-вызова: запрос на другой host по HTTP получил `Authorization` и `Cookie` для trusted HTTPS origin. Реальный сетевой запрос не делался.

Также «same-session» сейчас означает снимок авторизации: не гарантируется актуальность cookies после refresh/logout. Это может исказить oracles ролей и данных. Нужны origin policy, cookie jar либо согласованный APIRequestContext, redirect policy и явная синхронизация сессии. → R06.

### A08 · P0 · Импортируемый pack может скопировать файл вне run

Источник: [LoadedRun.pack_path](../../../src/testence/export/_model.py), Allure `_attachments`.

Путь из ledger складывается с run directory без проверки resolved containment. Воспроизведение: `pack.dir='../external'` привело к копированию синтетического `oracle.json` из соседней директории в Allure output.

Граница эксплуатации: экспорт специально подготовленного недоверенного run. Это не удалённое выполнение кода. Но для пересылки артефактов между агентами/командами путь должен быть недоверенными данными. Нужна единая проверка traversal, абсолютных путей, symlink/junction и ограничений размера. → R07, R08.

### A09 · P0 · Healthy control с нулём результатов оценивается green

Источник: [bench/corpus/run.py](../../../bench/corpus/run.py), `evaluate`, строки около 144–167.

`went_red` вычисляется из failed_claims; отсутствие claims даёт только warning. Воспроизведение: `exit_code=2`, `claims_seen=0`, `failed_claims=[]` на healthy control → `outcome_ok=true, observed=green`.

Это не опровергает автоматически исторические 51 item-runs; исходные запуски нужно отдельно переоценить. Но существующий evaluator не годится как единственный release gate. Проверять полноту, фазы, terminal events, exit code и ground truth независимо от агрегатора Testence. → R18.

### A10 · P0 для QA-релиза · Allure exporter не равен TestOps adapter

Источник: [Allure exporter](../../../src/testence/export/allure.py), [reporting guide](../../en/reporting.md), [CLI](../../../src/testence/cli.py).

Реализованы результаты, вложенные steps, attachments, marker names → tags, environment и стабильный SHA-256(nodeid) historyId. Не представлены полноценные case IDs, параметры теста, владельцы, requirement/issue links, fixture containers и отдельные attempts. Не реализовано чтение `ALLURE_TESTPLAN_PATH`.

Воспроизведение: testplan выбирал один тест; pytest запустил весь синтетический модуль, в журнал попало семь тестов, ещё один без `ex` оказался невидим. Поэтому утверждение документации о сохранении scheduled/selective runs при простой замене команды преждевременно.

Документация Allure различает `historyId`, `testCaseId` и другие identifiers. TestOps selective execution требует, чтобы runtime adapter прочитал testplan. Один лишь export этого не обеспечивает. [Allure identifiers](https://allurereport.org/docs/how-it-works-test-identifiers/), [allurectl](https://docs.qameta.io/reference/ecosystem/allurectl/).

→ R02, R13, R14, R15.

### A11 · P0 для CI-документации · Пример маскирует красный тестовый запуск

Источник: EN/RU reporting, рецепт `pytest ... || true`, затем выбор latest run и upload.

В примере не восстанавливается исходный test exit code. При успешном export/upload job может оказаться green. Выбор latest directory способен взять чужой/stale run при параллельных jobs.

Нужны конкретный run ID/manifest, always-publish и финальный статус, учитывающий тесты, полноту proof и ошибки публикации. Это вывод по скрипту; live CI pipeline не запускался. → R15, R20.

## Другие существенные ограничения

| ID | Приоритет | Наблюдение | Последствие и работа |
|---|---|---|---|
| A12 | P1, обязательный R1 | Engine и page/context session-scoped; `reset_taps` очищает buffers, не cookies/storage/DOM | Нет изоляции по умолчанию, риск order dependence; R06, R10 |
| A13 | P1, обязательный R1 | `save_and_verify` сравнивает UI и API, но не отдельное expected intent; `diff_views({}, {})=[]` | Две одинаково неверные/stale стороны согласуются. Это ограничение helper, не обещание, что каждый существующий тест слабый; R05 |
| A14 | P1, обязательный R1 | URL substring, optional method; два rAF после response, один read API; результат readiness не проверяется | Возможны совпадение не того запроса и false red на eventual consistency; R05, R11 |
| A15 | P1, обязательный R1 | Несколько assertions делают `.first`; click/fill имеют opt-in `force`; fast flags не отдельный proof profile | Exact text не означает strict cardinality. Нужны single/many assertion semantics и запись модификаций поведения; R11 |
| A16 | P1, обязательный R1 | Chromium-only implementation, один основной page; монолитный web-oriented Engine protocol | Для web breadth нужны frames/popups/files; для mobile — capabilities, а не обещание бесплатной замены engine; R12, R22 |
| A17 | P1, обязательный R1 | `heal.propose` при пустом списке candidates подсказывает real_bug; поиск первых 400 элементов | Недоступная страница/iframe/другая роль не доказывают удаление. Score — similarity, не calibrated probability; R09 |
| A18 | P1, обязательный R1 | Session cache сохраняет cookies обычным JSON без TTL/проверки личности/явного ACL; browser retained при fail | Нужны opt-in dev profile, scoped cache и обязательный cleanup CI; R06, R10 |
| A19 | P1 | Evidence buffers — списки; bodies читаются целиком до среза; fsync каждого event; весь ledger читается и сортируется | Возможные memory/I/O bottlenecks; скорость массовой suite не измерена; R08, R17 |
| A20 | P1, обязательный R1 | Нет `doctor`, agent init/status/update и managed verdict submit | Pack внутри wheel существует, но повторяемое подключение пользователя ещё отсутствует; R16 |
| A21 | P1, обязательный R1 | CI запускает pytest/Ruff/mypy/build, но не production SUT benchmark и corpus; `test_react_latency_budget` проверяет расчёт budget | Нельзя называть performance/correctness corpus защищённым CI; R17, R18, R19 |
| A22 | P1, обязательный R1 | Старый audit/competitive-landscape утверждают, что нет CI/skills/PlanSpec и quality gates красные | Эти оценки устарели. README JSON verdict тоже не проходит собственную схему; R20 |

## Аудит методов тестирования

Сильная часть — детерминированные сценарии, semantic targets, exact text, явные наблюдения UI/API, положительные и отрицательные mutations, controls и golden export tests. Это полезнее роста количества сгенерированных тестов без проверки их чувствительности.

Но «UI совпал с API» — только один класс oracle. Оба слоя могут вернуть старое состояние, разделять ошибочную логику или читать разные моменты транзакции. Same-session означает согласование прав пользователя, а не независимый источник истины. API-oracle может быть независим от DOM и одновременно зависим от той же backend-ошибки.

ТЗ должно сделать обязательными для каждого нового критичного сценария:

1. Expected outcome из требования, включая точные значения/инварианты, а не из фактически увиденного ответа.
2. Типы проверок: happy path, границы/классы эквивалентности, permissions, негативный эффект, восстановление/повтор, где применимо.
3. Явный источник oracle и ограничения его независимости; empty/invalid/read-failed не равны доказательству успеха.
4. Proof-sensitive control: healthy → намеренный дефект → healthy, с проверкой причины. Автор теста не получает скрытый truth label.
5. Для eventual consistency — deadline и наблюдение конкретного expected state. Повтор чтения допустим; повтор бизнес-действия не заменяет корректную синхронизацию.
6. Для flaky/retry — хранение первой попытки, состояния данных и всех последующих результатов. «Зелёный после retry» — отдельный сигнал.

UI layer не должен заменять unit/component/API/contract testing. QA определяет слой каждой проверки. В R1 Testence может ссылаться на результаты других layers, сохраняя собственную специализацию на web journeys. Visual diff и accessibility нужны в дальнейшем, но ARIA snapshot сам по себе не является a11y audit.

## Узкие места и порядок оптимизации

Свежий локальный профиль: [JSON](../../../outputs/audit-2026-09-06/react-latency.json).

| Граница | p50 | n | Интерпретация |
|---|---:|---:|---|
| Fresh process | 3759,12 ms | 3 | Общий developer feedback для маленького сценария |
| Bootstrap residual | 3090,92 ms | 3 | Измерено как process wall minus session wall; это не чистая стоимость интерпретатора |
| Test body | 662,00 ms | 3 | Доминирование startup в коротком сценарии |
| Public controlled fill safe | 15,5 ms | 24 | Микрооптимизация здесь мало меняет общий опыт |
| Public controlled fill fast | 15,2 ms | 24 | При этом снимает часть actionability checks |
| Mutation round trip | 99,0 ms | 3 | Локальный быстрый SUT, не типичная продуктовая сеть |

Исторический [warm benchmark](../../../bench/results/warm_runner_latency.md) показывает 3446,94 → 1132,93 ms whole-run p50 на другом снимке той же машины; во время этого аудита warm comparison не повторялся. Нельзя смешивать эти серии в одно сравнительное число. В текущем запуске бюджет пройден; n=3 недостаточно для стабильного p95 или продуктового превосходства.

Приоритеты:

- Сначала точный результат, proof completeness, session/data isolation и time-to-triage QA.
- Затем acquisition browser/context, auth, setup и reuse там, где доказана одинаковая семантика свежего запуска.
- Затем memory bounds capture, большие bodies, failure storms, fsync и экспорт 10k+ results.
- Сетевые ожидания привязать к operation ID и expected state; не ускорять за счёт пропуска реального поведения.
- Native kernels/CDP rewrite отложить до профиля, показывающего CPU bottleneck. Исторический parse benchmark сам по себе не оправдывает новый runtime.

Детерминированный код не гарантирует детерминированное внешнее приложение. Перезапуски, гонки, общие fixtures и зависимости сервиса должны измеряться отдельно.

## Документация и позиционирование

Документация объёмная и продуманная, но автор нового теста вынужден разбираться в architecture/ADR раньше, чем получает первое доказательство. Одновременно несколько документов задают разные launch gates: один клиент в roadmap против трёх в launch-thesis. Требуется единый release manifest.

README честно обозначает pre-alpha и security gaps. Однако общая сравнительная таблица упрощает традиционный E2E: Playwright умеет агентный plan/generate/heal и API validation; нельзя приписывать всему классу только логи и ручное authoring. [Playwright Test Agents](https://playwright.dev/docs/test-agents), [API testing](https://playwright.dev/docs/api-testing).

Allure 3 Agent Mode уже предоставляет агенту результаты, skips/retries, evidence и findings о качестве тестирования поверх существующей команды. Следовательно, «agent-readable evidence» недостаточно для самостоятельной категории. Ценность Testence должна быть в исполнимой политике QA, expected-outcome oracles, безопасности изменений и portable proof contract, который обогащает Allure. [Allure Agent Mode](https://allurereport.org/docs/agent-mode/).

Stagehand документирует cache с экономией inference на повторе; Midscene предлагает AI automation, reports/cache и web/mobile API. Поэтому «LLM не на каждом шаге» и «когда-нибудь mobile» также недостаточные отличия. Их runtime correctness в этом аудите не сравнивалась. [Stagehand caching](https://docs.stagehand.dev/v3/best-practices/caching), [Midscene reference](https://www.midscenejs.com/reference/).

Защищаемая гипотеза: Testence сокращает количество решений и ручных разборов, которые QA должен делать на каждый принятый сценарий, сохраняя чувствительность к реальным дефектам и существующую историю TMS. Это проверяется в [пилоте](adoption.md), а не количеством stars или шириной списка функций.

## Решение о релизе

**Сейчас: NO-GO для заявленного QA-ориентированного публичного alpha.** Это не запрет открыть исследовательский репозиторий, а оценка готовности продукта, который предлагают использовать в качестве основы доверия.

Конечный объём R1 зафиксирован в [release-spec.md](release-spec.md): исправить P0, довести web verification и Allure/TestOps до приемки, доказать сценарий «один QA — три проекта», выпустить воспроизводимые demo/bench и пройти gate установки/документации. Android/iOS, собственная облачная ферма и dashboard не блокируют R1. Публикация и работа с внешними аккаунтами в ходе аудита не выполнялись.
