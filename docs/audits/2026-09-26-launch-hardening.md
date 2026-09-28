# Укрепление перед стартом — 26 сентября 2026

Статус: циклы 1–3 влиты в `main` (PR #5, `7e1e380`); циклы 4–5 — ветка
`launch-hardening-4`. Исходная ветка `launch-hardening` от `main` на `28c951e`. Работа идёт циклами
«аудит → критичные находки → исправление → повторный аудит», пока аудит не перестанет
находить critical и high.

## Критерии «крепкого и функционального» продукта

Каждый критерий проверяется командой или воспроизводимым сценарием, а не оценкой.

| ID | Критерий | Как проверяется |
|---|---|---|
| K1 | Установка и первый запуск | wheel в чистом venv; команды Quick start из README выполняются буквально и дают обещанное, включая pack у упавшего демо |
| K2 | Свой проект по документации | новый пользователь пишет тесты для типового SPA (логин, форма, асинхронный список, чекбокс, select, confirm, параметризация) только по публичной документации, без `ex.native` и без чтения исходников |
| K3 | Понятное падение | сообщение отвечает на «что ожидали, что увидели, какой локатор, сколько элементов нашлось»; pack создан; статус failed/broken верен |
| K4 | Не мешает существующему набору | установка пакета не меняет поведения и артефактов тестов, которые не используют Testence; ошибка конфигурации — одна строка `UsageError`, а не `INTERNALERROR`; работает рядом с pytest-playwright, pytest-xdist, pytest-rerunfailures |
| K5 | Надёжность набора | полный набор зелёный в один процесс и под `-n 6` три раза подряд; `pytest examples` зелёный |
| K6 | Безопасность evidence | ни пароль из `fill`, ни токены, ни строка со страницы не исполняются и не утекают в `run.jsonl`, pack, `report.html`, экспорт |
| K7 | Статические гейты | `ruff format --check`, `ruff check`, `mypy src scripts` чистые |
| K8 | CLI честен | неверный вход — код 2 и одна строка; несуществующий run не выдаётся за пустой успешный |
| K9 | Выход из цикла | повторный аудит (движок/DSL, плагин/CLI, evidence/отчёт) не находит critical или high |

Окружение проверок: Windows 11, Python 3.12.4, Playwright 1.63, `TESTENCE_BROWSER_CHANNEL=msedge`
(Chromium из Playwright на этой машине не стартует), `TESTENCE_DEBUG_PORT=0` для параллели.

## Цикл 1

### Базовый срез

- `ruff format --check`, `ruff check`, `mypy src scripts` — чисто.
- `pytest -q -n 6`: 604 passed, 2 skipped, 4 failed, 137 с. Все четыре падения — только
  под xdist (в один процесс 11/11 зелёные): три в `tests/test_startup_cost.py`
  (контроллерный `EvidenceWriter` читает `PYTEST_XDIST_WORKER` внешнего воркера и не пишет
  manifest), одно в `tests/test_corpus_grading.py` (окно 500 мс под нагрузкой).
- Quick start из wheel в чистом venv: все команды отработали, pack у демо-падения на месте.
- Сценарий K2: SPA из `todo_app.py` (в scratchpad), 8 тестов по документации.

### Находки

| ID | Уровень | Находка | Статус |
|---|---|---|---|
| A1-01 | critical | `report.html`: JSON событий вставлен в `<script>` без экранирования; `</script>` из консоли страницы исполняется при открытии отчёта | исправлено |
| A1-02 | critical | Ошибка в `testence.json` (например `debug_port: 99999`) роняет любую сессию pytest с `INTERNALERROR` | исправлено: `UsageError` (код 4); в сессии без Testence ошибка откладывается до сбора и не срабатывает |
| A1-03 | critical | Любая сессия pytest в окружении с пакетом пишет `runs/<id>/`, даже если ни один тест не использует Testence | исправлено: writer в отложенном режиме, запись только в сессии Testence (CLI, `--testence-*`, фикстура или маркер) |
| A1-04 | high | `switch_page`/`popup` навешивают слушатели сети и консоли повторно; одно сообщение попадает в evidence N раз | исправлено: страница со слушателями запоминается |
| A1-05 | high | pytest-rerunfailures: повторы получают один `attempt_id`; pack упавшей попытки остаётся на итоговом passed | исправлено в цикле 2 (A2-00) |
| A1-06 | high | `report`/`metrics` на несуществующем run — traceback и код 1; `inspect`/`export` — код 0 и «пустой» run | исправлено: код 2 и одна строка; каталог без ledger по-прежнему incomplete-run (контракт `test_metrics`) |
| A1-07 | high | Падение `expect_text` не показывает фактический текст; 0 или >1 совпадений — сырой Playwright без подсказки | исправлено: `describe_matches` — текст единственного совпадения, число и тексты, похожие записи aria |
| A1-08 | medium | `navigate()` сравнивает origin префиксом строки: `localhost:3000` ≈ `localhost:30001` | исправлено: `_under()` сравнивает scheme, netloc и границу пути |
| A1-09 | medium | `wait_for_count(minimum=0)` ждёт первый элемент и падает сырым TimeoutError | исправлено |
| A1-10 | medium | `run.end.not_run` никогда не считается; при `-x` сводка не сходится с числом собранных | исправлено для одиночного процесса; под xdist сводку даёт reconcile |
| A1-11 | medium | oracle `diff_views`: `True` и `1` считаются равными | исправлено: bool строго, вложенный текст без внешних пробелов, `1 == 1.0` |
| A1-12 | medium | Тесты набора падают под xdist (A1 базовый срез) | исправлено: явный `worker=""`, окно 2 с |
| A1-13 | high | Порт 9222 по умолчанию общий на машину: второй прогон на хосте получает браузер без devtools-сервера, `launch` висит до таймаута 180 с (пойман в полном прогоне) | исправлено: по умолчанию порт выбирает ОС, явный `debug_port` + N на воркер |

Отложено как low или граница по замыслу (не блокирует старт): карточные номера в JSON-числах
не маскируются (маскирование 16–19-значных чисел по Луну задело бы snowflake-ID);
секреты в свободном тексте без `key=value` маскируются только по значению — это граница
политики, её нужно явно описать в документации; `expect_count(0)` и `expect_hidden`
проходят сразу, если элементов ещё нет, как в Playwright; фиксированный порт 9222 по
умолчанию; `inspect` без `--json` не печатает путь к pack; heal появляется только при
известном fingerprint — это починка дрейфа, а не подсказка при первом промахе.

### Проверки после исправлений цикла 1

- `ruff format --check`, `ruff check`, `mypy src scripts` — чисто.
- `pytest -q -n 6` без `TESTENCE_DEBUG_PORT` три раза подряд: 649 passed, 2 skipped
  (144 с, 135 с, 183 с), без падений.
- `pytest examples -q --testence-headless`: 5 passed, 1 skipped.
- K2 повторно на свежем wheel: `select` по неверной подписи — «no element matches; the
  accessibility tree has … combobox "Show"»; неверный текст — «1 element matches,
  showing '0 items left'». Юнит-сессия без Testence не создала `runs/`.
- Замороженный корпус: правка `tests/test_pytest_lifecycle.py` сломала digest
  `defect.worker-crash` и была возвращена; проверка перенесена в
  `tests/test_plugin_opt_in.py`. Файлы корпуса больше не менялись.

Новые тесты: `tests/test_plugin_opt_in.py`, `tests/test_failure_diagnostics.py`,
дополнения в `tests/test_report.py`, `tests/test_application.py`.

## Цикл 2

Аудит: ревью диффа цикла 1, области, которых цикл 1 не касался (auth, API-клиент,
изоляция, readiness, конфигурация, dev_browser/watch, установка навыков), и сценарий
«новый пользователь» по оставшемуся словарю DSL (фреймы, shadow DOM, upload/download,
popup, dialog, soft, clock, screenshot, native) на отдельном SPA.

| ID | Уровень | Находка | Статус |
|---|---|---|---|
| A2-00 | high | pytest-rerunfailures (A1-05, L12 п. 8) | исправлено: смена попытки в `pytest_runtest_logstart`; `rerun`/`retries`/`flaky` на `test.end`; `run.end.reruns`; reconcile и `LoadedRun.tests` считают итоговые попытки; Allure — результат на попытку под одним `historyId`; CTRF — `retries`, `flaky`, `retryAttempts`; JUnit — свойства; `ci evaluate --flaky warn\|fail`; `inspect` перечисляет flaky |
| A2-R1 | critical | Регрессия цикла 1: `TESTENCE_RUN_ID`, оставленный первой сессией в `os.environ`, делал вторую сессию того же процесса «запущенной CLI» | исправлено: `pytest_unconfigure` снимает run id, который сессия выставила сама |
| A2-R2 | high | Регрессия цикла 1: если все воркеры xdist упали до shard, ledger не оставался | исправлено: `worker.crash` активирует ledger контроллера |
| A2-R3 | medium | `_same()` считает `list` и `tuple` равными | оставлено намеренно: в JSON и ledger это один массив, прежний «diff» между одинаково отображаемыми значениями был ложно-красным |
| A2-01 | high | Профиль целиком заменял таблицы базы, в том числе `extra.evidence.redact`: секреты попадали в evidence профиля | исправлено: `_merge_profile` сливает таблицы рекурсивно |
| A2-02 | high | На Windows кэш сессии наследовал ACL каталога (`chmod 0o600` ничего не ограничивает) | исправлено: `icacls /inheritance:r /grant:r <user>:F` до записи; не получилось — кэш не пишется |
| A2-03 | medium | readiness `http` принимал ответ другого origin после редиректа | исправлено: итоговый URL сверяется с origin цели |
| A2-04 | medium | `.env`: хвостовой `# комментарий` становился частью значения | исправлено: `_env_value` |
| A2-05 | medium | Повтор получал тот же seed marker | исправлено: `attempt_id` из контекста теста |
| A2-06 | high | `expect_screenshot` без эталона — `FileNotFoundError` на языке ОС | исправлено: `VisualUnavailable` с подсказкой (проверка и раньше была inconclusive) |
| A2-07 | high | Человекочитаемый `inspect` показывал только assurance («2 unverified») и не говорил, что тесты прошли | исправлено: сначала исполнение, затем assurance |
| A2-08 | medium | Нет сигнатур `dialog`/`download`/`upload`/`popup`/`frame`/`expect_screenshot` в документации; нет shadow DOM и примера `evidence.screenshots` | исправлено в `testing-a-feature.md` и `configuration.md` (en/ru) |
| A2-09 | medium | Флейк обратного отсчёта с `ex.clock.fast_forward` под `-n 2`: `fast_forward` запускает таймер один раз, цепочка доходила до конца в реальном времени | исправлено: добавлен `ex.clock.run_for`, описана разница |

Проверено и чисто (по отчётам аудита): ApiClient (same-origin, редиректы, TLS, не-JSON),
`AuthContext.cookie_header`, стратегии входа без утечек в исключения, `managed_paths` и
`agent install` (symlink, зарезервированные имена, containment), readiness `file` и
`--apply-fixes` (без shell, вывод отброшен), парсер `.env` (кавычки, `export`, `=`, CRLF,
BOM), watch-поллер.

Вопрос владельцу (решение не принималось): pytest-rerunfailures распространяется под
MPL-2.0, а ADR-0007 требует permissive-лицензий для runtime-зависимостей, поэтому extra
`retry` из плана L12 п. 8 не добавлен. Поддержка работает без зависимости, через хуки
pytest; `tests/test_reruns.py` пропускается, если пакета нет. Чтобы CI покрывал повторы,
нужно решить, допустим ли пакет в dev-группе (ADR-0007: «dev tools permissive where
practical»).

### Проверки после исправлений цикла 2

- `ruff format --check`, `ruff check`, `mypy src scripts` — чисто.
- `pytest -q -n 6`: 670 passed, 2 skipped, 1 failed — `test_loopback` поймал мой новый
  тест с `ThreadingHTTPServer` (35 с на bind под macOS); заменён на `LoopbackHTTPServer`,
  файл зелёный.
- `pytest examples -q --testence-headless`: 5 passed, 1 skipped.
- `tests/test_reruns.py` (с установленным pytest-rerunfailures 16.7): 6 passed, 12 с.

## Цикл 3

Аудит: ревью диффа цикла 2 и «генеральная репетиция» из wheel рабочего дерева в чистом
venv — Quick start буквально по README, оба пользовательских проекта (todo-SPA и
SPA с фреймами, shadow DOM, диалогами, upload/download, popup, clock) в режимах plain,
`-n 2`, `--reruns 1` и `testence run`, затем `inspect`, `report`, `export` во все три
формата и `ci evaluate` (в том числе `--flaky fail`).

| ID | Уровень | Находка | Статус |
|---|---|---|---|
| A3-01 | high | Регрессия A2-R2: падение воркера активировало ledger и в наборе без Testence (нарушение K4) | исправлено: падение сохраняется только в сессии, которая уже пишет запуск; иначе запуск пишется при закрытии, если есть shard. Граница: если в сессии без явного признака все воркеры падают до сбора, ledger не остаётся — вывод pytest показывает падение |
| A3-02 | high | `metrics.aggregate()` считал попытку-повтор отдельным исходом: тест `broken`→`failed` без единого прохода становился flaky | исправлено: повторы не считаются, итоговый `flaky` засчитывается |
| A3-03 | medium | readiness `_origin` различал `http://h` и `http://h:80`, `h.` и `h` | исправлено: нормализация как в ApiClient |
| A3-04 | medium | Повторы при `--dist each` могли прикрепиться к итоговой попытке другого воркера | исправлено: воркер в ключе |
| A3-05 | low | Профиль с `{}` больше не очищает таблицу базы | описано в `configuration.md` (en/ru) |
| A3-06 | high (docs) | README обещал «UI state» в pack, скриншот же включается только явно | исправлено: README называет aria-дерево и опцию `capture_policy.screenshots` |
| A3-07 | medium | Тире в новой строке `inspect` превращалось в кракозябры в консоли cp866/cp1251 | исправлено: строка ASCII, тест проверяет `isascii()` |
| A3-08 | medium | Подсказка «в дереве есть combobox "Show"» рядом с неудачным поиском читалась как противоречие | исправлено: подсказка — готовая цель `Target('role', 'combobox', name='Show')` |

Репетиция подтвердила без замечаний: `doctor`, `init`, `plan prepare`, `run`, демо ложного
зелёного, `report` (полностью автономный HTML), `demo run --json`; посторонний прогон не
создаёт `runs/`; пароль `s3cret-pw` не найден ни в одном артефакте и экспорте; flaky виден в
`inspect`, CTRF (`retries`, `flaky`, `retryAttempts`), JUnit (`testence.*`), а
`ci evaluate --flaky fail` возвращает код 10.

Не исправлялось: обратный отсчёт на `fast_forward` в пользовательском проекте нестабилен —
это ожидаемое поведение `fast_forward`, для такого таймера есть `run_for` (A2-09).

## Выход из цикла

Ревью изменений цикла 3 не нашло critical и high. Две находки (medium и low) в подсказке
`describe_matches` исправлены: экранированные кавычки в имени снимаются, роли с дефисом
(`graphics-symbol`) распознаются; тест `test_a_hint_names_the_element_as_its_target_would`.

| Критерий | Итог |
|---|---|
| K1 | выполнен: Quick start из wheel в чистом venv (циклы 1 и 3) |
| K2 | выполнен: два пользовательских SPA по документации; найденные пробелы документации закрыты |
| K3 | выполнен: сообщение называет, что нашла цель; pack у каждой упавшей попытки |
| K4 | выполнен: `tests/test_plugin_opt_in.py` (без записи, битый конфиг, xdist, два `pytest.main`, падение воркера); работает рядом с pytest-playwright, xdist, rerunfailures |
| K5 | выполнен: `-n 6` трижды 649/649, после циклов 2–3 — 675 passed; в один процесс 671 passed (9 мин под нагрузкой); examples 5 passed |
| K6 | выполнен: XSS закрыт, маскировка профилей, ACL кэша; пароль из `fill` не найден ни в одном артефакте |
| K7 | выполнен: ruff format/check, mypy чистые |
| K8 | выполнен: не-run — код 2 и одна строка |
| K9 | выполнен: последний раунд без critical/high |

Последний полный прогон (`-n 6`, 675 passed, examples 5 passed) выполнен до правки
регулярного выражения подсказки; после неё `tests/test_failure_diagnostics.py` — 20 passed.

Решение владельца (28.09.2026) по pytest-rerunfailures (MPL-2.0): не зависеть от пакета,
а реализовать нужное самим. Сделано: `src/testence/reruns.py`, опция `--testence-reruns N`
(`TESTENCE_RERUNS`, 0–5). Повторяется весь тест через штатный `runtestprotocol`; перед
повтором сбрасываются упавшие фикстуры (кеш и финализаторы), экземпляр класса теста и,
если упала настройка коллектора, весь стек настройки. `xfail` не повторяется, `-x` не
повторяет после остановки. Записи ledger и экспорт не менялись: промежуточная попытка
получает `rerun`, как у pytest-rerunfailures, поэтому набор на этом пакете пишется так
же. `tests/test_reruns.py` больше не пропускается и проходит без пакета (10 тестов).

Открыто для владельца:
- Живые проверки CI на Linux и macOS: изменения проверены только на Windows 11 с
  `TESTENCE_BROWSER_CHANNEL=msedge`.
- Пункты плана этапа 4, которые этот аудит не затрагивал: L11 Firefox/WebKit, L13 MCP,
  L05 полностью, L15, L12 п. 1 drag и п. 9 карантин, релиз L01.

Следующая проверка: `uv run pytest -q` и `uv run pytest examples -q --testence-headless`
в CI на ветке `launch-hardening`.

## Цикл 4 (28.09.2026)

PR [kiselas/testence#5](https://github.com/kiselas/testence/pull/5) с циклами 1–3 открыт
в `main`. Цикл 4 идёт в ветке `launch-hardening-4` и проверяет то, чего циклы 1–3 не
касались. К критериям K1–K9 добавлены:

| ID | Критерий | Как проверяется |
|---|---|---|
| K10 | Цикл агента | агент только по навыкам plan/author/triage/repair и `agent-workflow.md` проходит план → тест → поломка UI → разбор по `inspect --json` и pack → починка → зелёный; каждая названная команда, флаг и поле существуют |
| K11 | Переход с allure-pytest и TestOps | набор на `@allure.*`, `allure.dynamic.*`, `parametrize(ids=...)` сохраняет `historyId`, `testCaseId`, метки, ссылки и параметры — с allure-pytest и без него; test plan TestOps выбирает нужное; рецепты документации работают буквально |
| K12 | Платформы | CI зелёный на Linux, macOS и Windows, Python 3.10 и 3.12, в том числе на минимальных версиях зависимостей |
| K13 | Повторы среди плагинов | `--testence-reruns` верен со всеми scope фикстур, xdist `load`/`loadscope`/`loadfile`, `-x`, `--lf`, xfail, pytest-timeout, pytest-rerunfailures |

Аудит: три агента на sonnet (K10, K11, K13) в отдельных venv из wheel рабочего дерева;
K12 — CI PR #5.

| ID | Уровень | Находка | Статус |
|---|---|---|---|
| A4-01 | critical | Без allure-pytest декораторы `@allure.*` ничего не делали: пакет `allure` создаёт метки только через слушателя, которого регистрирует allure-pytest. Набор, закончивший переход и удаливший allure-pytest, молча терял метки, ссылки, id и заголовки (K11). Эталон в `tests/fixtures/allure-pytest-reference` пишет сырые метки и поэтому этого не ловил | исправлено: `testence.allure_hooks` регистрирует тех же слушателей, если allure-pytest не активен; дополнение к ADR-0013; `tests/test_allure_hooks.py` на настоящем пакете `allure` (dev-группа `allure-python-commons`, Apache-2.0) |
| A4-02 | high | `allure.dynamic.*` не попадал в экспорт ни с allure-pytest, ни без него | исправлено: значения попытки пишутся в `test.end.allure_dynamic` и накладываются на результат Allure, как в allure-pytest |
| A4-03 | medium | `@allure.severity(allure.severity_level.CRITICAL)` экспортировался как `Severity.CRITICAL` | исправлено: значение Enum |
| A4-04 | high (docs) | `allure.step` и `allure.attach` не переносятся, а раздел о переходе этого не говорил | описано в `reporting.md` (en/ru): шаги Allure — шаги Testence, вложения — evidence |
| A4-05 | high | При загруженном allure-pytest он сам применяет test plan TestOps: запись с nodeid или `testence://` у него ничего не выбирает, испорченный файл плана — INTERNALERROR в allure-pytest | описано с обходом `-p no:allure_pytest` (после A4-01 декораторы без него работают); код стороннего плагина не меняется |
| A4-06 | medium | Секретное значение параметра без `ids=` остаётся в имени варианта (`test_login[hunter2]`) | оставлено: плагин предупреждает `PytestWarning` с советом дать `ids=`; маскировать nodeid значит менять идентичность теста |
| A4-07 | high | `--testence-reruns`: попытка, которую повторяют, разбиралась как перед настоящим следующим тестом; у последнего теста модуля или прогона это сносило фикстуры модуля и сессии, и повтор создавал их второй раз (K13) | исправлено: teardown такой попытки получает `nextitem=item`, а хук разбирает только сам тест и сломанный scope; тест `test_a_repeat_keeps_the_scopes_around_the_test` |
| A4-08 | medium | Строгий XPASS повторялся, хотя документация обещает, что xfail не повторяется | исправлено: оценённый pytest xfail не повторяется |
| A4-09 | medium (docs) | Не описано поведение рядом с pytest-rerunfailures (`--reruns` вместе с `--testence-reruns`), pytest-timeout (метод `thread` завершает процесс, ledger без `run.end`) и собственным `--junitxml` | описано в `reporting.md` (en/ru) |
| A4-10 | low | `-rR` не перечисляет повторы в сводке pytest (в терминале есть `R` и счётчик `N rerun`) | оставлено |
| A4-11 | medium | Навык автора и `agent-workflow.md` предлагали `--profile staging`; у проекта из `testence init` профилей нет, команда падает с кодом 2 (K10) | исправлено: `--profile` необязателен и описан |
| A4-12 | low | `agent install --client claude` копирует и `agents/openai.yaml` | оставлено: файл инертен, а фильтр по клиенту меняет digest набора |
| A4-13 | low | Навык repair не называл файл памяти fingerprint | исправлено: `.testence/fingerprints.json` |
| A4-14 | high (фича) | Нет drag-and-drop (L12 п. 1): kanban, сортировка, слайдер уходили в `ex.native` без шага и fingerprint | сделано: `ex.drag(source, destination)`, падение описывает и источник, и цель; `tests/test_dsl_drag.py` |
| A4-R1 | high | CI минимальных зависимостей (pytest 8.0): повтор метода класса получал прежний `self` — у 8.0 нет `Function._instance` | исправлено в PR #5 (`c521fc4`), проверено на pytest 8.0 |
| A4-R2 | medium | Тест ACL кэша на Windows падал на раннерах GitHub: `icacls` печатает по-разному, а DACL раннера явно даёт права SYSTEM, Administrators и OWNER RIGHTS | исправлено в PR #5 (`c521fc4`, `700108e`, `9d7b518`): тест падает только на правах кого-то ещё |

Проверено и чисто (по отчётам агентов): `doctor`, `init`, `agent install/verify`, `plan
validate/prepare` (fail closed на сценарии без readiness и на отсутствующем oracle),
сообщение о поломке UI с готовой `Target(...)`, полный pack (`heal.json`, `aria.txt`,
`TRIAGE.md` и др.), `verdict validate`, `repair validate`; `fullName`/`testCaseId`/
`historyId` совпадают с allure-pytest; потоковый экспорт побайтно равен экспорту после
прогона; test plan по `id` и `fullName`; повторы с `-x`, `--lf`, `--runxfail`,
`pytest.exit`, xdist `load`/`loadscope`/`loadfile`, падение воркера; Python 3.10.21.

### Проверки после исправлений цикла 4

- `ruff format --check`, `ruff check`, `mypy src scripts` — чисто.
- `pytest -q -n 4`: 691 passed, 2 skipped (6 мин 25 с). Предыдущий прогон нашёл две
  проблемы, обе исправлены: замороженный `tests/test_identity.py` передаёт фиктивный item
  без `config` (слушатель `allure.dynamic` теперь ищется через `getattr`), а сводка
  pytest под нагрузкой несла лишнее «1 warning» (проверка по частям).
- `pytest examples -q --testence-headless`: 5 passed, 1 skipped.
- `tests/test_reruns.py` на pytest 8.0.0 и 9.1: 11 passed; протокол повторов вручную под
  xdist `--dist loadscope` и с `--runxfail` — фикстуры модуля создаются один раз.
- K12: CI PR #5 на `9d7b518` — все задачи Linux, macOS и Windows (Python 3.10, 3.12,
  минимальные зависимости, Quality, Visual) зелёные; PR влит squash-коммитом `7e1e380`.

## Цикл 5 — повторный аудит

Агент на sonnet проверил дифф цикла 4: протокол повторов против `_pytest.runner`
(вложенные классы, все scope, сломанный `setup_module` у последнего теста, падение
teardown на повторяемой попытке, варианты xfail, `--maxfail`), слушатель allure
(маскирование `allure_dynamic` при записи и экспорте, попытки не смешиваются, потоковый
экспорт, `--strict-markers`), `drag` и документацию en/ru. Critical и high нет.

| ID | Уровень | Находка | Статус |
|---|---|---|---|
| A5-01 | low | Описание цели drag не выводилось, если описание источника пустое | исправлено |
| A5-02 | low | `allure.dynamic.parameter` не переносится | описано в `reporting.md`: параметры берутся из pytest |
| A5-03 | low | Вложенный `pytest.main()` внутри теста регистрирует второго слушателя в общем `allure_commons.plugin_manager`; внешний накапливает значения, которые никто не читает | оставлено |

## Выход из цикла 4–5

| Критерий | Итог |
|---|---|
| K1–K9 | сохраняются: полный набор и examples зелёные, статические гейты чистые |
| K10 | выполнен: цикл агента проходит по навыкам; единственная medium-находка (`--profile staging`) исправлена |
| K11 | выполнен: декораторы и `allure.dynamic.*` переносятся с allure-pytest и без него; ограничения (шаги, вложения, test plan при загруженном allure-pytest) описаны |
| K12 | выполнен: CI PR #5 зелёный на трёх ОС, Python 3.10/3.12 и минимальных зависимостях |
| K13 | выполнен: повторы сохраняют scope, не трогают xfail, поведение рядом с другими плагинами описано |

Открыто для владельца: L11 Firefox/WebKit, L13 MCP, L05 полностью, L15, L12 п. 9
карантин, релиз L01; A4-06 (секрет в id варианта без `ids=`), A4-12, A5-03.
