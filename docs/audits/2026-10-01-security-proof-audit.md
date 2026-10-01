# Аудит безопасности и достоверности доказательств — 1 октября 2026

Статус: исправления реализованы; итоговая проверка полного набора выполняется.
Это инженерная проверка одного Windows-хоста, не разрешение на публичный релиз.
План аудита: `AUD-20261001`. Проверяемая база:
`15ad5d23385dc64c447c7077cb280972185838a4` плюс перечисленные ниже изменения.

## Репозиторий и предыдущая работа

Изначально `main` находился на `e0476b9`, рабочее дерево было чистым. Выполнены
`git fetch origin` и `git merge --ff-only origin/main`: интегрированы четыре уже
принятых коммита, без конфликтов и потери локальной работы. `gh pr list --state open
--json number,title,headRefName,author` вернул `[]`. Единственный worktree — текущий.
Ветка `env-aware-browser-channel` проверена через `git cherry main
env-aware-browser-channel`: её правка уже присутствует в `main` (знак `-`).
Исторические task-ветки сохранены.

Итог предыдущего агента находится в [обзоре продукта](2026-09-28-product-review.md):
основная реализация P0/P1 принята. Внешние испытания P1-1/P1-7/P1-9 и публикация
остаются отдельными задачами; наличие кода не доказывает внешнюю приёмку.

## Находки и выполненные улучшения

| ID / claim | Приоритет | Дефект и исправление | Проверка |
|---|---|---|---|
| A26-01 / `mcp.responses.private` | P0 | MCP маскировал aria и отдельные поля, но URL, описание нажатой цели и исключения возвращались без общей границы маскирования. Все успешные документы и ошибки теперь проходят политику проекта; неверная privacy-конфигурация скрывает подробности | Синтетический пароль отсутствует в ответе click, URL и ошибке; JSON сохраняет структуру |
| A26-02 / `mcp.paths.contained` | P1 | Абсолютный `project/../outside` проходил лексическую проверку containment. И абсолютные, и относительные пути теперь разрешаются до проверки корня | Абсолютный выход через `..` отвергается до чтения run |
| A26-03 / `mcp.stream.survives` | P1 | Список, строка или число в JSON-RPC `params` могли завершить stdio-сервер через AttributeError; пустой список принимался как `{}`. Неверная форма получает `-32602`, следующее сообщение обрабатывается | Шесть неверных форм параметров и следующий `ping` в том же потоке |
| A26-04 / `oracle.identity.exact` | P0 | Python считает `True == 1`: булевый ID/correlation/revision мог дать ложное доказательство числовой привязки. Добавлено различение bool и числа при сохранении точных строковых идентификаторов | Неверные entity/correlation/revision дают `failed`; пробелы в ID не нормализуются |
| A26-05 / `oracle.fields.stable` | P1 | Predicate ссылался на исходный словарь, а public-документ разделял вложенные значения. Изменение словаря могло незаметно изменить ожидание и его описание. Ожидания и public-документы копируются глубоко | Изменение входного и публичного вложенного словаря не ослабляет predicate |
| A26-06 / `oracle.fields.present` | P0 | Отсутствующий ключ совпадал с буквальным ожидаемым значением `<missing>` — диагностическим placeholder. Наличие ключа проверяется отдельно от значения | Отсутствующее поле с таким ожиданием остаётся нарушением |
| A26-07 / `redaction.targets.usable` | P1 | При введении общей маскировки обнаружена чрезмерная маскировка: Target с именем Password читался как пара «секрет/значение», роль textbox терялась. Типизированные адреса элементов отделены от credential name/value records | Target Password остаётся пригодным; известный секрет в нём маскируется; обычная пара Password/value по-прежнему скрывается |

До производственных исправлений новые 11 проверок завершились с **11 failed**:
`outputs/audit-20261001-negative.log` и более полный
`outputs/audit-20261001-negative2.log`. Это воспроизведения дефектов, не успешные runs.
Кейс A26-07 выявлен при ревью собственной правки; исходный MCP ещё не применял
общую структурную маскировку. Не приписывать его предыдущему агенту.

## Приоритетный план следующих улучшений

| Порядок | Работа | Критерий завершения | Статус / зависимость |
|---|---|---|---|
| 1 | Закрыть A26-01–A26-07, проверить privacy/false-green controls и полный набор | Зелёные локальные checks, сохранённые отрицательные воспроизведения и точная привязка исходников | Реализовано; итог полного набора ниже |
| 2 | P1-5: обнаруживать `page.route`/`context.route` внутри `ex.native` | Native fulfill/abort отмечены в evidence; passthrough не объявлен mock; persistence proof не принимает подмену; fresh API read остаётся независимым | Известный незакрытый пробел, явно описан в testing-a-feature.md; не изменялся в этом аудите |
| 3 | Проверить дерево процессов `testence_run` при deadline | Синтетический тест запускает дочерний процесс, timeout сохраняет run/partial evidence и завершает только принадлежащее запуску дерево | По коду MCP subprocess.run убивает непосредственный CLI; CLI запускает pytest отдельно. Утечка дочернего процесса пока не воспроизведена, это риск, а не доказанный инцидент |
| 4 | Приёмка P1-1 на двух backend-приложениях | Через discovery + oracle suggest агент ловит посеянную потерю записи и доказывает восстановленный healthy run; время авторинга отделено от replay | Требуются подготовленные targets и реальные receipts; текущий mock-app не заменяет её |
| 5 | Разделить крупные модули по устойчивым контрактам | Выделить protocol transport из MCP/CLI и pytest identity/lifecycle из plugin без изменения публичных API, ledger и exporter goldens | `pytest_plugin.py`: 1792 строки, engine: 1754, CLI: 1049 на базе аудита. Сначала contract tests, затем отдельные небольшие PR |
| 6 | Матрица кандидата и внешние acceptance receipts | Exact clean candidate на Linux/macOS/Windows и dependency floors; реальные OpenCode/другие client trials, внешние проверки по действующему плану | Локальный аудит эти gates не закрывает; публикация остаётся за владельцем |

## Проверки и окружение

Windows 11 `10.0.26100`, Python `3.12.4` AMD64, uv `0.12.17`, Playwright `1.62.0`,
pytest `9.1.1`, pytest-xdist `3.8.0`. Browser channel из окружения: `msedge`;
для независимых браузерных запусков установлено `TESTENCE_DEBUG_PORT=0`.
Использованы только синтетические fixture/evidence репозитория. Сеть целевых приложений
в этой проверке — loopback; внешние приложения и настоящие клиентские испытания не запускались.

Команды (из корня проекта; логи и basetemp не переиспользованы):

```powershell
uv run pytest tests/test_mcp.py tests/test_expected_state.py tests/test_expected_fields.py -q -k 'invalid_params or absolute_run_paths or all_result_fields or impersonate or boolean_revision or mutating_the_input' --basetemp=.tmp-pytest-audit-20261001-negative2
uv run pytest tests/test_mcp.py tests/test_expected_state.py tests/test_expected_fields.py tests/test_expected_absence.py tests/test_expected_state_corpus.py tests/test_redaction.py tests/test_redaction_policy.py -q --basetemp=.tmp-pytest-audit-20261001-focused3
uv run ruff format --check src tests bench scripts examples
uv run ruff check src tests bench scripts examples
uv run mypy src scripts
uv run pytest -q -n 4 --basetemp=.tmp-pytest-audit-20261001-final
uv run pytest examples -q --testence-headless --basetemp=.tmp-pytest-audit-20261001-examples
uv run python bench/scale_profile.py --repeats 3 --check --output outputs/audit-20261001-scale.json
```

Целевой privacy/oracle/corpus набор: **122 passed, 33.66 s**;
`outputs/audit-20261001-focused3.log`. Примеры: **5 passed, 1 skipped, 49.25 s**;
`outputs/audit-20261001-examples.log`. Первый статический набор прошёл, финальный
набор должен включать последнюю правку typed-target redaction.

Первоначальный последовательный `uv run pytest -q
--basetemp=.tmp-pytest-audit-20261001-full` остановлен вручную на 26% для перехода к
полному xdist-набору после исправлений. Завершено только дерево процесса этого
запуска; это **interrupted**, не успешная проверка. Первый xdist integration run
`audit-20261001-final` обнаружил падение; итог/точный шаг дописывается после завершения.
Во время него дорабатывалась typed-target redaction, поэтому требуется новый полный
run на окончательных исходниках.

## Handoff

Изменённые production-файлы: `src/testence/mcp.py`, `src/testence/oracle.py`,
`src/testence/evidence/sanitize.py`. Regression-файлы: `tests/test_mcp.py`,
`tests/test_expected_state.py`, `tests/test_expected_fields.py`,
`tests/test_redaction_policy.py`. Документация MCP обновлена в en/ru.
Raw logs и artifacts остаются в ignored `outputs/`, `runs/` и новых basetemp.

Последний завершённый proving run: `audit-20261001-focused3`; failing step после
исправлений в нём отсутствует. Общий run пока выполняется; см. его лог выше.
Неуверенность: cross-platform/dependency floors, native mocks, timeout descendants и
внешняя product acceptance. Следующая команда — свежий полный pytest на окончательных
исходниках с новым basetemp, затем static checks и сохранение compact receipt.
