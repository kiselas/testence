# Справочник на одной странице

Всё, к чему тянется автор теста, в одном месте, со ссылками на страницу, где это
объяснено. Тест проверяет, что здесь перечислены все шаги `ex` и все команды.

## Target

`Target(kind, value, name=None, nth=None, exact=None, within=None)` из `testence.engine`.
`kind` — `role`, `label`, `text`, `testid`, `placeholder` или `css` (значение `xpath=` —
это CSS-цель). Совпадение по идентичности (`label`, `placeholder`, `name` у роли) точное;
`text` совпадает по подстроке, если не `exact=True`. `within` ограничивает поиск другой
целью; `nth` выбирает один из законных повторов. Два совпадения роняют шаг и называются в
сообщении. [Возможности engine](engine-capabilities.md)

## Шаги `ex`

Каждый шаг принимает `intent` (что пользователь делает или видит) и записывает его.

| Группа | Шаги |
|---|---|
| Навигация | `ex.goto(url)`, `ex.navigate(url, hard=False)`, `ex.open(route)`, `ex.reload()`, `ex.url()` |
| Действия | `ex.click(target, fast=False, modifiers=None)`, `ex.double_click`, `ex.right_click`, `ex.fill(target, value, fast=False)`, `ex.type(target, text)`, `ex.select(target, value, label=)`, `ex.press(key, target=None)`, `ex.check`, `ex.uncheck`, `ex.hover`, `ex.focus`, `ex.scroll_into_view`, `ex.drag(source, destination, html5=False, handle=None)`, `ex.drag_by(target, dx, dy=0, steps=8)`, `ex.upload(target, paths)`, `ex.download(target, path)` |
| Проверки | `ex.expect_text(target, text, exact=True)`, `ex.expect_visible`, `ex.expect_hidden`, `ex.expect_value`, `ex.expect_count`, `ex.expect_enabled`, `ex.expect_disabled`, `ex.expect_checked(checked=True)`, `ex.expect_attribute`, `ex.expect_url(contains=, equals=)`, `ex.expect_settled`, `ex.expect_screenshot`, `with ex.soft(intent):` |
| Читалки | `ex.text`, `ex.texts(minimum=1)`, `ex.count`, `ex.is_visible`, `ex.attribute`, `ex.input_value`, `ex.box(settled=False)`, `ex.boxes`, `ex.storage_item`, `ex.viewport()`, `ex.read_js(intent, function, arg=None, target=None)` |
| Сеть | `with ex.expect_request(path, method=) as sent:`, `with ex.expect_outcome(outcomes):`, `ex.route(pattern, status=, json=)`, `ex.rewrite_response`, `ex.ws_gate(pattern)`, `ex.settle()` |
| Страницы и окна | `ex.popup(target)`, `ex.switch_page(index, url_contains=)`, `ex.new_page(url)`, `ex.close_page()`, `with ex.frame(target):`, `ex.dialog(target, accept=True)`, `ex.set_viewport(width, height)` |
| Состояние | `ex.set_storage({...}, session=False)`, `ex.reset_storage(keys)`, `ex.clock` (`install`, `fast_forward`, `run_for`, `pause_at`, `resume`, `set_fixed_time`) |
| Оракулы | `ex.verify(name, expected, actual)`, `ex.verify_state(name, read, expected)`; `save_and_verify_state(...)` из `testence.oracle` |
| Улики | `ex.attach(name, data)`, `ex.note(text)` |
| Прямой доступ | `with ex.native(intent) as page:` (страница после него не передаётся дальше) |
| Служебное | `with ex.step(intent, target):` для кита или адаптера, `ex.finish()` (его вызывает плагин) |

## Киты

`from testence.kits import koobiq, react_aria, react_select, xyflow, codemirror`.
[Киты компонентов](kits.md)

## Фикстуры

| Фикстура | Что это |
|---|---|
| `ex` | шаги выше в браузере, вошедшем по `auth` проекта |
| `testence_engine` | движок под `ex` |
| `testence_api` | `ApiClient` с сессией `ex`: `get`, `get_fresh`, `post`, `patch`, `delete`, `assert_absent` |
| `testence_actor(name)` | второй пользователь из `users`: `.api`, `.ex` |
| `testence_settings` | разобранные `testence.json` и профиль |
| `testence_auth` | сам вход |
| `testence_writer` | запись улик прогона |
| `testence_namespace`, `testence_seed_marker` | пространство имён воркера для засеянных данных |
| `testence_control` | негативный контроль прогона или `None` |
| `testence_fingerprints` | хранилище отпечатков элементов |

## Маркер

`@pytest.mark.testence(...)`: `plan`, `claims`, `case_id` (кейс PlanSpec); `allure_id`,
`title`, `description`, `severity`, `labels`, `links`, `tms` (отчёт;
`tms={"cases": [...]}` для ручных кейсов); `anonymous=True` (без входа), `fresh_page=True`
(не под `page_reuse: module`), `timeout_s` (срок теста). [Отчёты](reporting.md)

## Параметры pytest

| Параметр | Что делает |
|---|---|
| `--testence-profile NAME`, `--testence-base-url URL`, `--testence-auth`, `--testence-api-prefix` | цель |
| `--testence-headless`, `--testence-browser-channel`, `--testence-browser-reuse`, `--testence-cdp URL` | браузер |
| `--testence-test-timeout S` | срок на тест ([настройка](configuration.md#срок-на-тест)) |
| `--testence-reruns N` | повтор упавшего теста, записанный попытками |
| `--testence-schedule longest-first` | самые долгие модули первыми под xdist |
| `--testence-control NAME` | негативный контроль |
| `--testence-runs-root DIR` | куда пишутся прогоны |
| `--testence-allure-results DIR`, `--testence-empty-testplan`, `--testence-testplan-unresolved` | Allure и TestOps |
| `--testence-full-trace` | все кадры трассировки |

## `testence.json`

Поля: `base_url`, `project_id`, `api_prefix`, `auth`, `login_path`, `api_login_path`,
`cdp_url`, `execution_mode`, `browser_channel`, `debug_port`, `headed`, `timeout_ms`,
`verify_tls`, `ca_bundle`, `runs_root`, `user_var`, `password_var`, `profiles`. Объекты и
ключи возможностей: `capture_policy`, `evidence`, `export`, `readiness`, `controls`,
`users`, `emulation`, `viewport`, `page_reuse`, `browser_reuse`, `test_timeout_s`,
`target_info`, `cases`, `test_id_attribute`, `session_cookie`, `session_probe_path`,
`storage_state`, `api_allowed_origins`, `api_auth_from_storage`.
[Настройка](configuration.md)

## Команды

| Команда | Что делает |
|---|---|
| `testence doctor [--target]` | проверить Python, браузер, цель и вход |
| `testence init` | заготовка онбординга без конфликтов |
| `testence status` | активный пакет, проект и настройки |
| `testence run [-- PYTEST_ARGS]` | прогон тестов под одним run id |
| `testence prove` | зелёный прогон плюс по прогону на контроль, строгий режим |
| `testence debug NODE` | один тест в охраняемом процессе с ARIA падения |
| `testence explore PATH` | ARIA страницы, уникальные Target и строки китов |
| `testence watch -- CMD` | перезапуск команды по сохранению |
| `testence inspect RUN` | что сделал прогон, его пакеты и сборка цели |
| `testence report RUN` | самодостаточный отчёт HTML |
| `testence timing RUN [OTHER]` | setup, call, teardown, вызовы API и ожидания; сравнение |
| `testence cases [--run RUN]` | ручные кейсы против тестов и итогов |
| `testence export RUN --to allure\|ctrf\|junit` | формат для интеграций |
| `testence metrics RUN...` | сводные метрики |
| `testence inventory RUN` | справочники экранов по прогону |
| `testence oracle suggest RUN` | проверки API, которые подразумевает прогон |
| `testence plan validate\|prepare\|skeleton` | проверка PlanSpec и заготовки тестов из файла кейсов |
| `testence seed scaffold --openapi DOC` | фикстуры уборки по OpenAPI |
| `testence verdict validate\|submit`, `testence repair validate` | вердикты и ремонт агента |
| `testence ci evaluate\|summary`, `testence delivery run` | квитанции CI и выгрузка |
| `testence quality apply\|rollback\|summary` | пакеты качества для нескольких проектов |
| `testence agent install\|verify` | переносимые навыки агента |
| `testence mcp` | MCP-сервер |
| `testence auth export` | вход как storage state |
| `testence capabilities` | что объявляет движок |
| `testence bench -- CMD`, `testence demo run` | повторные замеры, демо доказательства |
| `testence corpus validate`, `testence release validate` | только для сопровождающих Testence |
