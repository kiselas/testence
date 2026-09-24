# Этап 4. Подготовка к публичному запуску

Версия плана: **1.2, 24 сентября 2026** (1.1: ревью плана, 1.2: ответы владельца на
Q1–Q4; см. раздел 9).
Исходная точка: `main` на `91440a9`, опубликованный пакет `0.1.0a1` (собран с `b3b1004`).
Целевые пакеты: `0.1.0a2` (все P0 и безопасность) и `0.1.0a3` (остальные P1 и P2).
Статус: **в работе** — фаза 0 выполнена; фаза 1 (L02) — PR #22; фаза 2 (L07, L03, L08, L09) реализована на ветке `stage4/phase2-testops`.

Основание — ревью проекта перед массовой рекламой (24.09.2026): 16 замечаний P0–P2.
Здесь у каждого замечания есть ID `L01`–`L17`, решение, зависимости, затрагиваемые
файлы, проверка приёмки и фаза. Прогресс ведётся в таблице раздела 8.

## 1. Решения владельца и правила

### 1.1. Решения владельца (24.09.2026)

1. Исправляются все замечания P0, P1 и P2.
2. **Звёзды, независимые ревью и пилоты** обеспечивает владелец; в план не входят.
   Публичные документы «маскируют углы»: с витрины убирается внутренний язык релизных
   гейтов и списки pending-проверок (L17).
3. **Живую проверку с настоящим Allure TestOps** владелец проводит сам в ближайшее время;
   в план она не входит (L04).
4. **Бенчмарки против конкурентов** закрепляются воспроизводимым прогоном и выносятся на
   видное место в README (L05).

### 1.2. Ответы владельца на вопросы плана (24.09.2026)

| # | Вопрос | Решение |
|---|---|---|
| Q1 | «Выпилить то, что никто не проверял с настоящим TestOps» | Живая проверка убрана из плана, оговорка «не проверено на живом тенанте» убирается с витрины. Код TestOps-интеграции остаётся и исправляется |
| Q2 | Нужен ли промежуточный релиз | Да: `0.1.0a2` после P0 и безопасности (фазы 1–3), `0.1.0a3` после остального. Реклама может стартовать на `0.1.0a2` |
| Q3 | Сессии авторинга и сопровождения против Playwright Test Agents (L05 п. 4) | Запускаем; бюджет токенов есть |
| Q4 | Cypress и SeleniumBase в бенчмарке | Входят во все три части бенчмарка: replay, корректность, авторинг |

### 1.3. Правила, которые не меняются ни одним пунктом плана

- «Маскировать углы» значит убрать с витрины внутренние статусы и негатив, но не
  утверждать того, чего не было. Нельзя писать о независимых ревью, пилотах, живой
  проверке TestOps или другой платформы, hosted receipts до того, как они реально
  появятся ([AGENTS.md](../../../AGENTS.md)).
- Предупреждение о безопасности в SECURITY.md переписывается точно после L02, а не
  удаляется, пока утечка существует.
- Цифры бенчмарков на витрине берутся только из закоммиченных сырых результатов, снятых
  скриптами `bench/` на коммите кандидата, вместе с командой, окружением и границами
  применимости.
- Ни одна цифра не улучшается ослаблением сценария или оракула; ретраи взаимодействий не
  добавляются (CONTRIBUTING, AGENTS.md).
- Публикация наружу (PyPI, GitHub Release, настройки GitHub, загрузка в TMS) — только с
  явного подтверждения владельца. Загрузки из сети для разработки (allure-pytest для
  эталонов, браузеры Firefox/WebKit, MCP SDK, npm-пакеты конкурентов, схема CTRF) —
  обычная работа.

## 2. Сводка

| ID | Приор. | Что | Зависит от | Фаза | Релиз | Объём |
|---|---|---|---|---|---|---|
| L02 | P0 | Редактирование секретов в evidence и экспортах, маски скриншотов | — | 1 | a2 | M |
| L03 | P0 | Запуск из TestOps не должен ронять прогон; параметризованные кейсы | L07 п. 1 | 2 | a2 | M |
| L07 | P1 | Совместимость с allure-pytest: история, ID и метаданные | — | 2 | a2 | M |
| L08 | P1 | Полнота карточки в Allure/TestOps | L02, L07 | 2 | a2 | M |
| L09 | P1 | Потоковая выдача для `allurectl watch`; полный рецепт | L02, L08 | 2 | a2 | M |
| L06 | P0 | Выход на «сырой» Playwright из DSL | — | 3 | a2 | S |
| L14 | P2 | Шероховатости онбординга | — | 3 | a2 | S |
| L17 | — | «Маскировка углов» в публичной документации | L02 | 3 | a2 | S |
| L04 | P0 | Живая проверка TestOps — владелец; убрать оговорку с витрины | — | 3 | a2 | S |
| L01 | P0 | Выпустить `0.1.0a2` (потом `0.1.0a3`) | фазы 1–3 | 3 и 7 | a2, a3 | S |
| L12 | P1 | hover, drag, select, вкладки, эмуляция, clock, trace/video, soft asserts, ретраи, карантин | L06, L02 | 4 | a3 | L |
| L11 | P1 | Firefox и WebKit | L12 п. 4 | 4 | a3 | L |
| L10 | P1 | Test IT, Qase, TestRail, Xray, Zephyr, ReportPortal; CTRF; JUnit | L07 п. 3, L08 | 5 | a3 | L |
| L13 | P1 | MCP-сервер | L02, L06 | 5 | a3 | L |
| L05 | P0 | Бенчмарки против конкурентов: закрепить и вынести в README | L12, L11 | 6 | a3 | L |
| L15 | P2 | Порог входа: путь без PlanSpec, глоссарий | L07 п. 3 | 6 | a3 | M |
| L16 | P2 | Только Python, один мейнтейнер, Discussions | — | 6 | a3 | S (владелец) |

L05 стоит в `a3`, потому что цифры снимаются на финальном раннере. На время рекламы
`a2` README ссылается на действующий бенчмарк replay, перезапущенный на коммите `a2` с
увеличенным числом повторов (L05 п. 2 — минимальная часть, фаза 3).

Объём: S — до дня, M — 2–4 дня, L — неделя и больше. Грубая оценка: фазы 0–3 (до
`0.1.0a2`) — 2–2,5 недели; фазы 4–7 — ещё 5–6 недель (L05 с пятью плечами и
агентскими сессиями — около двух недель из них).

## 3. Порядок работ

```text
Фаза 0  базовый снимок: ветка, полный зелёный набор проверок, SHA, время прогона
Фаза 1  L02 безопасность evidence                       ← до любых изменений экспорта
Фаза 2  L07 → L03 → L08 → L09 TestOps/Allure            ← именование раньше test plan
Фаза 3  L06, L14, L17, L04, мини-L05 → релиз 0.1.0a2    ← реклама может стартовать
Фаза 4  L12 → L11 раннер                                ← эмуляция до браузерной матрицы
Фаза 5  L10 платформы и CTRF/JUnit; L13 MCP             ← независимы, можно параллельно
Фаза 6  L05 бенчмарки полностью; L15, L16
Фаза 7  релиз 0.1.0a3
```

Каждая фаза — один или несколько PR в `main`. Внутри PR действует порядок из
[пособия этапа 3](../03-r1-release/implementation-guide.md): сначала регрессионный тест,
который падает по нужной причине, затем исправление в нижнем общем слое. Фаза 0
записывает в таблицу прогресса SHA, результат `pytest -q` и время полного прогона —
это база для оценки роста CI.

Обязательные проверки на каждой границе фазы (CONTRIBUTING):

```bash
uv run ruff format --check src tests bench scripts examples
uv run ruff check src tests bench scripts examples
uv run mypy src scripts
uv run pytest -q
uv run pytest examples -q --testence-headless
```

На машине владельца Chromium из Playwright не запускается, поэтому браузерные прогоны
идут с `TESTENCE_BROWSER_CHANNEL=msedge`. CI остаётся на штатном Chromium.

Новые архитектурные решения оформляются двуязычными ADR (`docs/en/adr`, `docs/ru/adr`):

| ADR | Решение | Уточняет |
|---|---|---|
| ADR-0024 | Политика редактирования evidence, маски скриншотов | ADR-0003, ADR-0023 |
| ADR-0025 | Отображаемые значения параметров в ledger | ADR-0019 |
| ADR-0026 | Потоковый Allure-экспорт (tripwire ADR-0013) | ADR-0013 |
| ADR-0027 | Native escape hatch | ADR-0001 |
| ADR-0028 | Несколько браузеров | ADR-0001, ADR-0022 |
| ADR-0029 | MCP-сервер | ADR-0015 |
| ADR-0030 | JUnit-экспортер | ADR-0013 |

Номера идут в порядке фаз, чтобы публичный индекс ADR не имел пропусков.

Каждое изменение пользовательских документов делается в `docs/en` и `docs/ru`
одновременно; `tests/test_documentation.py` обновляется вместе с документами.

## 4. Работы фаз 1–3 (релиз 0.1.0a2)

### L02 (P0). Редактирование секретов в evidence и экспортах

**Проблема (воспроизведено).** Маскировка в
[sanitize.py:13](../../../src/testence/evidence/sanitize.py) срабатывает только при
точном совпадении нормализованного ключа. В открытом виде остаются `authToken`,
`sessionToken`, `apiToken`, `jwt`, `csrfToken`, `pwd`, OAuth-`code` и `session` в URL,
email, телефон, номер карты.

Масштаб (уточнено при начале реализации): тела запросов и ответов и скриншоты по
умолчанию выключены и включаются через `capture_policy`
([configuration.md](../../en/configuration.md), раздел «Evidence capture policy»). Если
тела включены, сохраняются ответы на все не-GET запросы, включая логин
([playwright_cdp.py:387](../../../src/testence/engine/playwright_cdp.py)). Без этой
настройки наружу по умолчанию уходят URL с параметрами, текст консоли, ARIA-снимок и
сообщения об ошибках. Скриншоты не маскируются, у
`expect_screenshot` масок нет вовсе
([visual.py:121](../../../src/testence/visual.py)). Allure-экспорт копирует
`network.jsonl`, `aria.txt` и `screenshot.png` во вложения, а `allurectl` загружает их в
TestOps. По значению маскируются только переменные логина и пароля
([pytest_plugin.py:425](../../../src/testence/pytest_plugin.py)).

**Решение.**

1. Сопоставление ключей по токенам, а не по точному совпадению: ключ разбивается по
   camelCase, `_`, `-`, `.`. Он чувствителен, если содержит токен из набора `password`,
   `passwd`, `pwd`, `pass`, `secret`, `token`, `auth`, `authorization`, `cookie`,
   `session`, `sid`, `jwt`, `csrf`, `xsrf`, `otp`, `pin`, `credential(s)`,
   `signature`, `sig`, `bearer` или пару `api|access|private|secret` + `key`.
   Разбиение на токены защищает от ложных срабатываний вроде `passage`, `author`,
   `keyboard`, `pinned`.
2. Маскирование по значению независимо от ключа: JWT (`eyJ…​.…​.…`), известные префиксы
   токенов (`ghp_`, `github_pat_`, `glpat-`, `xox[abp]-`, `sk-`, `AKIA`), номера карт с
   проверкой Луна.
3. Расширенный список параметров URL: `code`, `session`, `sid`, `sig`, `signature`,
   `key`, `apikey`, `access_key`, `x-amz-signature`, `x-amz-credential` и все имена из
   п. 1.
4. Конфигурация `evidence.redact` в `testence.json`: `keys` (доп. токены), `allow_keys`
   (исключения на случай избыточного маскирования, например `session_status`), `env`
   (имена переменных окружения, значения которых маскируются дополнительно к логину и
   паролю), `url_params`, `pii: ["email", "phone"]`. Email и телефон маскируются только
   при явном включении: тесты часто проверяют email пользователя.
5. Маски скриншотов: `evidence.mask` — список целей (`role`/`test_id`/`css`),
   передаётся в Playwright `screenshot(mask=[...])` для pack-скриншота и
   `expect_screenshot`. Непустой список масок записывается в профиль визуального
   эталона: смена масок делает эталон несовместимым (inconclusive), а не даёт
   пиксельный вердикт; эталоны без масок остаются валидными (ADR-0023).
6. Повторное редактирование при экспорте: экспортеры прогоняют текстовые вложения и поля
   через ту же политику. Это закрывает ledger и pack, записанные `0.1.0a1` до
   исправления.
7. Политика вложений при экспорте: `testence export --attachments full|minimal|none`
   (по умолчанию `full` — уже отредактированные файлы; `minimal` исключает
   `network.jsonl`, `aria.txt` и скриншот). Артефакты, которые нельзя отредактировать
   (Playwright trace и видео из L12), не экспортируются без явного
   `--include-unredacted`, а в `manifest.json` помечаются `redaction: "none"`.
8. Канареечный тест: ~40 форм секретов (ключи, значения, URL, JSON внутри строки, JSONL,
   сообщения ошибок и ассертов, параметры тестов). Прогнать через ledger, pack, HTML-отчёт,
   verdict/heal и все экспортеры и проверить побайтным поиском по run-директории и
   каталогам экспорта, что ни одно значение не встречается.

**Файлы.** `src/testence/evidence/sanitize.py`, `src/testence/config.py`,
`src/testence/pytest_plugin.py`, `src/testence/engine/protocol.py`,
`src/testence/engine/playwright_cdp.py`, `src/testence/triage/pack.py`,
`src/testence/visual.py`, `src/testence/dsl/steps.py`, `src/testence/export/*.py`,
`src/testence/cli.py`, `tests/test_redaction.py`, `docs/{en,ru}/configuration.md`,
`docs/{en,ru}/evidence-schema.md`, ADR-0024.

**Приёмка.** Канареечный тест зелёный. Отрицательные контроли остаются нетронутыми:
`passage`, `author`, `keyboard`, `pinned`, собственные `sha256:…`-поля Testence,
`allow_keys`. Скриншот с маской сравнивается с эталоном: пиксели внутри маски закрашены.
Ledger `0.1.0a1` с открытым токеном после `testence export` токена не содержит.

### L07 (P1). Совместимость с allure-pytest при миграции

Идёт раньше L03: от формы `fullName` зависит, какие селекторы присылает TestOps.

**Проблема.** У Testence другие `fullName` и `testCaseId`, чем у allure-pytest. При
переводе существующего набора в TestOps появятся дубли кейсов, пропадут история и связи
ручных кейсов с автотестами. Декораторы `@allure.*` игнорируются. `allure_id` задаётся
только через `@pytest.mark.testence(plan=…)`, а для этого нужен PlanSpec-файл
([pytest_plugin.py:206](../../../src/testence/pytest_plugin.py)). Утверждение
«migration touches the test command, never the pipeline»
([allure.py:7](../../../src/testence/export/allure.py)) про историю неверно.

**Решение.**

1. Режим именования `export.allure.naming: allure-pytest|nodeid`, по умолчанию
   `allure-pytest`. `fullName` = `package.module[.Class]#func` без параметров, а
   `testCaseId` и `historyId` считаются по формулам allure-pytest (формулы и
   поддерживаемую версию сверить с его исходниками). `nodeid` — прежнее поведение
   `0.1.0a1` для тех, кто уже загружал результаты.
2. Явная идентичность Testence сильнее эвристики: если у теста задан `case_id` из PlanSpec
   (он переживает переименование, ADR-0019), `testCaseId` строится от
   `(project, case_id)`, как сейчас. Формула allure-pytest применяется к тестам без
   явного `case_id`. Это правило записывается в документацию миграции.
3. Чтение метаданных allure-pytest без импорта `allure`: метки `allure_label`
   (`as_id`/`ALLURE_ID`, `feature`, `story`, `epic`, `severity`, `owner`, `tag`,
   произвольные), `allure_link`, атрибуты функции для title и description. Точные имена
   меток и атрибутов сверить с исходниками поддерживаемой версии allure-pytest.
4. `@pytest.mark.testence(...)` без `plan` для чистых метаданных: `allure_id`, `title`,
   `description`, `severity`, `labels={...}`, `links=[...]`, `tms={...}` (L10). С `plan`
   действуют прежние проверки claims.
5. Одинаковый `allure_id` у двух разных (не параметризованных вариантов одного) тестов —
   предупреждение при сборе тестов.
6. Если одновременно активен allure-pytest с `--alluredir`, выдаётся предупреждение о
   дублях результатов.

**Файлы.** `src/testence/pytest_plugin.py`, `src/testence/export/allure.py`,
`src/testence/export/_model.py`, `src/testence/identity.py`, `tests/test_export.py`,
`tests/goldens/allure/`, `docs/{en,ru}/reporting.md` (раздел «Миграция с
allure-pytest»).

**Приёмка.** Golden-сравнение: один набор с метками `@allure.*`, прогнанный настоящим
allure-pytest зафиксированной версии и Testence, даёт одинаковые `fullName`,
`testCaseId`, `historyId`, `ALLURE_ID`, `feature/story/severity` и `name`. Тест с
PlanSpec `case_id` сохраняет `testCaseId` после переименования функции.

### L03 (P0). Запуск из TestOps не должен ронять весь прогон

**Проблема (воспроизведено).** В [testplan.py:92](../../../src/testence/testplan.py):

- если в плане есть кейс, удалённый или переименованный в коде, падает весь прогон
  (`did not resolve`), и в TestOps не приходит ни одного результата;
- параметризованный тест с `allure_id` при любом перезапуске из TestOps даёт
  `ambiguous`;
- `fullName` сейчас содержит параметры
  ([allure.py:96](../../../src/testence/export/allure.py)), поэтому перезапуск
  параметризованного кейса выполняет один вариант;
- неизвестные поля в плане отвергаются, так что любое расширение формата со стороны
  TestOps сломает запуски.

**Решение.**

1. Новая опция `--testence-testplan-unresolved=warn|fail`, по умолчанию `warn`.
   Неразрешённые записи не останавливают прогон: они печатаются в итоге pytest,
   пишутся событием `testplan.unresolved` в ledger и попадают в экспорт
   (`environment.properties`, CTRF `extra`) и в `ci evaluate` (счётчик и режим
   `--testplan-unresolved=fail` для строгих пайплайнов). `fail` сохраняет прежнее
   строгое поведение.
2. Если план непустой, но ни одна запись не разрешилась, прогон падает даже в режиме
   `warn`: иначе опечатка в плане превратилась бы в зелёный прогон нуля тестов.
3. Совпадение по `id` выбирает **все** варианты с этим `allure_id`, без ошибки.
4. Совпадение по `selector` принимает три формы: `fullName` в стиле allure-pytest
   (`package.module[.Class]#func` — все варианты), pytest nodeid (ровно один вариант) и
   `testence://project/case/variant`.
5. Перекрытие записей даёт дедупликацию, а не ошибку.
6. Неизвестные поля плана и его записей игнорируются с предупреждением. Проверка версии
   `1.0` остаётся.
7. Поведение для пустого плана (`--testence-empty-testplan`) не меняется.

**Файлы.** `src/testence/testplan.py`, `src/testence/pytest_plugin.py`,
`src/testence/ci.py`, `src/testence/export/_model.py`, `src/testence/export/allure.py`,
`src/testence/export/ctrf.py`, `tests/test_testplan.py`, `tests/test_ci.py`,
`docs/{en,ru}/reporting.md`, `docs/{en,ru}/evidence-schema.md`.

**Приёмка.** Сценарии из ревью становятся тестами: устаревшая запись → прогон выбранных,
предупреждение и событие в ledger; все записи неразрешены → ошибка; параметризованный
тест + `allure_id` → выполнены все варианты; селектор в стиле allure-pytest → все
варианты; nodeid → один вариант; `--testence-testplan-unresolved=fail` → прежний
`UsageError`. Существующие тесты, закрепляющие строгое поведение, переносятся под режим
`fail`, их смысл сохраняется.

### L08 (P1). Полнота карточки в Allure/TestOps

**Проблема.** Все маркеры pytest становятся тегами: на локальных прогонах собственного
набора `parametrize` висит на 1612 результатах из 6461. Параметры показываются как
`sha256:…`, есть служебный параметр `variant_id`. В `trace` — одна строка сообщения
([allure.py:113](../../../src/testence/export/allure.py)). Любое исключение в теле теста
получает `failed`. Имя кейса — имя функции, PlanSpec не используется. Нет иерархии
сьютов. Вложения есть только у упавших тестов.

**Решение.**

1. Теги: пропускать встроенные и служебные маркеры (`parametrize`, `usefixtures`,
   `filterwarnings`, `skip`, `skipif`, `xfail`, `testence`, `testence_quarantine`,
   `allure_*`, `timeout`, `asyncio`). Пользовательские маркеры остаются дословными.
2. Параметры: в ledger добавить поле `parameter_display` — значения скаляров, прошедшие
   редактирование L02 и ограниченные по длине; для прочих типов — id из `callspec`.
   Параметр с чувствительным по L02 именем получает `mode: "masked"`. `variant_id`
   переезжает в label. Digest-поля идентичности не меняются. Это отступление от принципа
   «только digest» ADR-0019 оформляется ADR-0025 и отключается
   `export.parameters: digest`.
3. Ошибка: в `test.end` добавить `error_trace` (полный longrepr, ограниченный и
   отредактированный) и `error_kind`. Статус исполнения в ledger и логика `ci evaluate`
   не меняются; меняется только отображение в Allure:

   | `error_kind` | Источник | Allure |
   |---|---|---|
   | `assertion` | `AssertionError`, падения `expect_*` | `failed` |
   | `oracle` | `OracleFailed`, расхождение expected-state | `failed` |
   | `infrastructure` | таймаут поиска цели, ошибка браузера или сети, сбой старта движка | `broken` |
   | `test_code` | прочие исключения в коде теста | `broken` |

4. Имя и описание: для теста, связанного с PlanSpec, `name` = заголовок сценария,
   `description` = claims и ссылка на план. Без плана — title и description из L07, иначе
   первая строка docstring.
5. Иерархия как у allure-pytest: `parentSuite`, `suite`, `subSuite`, `package`,
   `testClass`, `testMethod`, `host`, `thread`, `language`, `framework`.
6. Вложения: `evidence.screenshots: on-failure|always`. Скриншот падения прикрепляется и
   к упавшему шагу. Trace и видео — по L02 п. 7 и L12.
7. `categories.json` для классов ошибок из таблицы п. 3.

**Файлы.** `src/testence/export/allure.py`, `src/testence/export/_model.py`,
`src/testence/pytest_plugin.py`, `src/testence/identity.py`,
`docs/{en,ru}/evidence-schema.md`, `tests/test_export.py`, goldens, ADR-0025.

**Приёмка.** Обновлённые goldens. Отдельные тесты: служебные маркеры не попадают в теги,
параметр `password` маскируется, таймаут поиска цели даёт `broken`, а `OracleFailed` —
`failed`. Ledger `0.1.0a1` экспортируется без падений.

### L09 (P1). Потоковая выдача и полный рецепт TestOps

**Проблема.** Результаты появляются только после прогона, `allurectl watch` бесполезен.
Если CI убьёт job, в TestOps не придёт ничего. В рецепте нет `allurectl job-run plan`, без
которого запуск из TestOps не получит план.

**Решение.** Срабатывает tripwire ADR-0013. Опция `--testence-allure-results DIR` (или
`TESTENCE_ALLURE_RESULTS`): результат теста атомарно (временный файл + rename) пишется
на `test.end`, контейнеры фикстур — после teardown, `environment.properties` и
`categories.json` — в конце сессии. Действуют политики L02 (редактирование, вложения).
При xdist каждый воркер пишет свои файлы (UUID детерминированы). `testence export`
остаётся для пост-обработки. Рецепт в `reporting.md` сохраняет код завершения pytest
(этого требует тест документации):

```bash
export TESTENCE_RUN_ID="r-${CI_PIPELINE_ID}-${CI_JOB_ID}"
export ALLURE_TESTPLAN_PATH="$PWD/testplan.json"
RUN="runs/${TESTENCE_RUN_ID}"
if [ -n "${ALLURE_JOB_RUN_ID:-}" ]; then
  allurectl job-run plan --output-file "$ALLURE_TESTPLAN_PATH"
else
  unset ALLURE_TESTPLAN_PATH
fi
set +e
allurectl watch --results "$RUN/allure-results" -- \
  pytest tests_e2e -q --testence-allure-results "$RUN/allure-results"
TEST_EXIT=$?
set -e
exit "$TEST_EXIT"
```

При реализации сверить с документацией allurectl имя флага каталога результатов у
`watch` и то, что `watch` возвращает код завершения вложенной команды.

**Файлы.** `src/testence/pytest_plugin.py`, `src/testence/export/allure.py` (вынести
построение одного результата), `tests/test_export.py`,
`tests/test_parallel_evidence.py`, `tests/test_documentation.py`, ADR-0026,
`docs/{en,ru}/reporting.md`.

**Приёмка.** Во время прогона из 3 тестов файлы появляются по одному. Прогон, убитый
после второго теста, оставляет два валидных результата. Результаты потокового и
пост-экспорта побайтно совпадают. Под `-n 2` дублей нет.

### L06 (P0). Выход на «сырой» Playwright

**Проблема.** Страница хранится в приватном `_page`, а ADR-0001 не выпускает типы
Playwright наружу. Любой пробел DSL — тупик без форка.

**Решение.** Единственный явно помеченный шов:
`with ex.native("drag card to Done") as page:`. Он отдаёт Playwright `Page` и записывает
шаг с intent. Исключение внутри блока становится упавшим шагом и попадает в pack.
Healing для таких шагов не предлагается: fingerprint цели внутри блока неизвестен. В
ledger пишется `native.used`, чтобы triage и assurance знали, что действия внутри не
записаны пошагово. Движок без нативного Playwright поднимает `UnsupportedCapability`.
Новая capability — `browser.native`. Работает и в warm/attached режиме.

**Файлы.** `src/testence/dsl/steps.py`, `src/testence/engine/protocol.py`,
`src/testence/engine/playwright_cdp.py`, `src/testence/engine/capabilities.py`,
`src/testence/evidence/events.py`, ADR-0027, `docs/{en,ru}/engine-capabilities.md`,
навык `testence-author` (правило: сначала DSL, native — с обоснованием в intent).

**Приёмка.** Тест с `ex.native` выполняет `page.mouse` и `page.keyboard`. Падение внутри
блока даёт pack со скриншотом и шагом `failed`. Движок-заглушка без capability даёт
понятную ошибку до выполнения.

### L14 (P2). Онбординг

1. `testence run` без аргументов остаётся зелёным, но в конце печатает следующий шаг —
   `testence run -- .testence/examples/test_demo_failure.py`, чтобы увидеть, как
   Testence ловит ложно-зелёный тест, — и путь к pack. В quick start README — такой же
   шаг ([cli.py:488](../../../src/testence/cli.py)).
2. Классифицировать ошибку запуска браузера (нет исполняемого файла / сбой запуска
   процесса / политика ОС) в `doctor`
   ([application.py:402](../../../src/testence/application.py)) и в `run`. При сбое
   запуска предлагать `TESTENCE_BROWSER_CHANNEL=msedge|chrome`, а не переустановку. В
   `run` ошибка старта движка оборачивается ссылкой на `testence doctor`.
3. `testence inspect` печатает текст вместо Python-словаря (`cli.py:512`).
4. Примеры вызова в `--help` подкоманд (`epilog`); `run --help` объясняет, что
   позиционные аргументы передаются в pytest.
5. `playwright>=1.49,<2`, обновление `support.json` и еженедельный CI-прогон на
   последней версии Playwright.

**Приёмка.** Тесты `tests/test_application.py` и `tests/test_documentation.py`. Повтор
онбординга с чистого окружения (как в ревью) проходит без замечаний.

### L17. «Маскировка углов» в публичной документации

Витрина — README, `docs/{en,ru}/README.md`, пользовательские руководства, `SECURITY.md`,
`SUPPORT.md`.

1. Бейдж `alpha candidate` → `alpha`. Раздел «Project status» — три строки: alpha, API
   может меняться, ссылки на roadmap и changelog.
2. Убрать с витрины абзац про hosted receipts под заголовком, фразы про pending
   independent client/public release acceptance, «engineering candidate», «does not
   claim independent model/client acceptance». Детали релизной инженерии остаются в
   `docs/stages/` и `docs/audits/`.
3. Внутренние аналитические документы (`project-audit`, `open-source-readiness`,
   `launch-thesis`, `product-positioning`, `competitive-landscape`) убрать из
   пользовательского индекса `docs/{en,ru}/README.md` в отдельный раздел «Для
   мейнтейнеров» или перенести в `docs/internal/`. Все внутренние ссылки обновляются:
   `test_current_documentation_has_no_broken_local_links` должен остаться зелёным.
4. SECURITY.md после L02: точное описание того, что маскируется по умолчанию и как
   настроить маски и политику вложений; рекомендация проверять pack перед передачей за
   пределы команды. Процесс сообщения об уязвимостях не меняется.
5. Правила раздела 1.3 действуют: никаких утверждений о ревью, пилотах и живых проверках
   до их появления.

### L04 (P0). Живая проверка TestOps — у владельца

Проверку проводит владелец. В рамках этапа из `docs/{en,ru}/reporting.md` убирается
фраза о том, что полный цикл на реальном тенанте остаётся внешним гейтом.
`infra/testops-sandbox` остаётся инструментом владельца. Чтобы проверка владельца
покрыла исправленный код, она проводится на кандидате `0.1.0a2` (после фазы 2) по
чек-листу из [readme песочницы](../../../infra/testops-sandbox/README.md), дополненному
сценариями L03 (устаревшая запись, параметризованный кейс) и L09 (`allurectl watch`).
Обезличенная квитанция сохраняется в `release/evidence/`.

### L01 (P0). Релизы 0.1.0a2 и 0.1.0a3

**Проблема.** На PyPI только `0.1.0a1` с `b3b1004`. После неё в `main` вошли 7 PR с
исправлениями (#15–#21), включая «Stabilize the published alpha for first external
users» и macOS. GitHub Release для тега не создан.

**Решение.**

- `0.1.0a2` в конце фазы 3: версия, `CHANGELOG` (en/ru) с разделом несовместимых
  изменений (раздел 5) и флагами прежнего поведения, новый манифест кандидата со ссылкой
  на macOS-квитанцию — macOS становится релизной платформой именно с этим кандидатом,
  когда матрица пройдёт на его коммите. Полная CI-матрица на коммите кандидата.
- `0.1.0a3` в фазе 7 по той же процедуре.
- Публикация через `publish.yml`, решение владельца (`owner-go`) и GitHub Release —
  **только с явного подтверждения владельца**.

**Файлы.** `pyproject.toml`, `release/`, `support.json`, `docs/{en,ru}/CHANGELOG.md`,
`tests/test_documentation.py` (согласованность версий).

**Приёмка.** Манифест кандидата проходит валидацию. Установленный wheel проходит
`tests/test_client_simulation.py` и `scripts/installed_wheel_smoke.py` на Windows, Linux
и macOS.

## 5. Работы фаз 4–6 (релиз 0.1.0a3)

### L12 (P1). Недостающие возможности раннера

**Проблема.** Нет hover и drag-and-drop, выбора option по видимому тексту, DSL для
вкладок, эмуляции устройств, геолокации, locale/timezone, permissions, clock,
Playwright trace и видео, soft-ассертов, встроенных ретраев и карантина.

**Решение (каждый пункт — отдельный PR с тестом на `tests/mock_app.py`):**

1. `hover(target)`, `drag(source, dest)` в Engine и DSL, capability `browser.pointer`.
2. `select(target, value=None, *, label=None, index=None, values=None)` с multi-select.
3. `ex.switch_page(index | url_contains=…)`, `ex.close_page()`, учёт открытых страниц в
   движке (сейчас `switch_page` есть только в Engine).
4. Эмуляция в `Settings`: `device` (дескриптор Playwright), `locale`, `timezone_id`,
   `geolocation`, `permissions`, `color_scheme`, `user_agent`. Применяется при создании
   контекста; в attached-режиме — ошибка. Capability `browser.emulation`.
5. `ex.clock.install(time)`, `fast_forward`, `pause_at` через `page.clock`
   (Playwright ≥ 1.45 укладывается в минимальную 1.49).
6. `trace: off|on|retain-on-failure`, `video: off|retain-on-failure`, по умолчанию
   `off`. Сохраняются в pack с пометкой `redaction: "none"` (L02 п. 7).
7. `with ex.soft("checkout summary"):` собирает падения `expect_*` внутри блока, пишет
   каждое упавшим шагом и в конце поднимает сводное `SoftAssertionsFailed`.
8. Ретраи: официальная поддержка `pytest-rerunfailures` (extra `retry`). Нумерация
   попыток в плагине уже есть ([pytest_plugin.py:571](../../../src/testence/pytest_plugin.py));
   проверить, что каждый повтор получает новый `attempt_id` и отдельный pack. В Allure
   повторы идут отдельными результатами одной истории, в CTRF — `retries`/`flaky`.
   `ci evaluate --flaky=fail|warn` показывает прохождение после повтора как flaky, а не
   как чистый зелёный. Повтор взаимодействий внутри теста не добавляется.
9. Карантин: `@pytest.mark.testence_quarantine(reason=…, until="YYYY-MM-DD")`. Тест
   выполняется и записывается, но не валит сборку. `ci evaluate` показывает число тестов
   в карантине. Просроченный `until` ломает сбор тестов с понятным сообщением. В экспорт
   идёт label `quarantine`.

**Файлы.** `src/testence/engine/{protocol,playwright_cdp,capabilities}.py`,
`src/testence/dsl/steps.py`, `src/testence/config.py`, `src/testence/pytest_plugin.py`,
`src/testence/ci.py`, `src/testence/export/*.py`, `pyproject.toml` (extra `retry`),
`tests/`, навык `testence-author`, `docs/{en,ru}/engine-capabilities.md`,
`docs/{en,ru}/testing-a-feature.md`.

**Приёмка.** Для каждого пункта: позитивный тест, отрицательный тест (неподдерживаемый
режим или браузер даёт понятную ошибку) и запись шага с intent в ledger. Бенчмарк
задержек React (`bench/react_latency.py`) укладывается в бюджет.

### L11 (P1). Firefox и WebKit

**Проблема.** Движок жёстко вызывает `playwright.chromium.*`
([playwright_cdp.py:201-230](../../../src/testence/engine/playwright_cdp.py)).

**Решение.** Настройка `browser: chromium|firefox|webkit` (`TESTENCE_BROWSER`,
`--testence-browser`). `browser_channel` и `--remote-debugging-port` — только для
Chromium. Attached, persistent и warm режимы, а также `dev_browser` работают только в
Chromium: при другом браузере — понятная ошибка до запуска; capability-документ свой для
каждого браузера. `doctor` проверяет выбранный браузер. В fingerprint прогона и в Allure
появляется `browser` с версией. Один браузер на прогон, матрица задаётся в CI; несколько
браузеров в одном прогоне в этап не входят.

**Файлы.** `src/testence/config.py`, `src/testence/engine/playwright_cdp.py`,
`src/testence/engine/capabilities.py`, `src/testence/pytest_plugin.py`,
`src/testence/application.py` (doctor), `.github/workflows/ci.yml` (установка
браузеров; Linux: firefox и webkit на examples и браузерном поднаборе; macOS: webkit),
`support.json` и его тест в `tests/test_documentation.py`, ADR-0028,
`docs/{en,ru}/configuration.md`, `docs/{en,ru}/engine-capabilities.md`.

**Приёмка.** `examples/` и браузерный поднабор зелёные на трёх браузерах в CI. Evidence
pack (aria, network, console, скриншот) собирается во всех трёх. Рост времени CI
зафиксирован относительно базы фазы 0.

### L10 (P1). Другие платформы, CTRF и JUnit

**Проблема.** Экспортеров два: Allure и CTRF. TestRail, Xray и Zephyr получают только
JUnit от pytest, без ID кейсов и шагов. Для ReportPortal нет ничего. CTRF устарел:
`specVersion "0.0.0"` ([ctrf.py:25](../../../src/testence/export/ctrf.py)), а шаги,
вложения, ретраи и flaky уходят в `extra`, хотя в схеме это штатные поля.

**Решение.**

1. **CTRF:** актуальная `specVersion` и штатные поля `steps`, `attachments`, `retries`,
   `flaky`, `trace`, `browser`, `parameters`, `labels`, `suite`. Проверка по
   зафиксированной копии схемы в `tests/` (лицензию схемы уточнить и указать).
2. **JUnit-экспортер** `--to junit` (ADR-0030, уточняет ADR-0013). Он нужен, потому что
   `--junitxml` не несёт шагов, ID и вложений: `<properties>` с идентичностью Testence,
   `allure_id` и TMS-ID, шаги в `system-out`, вложения в формате `[[ATTACHMENT|path]]`,
   `failure` с message, type и trace. Фраза «JUnit deliberately not an exporter» в
   `reporting.md` заменяется объяснением разницы.
3. **TMS-ID в тестах:** `@pytest.mark.testence(tms={"testrail": "C123", "xray": "PROJ-12",
   "zephyr": "PROJ-T12", "testit": "…", "qase": 12})` → JUnit properties, Allure
   labels/links, CTRF labels. Имена свойств для каждого инструмента сверить с его
   документацией.
4. **Рецепты (en/ru):** Test IT (`testit-importer-allure` / `testit-cli`), Qase
   (`qasectl testops result upload --format allure`), TestRail (`trcli parse_junit`),
   Xray (импорт JUnit), Zephyr Scale (JUnit), ReportPortal (импорт JUnit), отчёты тестов
   GitLab и GitHub.
5. **Публикация.** По той же логике, что для TestOps (Q1), платформа попадает в публичную
   документацию только после живой проверки владельцем. До этого рецепт и golden лежат в
   `docs/internal/integrations/` и на витрине не упоминаются.

**Файлы.** `src/testence/export/ctrf.py`, `src/testence/export/junit.py` (новый),
`src/testence/export/__init__.py`, `src/testence/pytest_plugin.py`,
`tests/test_export.py`, `tests/goldens/{ctrf,junit}/`, `docs/{en,ru}/reporting.md`,
`docs/internal/integrations/`, ADR-0030.

**Приёмка.** CTRF проходит валидацию по схеме, JUnit — по XSD Jenkins (или GitLab). Для
каждого рецепта есть golden, воспроизводящий команду рецепта до шага загрузки.

### L13 (P1). MCP-сервер

**Проблема.** MCP-сервера нет ([agent-workflow.md:7](../../en/agent-workflow.md)). UI агент
исследует своим браузерным инструментом, и локаторы исследования и прогона расходятся.

**Решение.** Extra `testence[mcp]` с официальным Python SDK MCP (лицензию и транзитивные
зависимости проверить на соответствие ADR-0007). Команда `testence mcp serve` (stdio).
Инструменты — тонкие обёртки над `application.py`: `doctor`, `plan_validate`,
`plan_prepare`, `run`, `inspect_run`, `read_pack` (ограниченный), `export`,
`verdict_validate`, `repair_validate`. Инструменты исследования поверх attached
dev-браузера: `browser_open`, `browser_snapshot` (aria + кандидаты с готовыми `Target`
Testence), `browser_click`, `browser_fill`, `browser_screenshot` (с масками L02).

Главное отличие от Playwright MCP: исследование идёт через тот же движок и то же
разрешение `Target`, что и прогон, поэтому найденный локатор — ровно тот, что сработает в
тесте. `testence agent install` регистрирует сервер для Claude Code, Codex и OpenCode с
той же защитой от конфликтов, что у навыков.

**Безопасность.** `run` исполняет код тестов проекта — это доверенный код (граница из
этапа 3), и документация говорит об этом прямо. Пути в аргументах ограничены корнем
проекта и `runs/`. `browser_open` по умолчанию разрешает только origin из `base_url`
профиля, остальное — через явный список в конфигурации. Ответы инструментов проходят
редактирование L02. Сервер не хранит учётные данные и не отдаёт `env_values`.

**Файлы.** `src/testence/mcp/` (новый), `src/testence/cli.py`,
`src/testence/agent/install.py`, навыки (упоминание инструментов), `pyproject.toml`,
`bench/client_simulation/`, ADR-0029, `docs/{en,ru}/agent-workflow.md`,
`docs/{en,ru}/agent-skills.md`.

**Приёмка.** Внутрипроцессный MCP-клиент проходит сценарий «открыть → снимок → найти
цель → написать тест → прогнать → прочитать pack». Локатор из `browser_snapshot`
используется в тесте без правок. Отрицательные тесты: путь вне проекта, origin вне
списка, секрет в ответе — отклоняются или маскируются.

### L05 (P0). Бенчмарки против конкурентов

**Проблема.** Сейчас есть одно сравнение: 7 повторов, один статический SUT, только
Playwright Test (+27,5%, [competitive.md](../../en/benchmark/competitive.md)). Корпус
дефектов — 17 позиций. В README бенчмарков против конкурентов на видном месте нет.

**Решение.**

1. **Плечи.** Пять: Testence, Playwright Test (TS), pytest-playwright (Python — самое
   честное сравнение на одном языке), Cypress (JS, штатный раннер `cypress run`,
   Electron или Chrome — фиксируется в методике), SeleniumBase (Python, pytest-режим,
   Chrome). Версии всех плеч фиксируются в `bench/node/package-lock.json` и
   `bench/competitive/requirements.lock`; Chromium-плечи используют одну ревизию
   браузера, где инструмент это позволяет, а расхождение записывается в методику.
2. **Replay.** SUT: статический (есть), React SUT из `bench/sut`, один OSS-таргет
   (Tabler). Сценарий один и тот же для всех плеч: шесть шагов с intent, те же
   ожидания. Не меньше 30 повторов, случайный порядок плеч, прогрев отбрасывается,
   один воркер, без ретраев, trace и видео. Отчёт: медиана, p95, 95% bootstrap-интервал.
   Два окружения: GitHub `ubuntu-latest` (закреплённое) и локальный Windows. Минимальная
   часть для `a2` (фаза 3): текущий сценарий, 30 повторов, пять плеч, коммит `a2`.
3. **Корректность — главное отличие Testence.** Посеянные дефекты «UI говорит успех, а
   данные не сохранились»: 500 на POST за оптимистичным UI, устаревший список, чужая
   сущность, частичное сохранение. Чтобы сравнение не подгонялось под Testence, у
   каждого конкурента два варианта тестов:
   - **идиоматичный** — получен штатным генератором инструмента по тому же тексту
     требования и принят без ручного ослабления: Playwright codegen или Playwright Test
     Agents для обоих Playwright-плеч, Cypress Studio для Cypress, режим записи
     SeleniumBase для SeleniumBase. Где генератор не справился, тест пишет агентская
     сессия из п. 4 по тому же требованию, и это отмечается в методике;
   - **усиленный** — с явной проверкой через API (`request` в Playwright, `cy.request`
     в Cypress, `requests` в SeleniumBase), написанный по документации инструмента.

   Метрики: доля пойманных дефектов, ложно-зелёных, ложно-красных, а для усиленного
   варианта ещё объём дополнительного кода. Все тесты конкурентов и способ их получения
   публикуются.
4. **Авторинг и сопровождение (Q3 — запускаем).** Плечи:
   - Testence с пакетом навыков;
   - Playwright Test Agents (planner/generator/healer, `npx playwright init-agents`);
   - pytest-playwright, Cypress и SeleniumBase — тот же агент без специальных
     инструментов, только документация инструмента в репозитории SUT.

   Одинаковое требование, стартовый репозиторий и модель: Claude Sonnet 5 в
   изолированных сессиях, у каждой свой worktree и никакого контекста из других плеч.
   Не меньше 3 сессий на плечо: 15 сессий авторинга и 15 сессий сопровождения. Метрики
   авторинга: время до первого зелёного и до принятого diff, число ходов и вызовов
   инструментов, вмешательства человека, токены, подтверждённые claims. Сопровождение:
   безвредный рестайл, дрейф accessible name, реальный дефект, нестабильность таймингов;
   метрики — время диагностики, ложные heal, ложные red, верная причина, размер diff.
   Промпты, транскрипты (без секретов) и итоговые тесты публикуются. Перед запуском
   сессий владелец получает строку с числом сессий, моделью и темами.
4. **Закрепление.** Workflow `.github/workflows/benchmarks.yml` (ручной запуск и
   еженедельный cron) пересобирает результаты и сохраняет артефакты. Бюджеты в
   `bench/budgets/` ловят регрессии Testence. Сырые JSON коммитятся в `bench/results/`
   с SHA кандидата и версиями всех плеч.
5. **Видное место.** В README сразу после таблицы «Why Testence» — раздел «Benchmarks»:
   таблица по пяти плечам со столбцами replay (медиана), пойманные ложно-зелёные дефекты
   (идиоматичный и усиленный вариант), время авторинга до принятого теста; отдельной
   строкой — warm-цикл авторинга Testence. Под
   таблицей — строка окружения и даты, команда воспроизведения, ссылки на методику и
   сырые данные. Обновить [launch-thesis.md](../../en/launch-thesis.md) и
   [launch-protocol.md](../../en/benchmark/launch-protocol.md) (en/ru): решение владельца
   выносить измеренные результаты в заголовок при наличии границ применимости.

**Файлы.** `bench/competitive/` (раннер плеч, `requirements.lock`, SeleniumBase-плечо,
агентские сценарии и их результаты), `bench/node/competitive/` (Playwright Test),
`bench/node/cypress/` (новый), `bench/corpus/`, `bench/results/`, `bench/budgets/`,
`.github/workflows/benchmarks.yml`, `README.md`, `docs/{en,ru}/benchmark/*.md`,
`docs/{en,ru}/launch-thesis.md`. Лицензии Cypress (MIT) и SeleniumBase (MIT)
фиксируются в методике; как зависимости пакета они не входят (ADR-0007 не
затрагивается).

**Приёмка.** Одна команда воспроизводит каждую цифру из README. Числа в README совпадают
с закоммиченным JSON (новый тест в `tests/test_documentation.py`). Методика перечисляет
версии всех плеч, железо, число повторов и исключения.

### L15 (P2). Порог входа

1. README и `testing-a-feature.md` начинаются с обычного pytest-теста на DSL без
   PlanSpec: полный evidence, экспорт в TestOps и `allure_id` работают и без плана
   (L07 п. 4). PlanSpec подаётся как следующий уровень — трассировка claims и
   repair-доказательства.
2. Глоссарий `docs/{en,ru}/glossary.md`: PlanSpec, claim, oracle, assurance, proof, pack,
   verdict. Первое упоминание термина на витрине ссылается на глоссарий.
3. Русская документация для QA: `docs/ru/testing-a-feature.md` и `reporting.md`
   покрывают тот же путь, что английские (построчная сверка разделов).

### L16 (P2). Вне кода

- Только Python: переписывание на TypeScript в этап не входит. В README — короткий FAQ:
  тестируемое приложение может быть на любом стеке, тесты пишутся на Python.
- Второй мейнтейнер, включение Discussions, GitHub Release для `v0.1.0a1`, `v0.1.0a2` и
  `v0.1.0a3` — действия владельца в GitHub; исполнитель готовит тексты.

## 6. Несовместимые изменения

| Изменение | Релиз | Как вернуть прежнее поведение |
|---|---|---|
| `fullName`/`testCaseId`/`historyId` в стиле allure-pytest (без явного `case_id`) | a2 | `export.allure.naming: nodeid` |
| Неразрешённая запись test plan → предупреждение | a2 | `--testence-testplan-unresolved=fail` |
| Служебные маркеры не попадают в теги | a2 | — (исправление) |
| Значения параметров вместо digest в экспорте | a2 | `export.parameters: digest` |
| Исключение не-ассерт в теле теста → `broken` в Allure | a2 | — (исправление) |
| Ключи-секреты сопоставляются по токенам; экспорт повторно редактирует | a2 | `evidence.redact.allow_keys` для отдельных ключей |
| Маски в профиле визуального эталона | a2 | эталоны без масок не меняются |
| Новые методы Engine (`hover`, `drag`, `native` и др.) | a3 | сторонние движки объявляют capabilities, остальное — `UnsupportedCapability` |

## 7. Риски

| Риск | Мера |
|---|---|
| Смена именования ломает историю у тех, кто уже загружал `0.1.0a1` в TestOps | Флаг `nodeid`; раздел в CHANGELOG; такие пользователи единичны |
| Маскирование по токенам скроет полезные данные evidence | `allow_keys`, отрицательные контроли в канареечном тесте |
| `warn` для test plan прячет опечатки | Полностью неразрешённый план падает; счётчик и строгий режим в `ci evaluate` |
| Браузерная матрица и бенчмарки удлиняют CI | Браузерный поднабор вместо полного набора; бенчмарки в отдельном workflow |
| Бенчмарк оспорят как подогнанный | Два варианта конкурентов, публикация их тестов, воспроизводимость одной командой |
| MCP расширяет поверхность атаки | Ограничения путей и origin, редактирование ответов, отрицательные тесты |
| Этап растягивается и откладывает рекламу | Реклама стартует на `0.1.0a2` после фаз 1–3 (Q2) |
| Агентские сессии бенчмарка (30 штук) дороги и шумны | Строка с числом сессий и моделью владельцу перед запуском; фиксированные промпты и стартовые коммиты; повтор сессии только по заранее записанному правилу исключения |
| Cypress и SeleniumBase сравниваются не на том же браузере | Ревизия браузера каждого плеча записывается в сырые результаты; расхождение — в строке границ под таблицей README |

## 8. Прогресс

| ID | Статус | PR | Последняя проверка | Остаток |
|---|---|---|---|---|
| Фаза 0 | выполнено | — | `91440a9`, Windows 11, Python 3.12, `TESTENCE_BROWSER_CHANNEL=msedge`: 484 passed, 2 skipped, 322 с | правка `sanitize.py` началась во время прогона; тесты, запускающие подпроцессы, могли подхватить новый код |
| L02 | реализовано, ждёт PR | — | см. раздел 8.1 | trace/video с пометкой `redaction: "none"` — вместе с L12 |
| L07 | реализовано, ждёт PR | — | см. раздел 8.2 | — |
| L03 | реализовано, ждёт PR | — | см. раздел 8.2 | — |
| L08 | реализовано, ждёт PR | — | см. раздел 8.2 | — |
| L09 | реализовано, ждёт PR | — | см. раздел 8.2 | — |
| L06 | не начато | — | — | — |
| L14 | не начато | — | — | — |
| L17 | не начато | — | — | — |
| L04 | у владельца | — | — | живая проверка на кандидате `a2` |
| L01 | не начато | — | — | подтверждение публикации владельцем |
| L12 | не начато | — | — | — |
| L11 | не начато | — | — | — |
| L10 | не начато | — | — | живые проверки платформ (владелец) |
| L13 | не начато | — | — | — |
| L05 | не начато | — | — | — |
| L15 | не начато | — | — | — |
| L16 | не начато | — | — | действия владельца в GitHub |

### 8.1. L02 — что сделано

- `src/testence/evidence/sanitize.py`: сопоставление ключей по частям и фрагментам,
  маскирование по форме значений (JWT, префиксы провайдеров, карты с проверкой Луна),
  параметры URL, правило «слот-имя → значение», `RedactionPolicy`, повторная маскировка
  событий и файлов при экспорте.
- `evidence.redact` и `evidence.mask` в настройках (`config.py`), политика в
  `run.start`, маски в `PlaywrightCdpEngine.screenshot` и в профиле визуального эталона.
- `testence export --attachments full|minimal|none`; Allure-вложения и HTML-отчёт
  проходят повторную маскировку.
- Тесты: `tests/test_redaction_policy.py` (канарейка на 44 формы секретов и 8
  отрицательных контролей, повторная маскировка старого прогона, политика вложений,
  маски на реальном браузере, несовместимость эталона после смены масок, отказ сессии
  при неверных настройках).
- Документация en/ru: `configuration.md`, `reporting.md`, `evidence-schema.md`,
  ADR-0024, уточнение ADR-0023, CHANGELOG.
- Расхождение с планом: маски не входят в digest эталона, а записываются в его профиль
  (смена масок даёт inconclusive). Пункт L02 п. 5 обновлён.
- `cookie` сопоставляется только как точное имя ключа (`cookie`, `cookies`,
  `set-cookie`) и текстом заголовка `Cookie:`, а не как фрагмент имени. Причина:
  замороженный корпус `corpus/r1-correctness-v2.json` пинует digest файла
  `tests/test_evidence.py`, а его тест ожидает, что поле `cookie_line` сохраняет
  `Cookie: <redacted>`. Замороженный источник не менялся.
- Бюджет `bench/scale_profile.py --repeats 3 --check` пройден после изменений.
- Итоговая проверка на ветке (Windows 11, Python 3.12, `TESTENCE_BROWSER_CHANNEL=msedge`): `ruff format --check`, `ruff check`, `mypy src scripts` чистые; `pytest -q` — 507 passed, 2 skipped, 205 с; `pytest examples --testence-headless` — 5 passed, 1 skipped; `testence corpus validate … --structure-only` — exit 0.

### 8.2. Фаза 2 (L07, L03, L08, L09) — что сделано

- **L07.** `src/testence/allure_compat.py` воспроизводит `fullName`, `testCaseId`,
  `historyId`, метки, ссылки, title и description allure-pytest без импорта `allure`.
  Эталон — настоящий allure-pytest 2.16.1 на проекте
  `tests/fixtures/allure-pytest-reference/` (`regenerate.py`, `expected.json`);
  `tests/test_allure_compat.py` сверяет с ним идентичности, имя, description, метки,
  дерево, теги, `titlePath` и параметры. Маркер `testence` принимает метаданные без
  `plan`. Явный `case_id` PlanSpec сохраняет свою идентичность. Режим
  `export.allure.naming: nodeid` — прежнее поведение.
- **L03.** `resolve()` в `src/testence/testplan.py`: устаревшие записи попадают в отчёт
  (предупреждение, событие `testplan.unresolved`, экспорт, квитанция CI), `allure_id`
  и `fullName` выбирают все варианты, перекрытия дедуплицируются, неизвестные поля
  игнорируются с предупреждением, полностью неразрешённый план падает. Строгий режим —
  `--testence-testplan-unresolved=fail`; `ci evaluate --testplan-unresolved fail`.
- **L08.** Статус `failed`/`broken` по `error_kind`, полный трейс, имя и описание из
  PlanSpec, дерево сьютов и `titlePath`, теги по правилу allure-pytest, читаемые
  замаскированные параметры (ADR-0025, `export.allure.parameters: digest`),
  `categories.json`, скриншот падения на упавшем шаге, `evidence.screenshots: always`.
  Найдено при реализации: значение параметра с именем секрета попадает в pytest-id;
  маскировать id нельзя (идентичность), поэтому при сборе выдаётся предупреждение с
  советом задать `ids=`.
- **L09.** `--testence-allure-results` / `TESTENCE_ALLURE_RESULTS`: слушатель evidence
  writer (`src/testence/export/stream.py`) пишет результат теста на `test.end` через
  staging-каталог процесса и атомарное переименование (ADR-0026). Тесты: побайтное
  совпадение с экспортом после прогона, файлы появляются по одному, убитый прогон
  оставляет готовые результаты, под `-n 2` без потерь и дублей (три прогона подряд).
  Найдено при реализации: общий staging-каталог давал гонку под xdist; теперь он свой
  у каждого процесса и потока.
- **L04.** Фраза о непроверенном живом тенанте TestOps убрана из `reporting.md`.
- Проверка на ветке (Windows 11, Python 3.12, `TESTENCE_BROWSER_CHANNEL=msedge`): `ruff format --check`, `ruff check`, `mypy src scripts` чистые; `pytest -q` — 538 passed, 2 skipped, 270 с; тесты документации, контрактов и корпуса после правок документов — 43 passed; `pytest examples --testence-headless` — 5 passed, 1 skipped; заморозка корпуса — exit 0; `bench/scale_profile.py --repeats 3 --check` — бюджет пройден.
- Документация en/ru: `reporting.md` (раздел TestOps переписан: потоковый рецепт с
  `allurectl job-run plan`, миграция с allure-pytest, карточка, выбор по плану),
  `configuration.md`, `evidence-schema.md`, ADR-0025, ADR-0026, CHANGELOG.

## 9. История версий плана

### Версия 1.1 — ревью плана

Ревью версии 1.0 нашло и исправило:

- **Фактическая ошибка:** после `0.1.0a1` в `main` вошло 7 PR с исправлениями
  (#15–#21), а не 6.
- **Один релиз в конце откладывал рекламу на 6–8 недель.** Разбито на `0.1.0a2` (P0,
  безопасность, TestOps, онбординг, витрина) и `0.1.0a3` (остальное); добавлен вопрос
  Q2.
- **Порядок в фазе 2:** L07 (форма `fullName`) идёт раньше L03 (разбор селекторов).
- **Конфликт с ADR-0019:** формула allure-pytest перебивала `case_id`, который по дизайну
  переживает переименование. Теперь явный `case_id` сильнее (L07 п. 2).
- **Дыра в L03:** `warn` превращал полностью неверный план в зелёный прогон нуля тестов.
  Добавлены падение в этом случае и строгий режим в `ci evaluate`.
- **L02:** нет исключений для избыточного маскирования (`allow_keys`); ledger и pack из
  `0.1.0a1` оставались с секретами (добавлено повторное редактирование при экспорте);
  не учитывалось влияние масок на визуальные эталоны.
- **L08:** правило `error_kind` было неопределённым — добавлена таблица соответствия;
  отступление от «только digest» оформлено ADR-0025.
- **L09:** рецепт терял код завершения pytest, который закреплён тестом документации.
- **L13:** не было раздела безопасности (исполнение кода, пути, origin, секреты в
  ответах).
- **L05:** сравнение корректности было уязвимо к обвинению в подгонке — добавлены
  идиоматичный и усиленный варианты конкурентов; расплывчатое «Cypress, если позволит
  время» стало вопросом Q4.
- **L17:** не учитывались внутренние аналитические документы в пользовательском индексе
  и тест на битые ссылки.
- **L04:** проверка владельца теперь привязана к кандидату с исправлениями и
  дополнена сценариями L03 и L09.
- Добавлены столбец зависимостей, оценки сроков, реестр рисков, отдельные открытые
  вопросы с ответами по умолчанию и фаза 0 с базой для оценки роста CI.

### Версия 1.2 — ответы владельца

- Q1: живая проверка TestOps остаётся у владельца, оговорка уходит с витрины, код
  исправляется.
- Q2: два релиза — `0.1.0a2` после фаз 1–3 и `0.1.0a3` в конце.
- Q3: сессии авторинга и сопровождения запускаются. В L05 п. 4 — пять плеч, по 3
  сессии авторинга и 3 сессии сопровождения на плечо.
- Q4: Cypress и SeleniumBase добавлены во все части бенчмарка, у каждого есть
  идиоматичный вариант (Cypress Studio, режим записи SeleniumBase) и усиленный вариант
  с проверкой через API.
- Срок фаз 4–7 увеличен до 5–6 недель; в реестр рисков добавлены стоимость агентских
  сессий и разные браузеры у плеч.
