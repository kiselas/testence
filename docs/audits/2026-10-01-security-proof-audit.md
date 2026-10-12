# Аудит безопасности и достоверности доказательств — 1 октября 2026

Статус: локальный аудит завершён; исправления и обязательные checks прошли.
Это инженерная проверка одного Windows-хоста, не разрешение на публичный релиз.
План аудита: `AUD-20261001`. Проверяемая база:
`15ad5d23385dc64c447c7077cb280972185838a4` плюс перечисленные ниже изменения.
Окончательные production/test исходники проверены на чистом коммите
`5bb3794d2e6d93d01be1168afc7586919ab161f3`; последующий коммит дополняет только
этот отчёт и [compact receipt](2026-10-01-security-proof-receipt.json).
Claim IDs ниже — идентификаторы аудита framework, не новая принятая продуктовая PlanSpec.

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
`outputs/audit-20261001-negative.log` (basetemp `negative2`). Это воспроизведения
дефектов, не успешные runs.
Кейс A26-07 выявлен при ревью собственной правки; исходный MCP ещё не применял
общую структурную маскировку. Не приписывать его предыдущему агенту.

## Приоритетный план следующих улучшений

| Порядок | Работа | Критерий завершения | Статус / зависимость |
|---|---|---|---|
| 1 | Закрыть A26-01–A26-07, проверить privacy/false-green controls и полный набор | Зелёные локальные checks, сохранённые отрицательные воспроизведения и точная привязка исходников | Выполнено: полный набор, целевой corpus, examples и static gates |
| 2 | P1-5: обнаруживать `page.route`/`context.route` внутри `ex.native` | Native fulfill/abort отмечены в evidence; passthrough не объявлен mock; persistence proof не принимает подмену; fresh API read остаётся независимым | Известный незакрытый пробел, явно описан в testing-a-feature.md; не изменялся в этом аудите |
| 3 | Проверить дерево процессов `testence_run` при deadline | Синтетический тест запускает дочерний процесс, timeout сохраняет run/partial evidence и завершает только принадлежащее запуску дерево | По коду MCP subprocess.run убивает непосредственный CLI; CLI запускает pytest отдельно. Утечка дочернего процесса пока не воспроизведена, это риск, а не доказанный инцидент |
| 4 | Приёмка P1-1 на двух backend-приложениях | Через discovery + oracle suggest агент ловит посеянную потерю записи и доказывает восстановленный healthy run; время авторинга отделено от replay | Требуются подготовленные targets и реальные receipts; текущий mock-app не заменяет её |
| 5 | Разделить крупные модули по устойчивым контрактам | Выделить protocol transport из MCP/CLI и pytest identity/lifecycle из plugin без изменения публичных API, ledger и exporter goldens | `pytest_plugin.py`: 1792 строки, engine: 1754, CLI: 1049 на базе аудита. Сначала contract tests, затем отдельные небольшие PR |
| 6 | Матрица кандидата и внешние acceptance receipts | Exact clean candidate на Linux/macOS/Windows и dependency floors; реальные OpenCode/другие client trials, внешние проверки по действующему плану | Локальный аудит эти gates не закрывает; публикация остаётся за владельцем |

Дополнительная задача среды: для `evidence.video` нужен Playwright FFmpeg даже при
системном Edge. Текущая `browser_launch_hint` ошибочно предлагает установить браузер,
когда отсутствует FFmpeg. Уточнить подсказку и проверку doctor отдельно; приёмка —
сообщение `python -m playwright install ffmpeg` для этой ошибки без смены канала.

## Проверки и окружение

Windows 11 `10.0.26100`, Python `3.12.4` AMD64, uv `0.12.17`, Playwright `1.62.0`,
pytest `9.1.1`, pytest-xdist `3.8.0`. Browser channel из окружения: `msedge`;
для независимых браузерных запусков установлено `TESTENCE_DEBUG_PORT=0`.
После выявленной ошибки выполнено `uv run playwright install ffmpeg`: установлен
FFmpeg v1011 и Winldd v1007. FFmpeg успешно отвечает на `-version`. Установка произошла
во время final2 до его video-case; исходники в этом прогоне не менялись.
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
uv run pytest -q -n 4 --basetemp=.tmp-pytest-audit-20261001-final2 --durations=15 --junitxml=outputs/audit-20261001-final2.xml
uv run pytest examples -q --testence-headless --basetemp=.tmp-pytest-audit-20261001-examples
uv run python bench/scale_profile.py --repeats 3 --check --output outputs/audit-20261001-scale.json
uv run playwright install ffmpeg
uv run pytest tests/test_trace_video.py tests/test_corpus_grading.py -q --basetemp=.tmp-pytest-audit-20261001-environment --durations=10
```

Целевой privacy/oracle/corpus набор: **122 passed, 33.66 s**;
`outputs/audit-20261001-focused3.log`. Примеры: **5 passed, 1 skipped, 49.25 s**;
`outputs/audit-20261001-examples.log`. Финальный статический набор с typed-target
redaction: **ruff format/check и mypy прошли**, `git diff --check` чист.

Окончательный полный набор: **826 passed, 2 skipped, 419.82 s**, exit 0;
`outputs/audit-20261001-final2.log` и `outputs/audit-20261001-final2.xml`.
Оба skip требуют отсутствующих Windows symlink-привилегий: directory-link export и
file-link ledger reader. Example skip — намеренно исключённый `demo_failure`.
Записи/export и placeholder controls после установки зависимости:
**9 passed, 143.35 s**, `outputs/audit-20261001-environment.log`.
Video/trace case занял 125.09 s в узком прогоне и 38.71 s в полном; это наблюдаемая
вариабельность данного хоста, не performance promise и не доказанный deadlock.
Scale gate: **passed**, три свежих cold samples и warm samples, без нарушений бюджета;
`outputs/audit-20261001-scale.json`. Не сравнивать эти времена с reference host.

Первоначальный последовательный `uv run pytest -q
--basetemp=.tmp-pytest-audit-20261001-full` остановлен вручную на 26% для перехода к
полному xdist-набору после исправлений. Завершено только дерево процесса этого
запуска; это **interrupted**, не успешная проверка. Первый xdist integration run
`audit-20261001-final`: **2 failed, 822 passed, 2 skipped, 708.47 s**, exit 1.
Во время него дорабатывалась typed-target redaction; его нельзя приписать целиком
окончательному коммиту. Точные падения сохранены:

- `tests/test_corpus_grading.py::test_collection_loading_waits_for_all_placeholders_and_rejects_persistent_ones`,
  первая `engine.goto`, `Page.goto: Timeout 10000ms exceeded`. Причина таймаута не
  установлена; те же проверки без изменения timeout прошли в final2 и узком прогоне.
  Это не доказывает, что источник нестабильности устранён.
- `tests/test_trace_video.py::test_retain_on_failure_keeps_the_failed_tests_trace_and_video_only`:
  отсутствие recordings. Ledger `r-20261001-093025-f57411` показывает, что обе synthetic
  проверки были `broken` в setup, `BrowserContext.new_page`: отсутствовал
  `ffmpeg-1011/ffmpeg-win64.exe`. Evidence:
  `.tmp-pytest-audit-20261001-final/popen-gw2/test_retain_on_failure_keeps_t0/runs/r-20261001-093025-f57411/run.jsonl`.
  Зависимость установлена; последующие проверки проверяют настоящие trace/video файлы,
  не skip и не ослабленные ожидания.

## Handoff

Изменённые production-файлы: `src/testence/mcp.py`, `src/testence/oracle.py`,
`src/testence/evidence/sanitize.py`. Regression-файлы: `tests/test_mcp.py`,
`tests/test_expected_state.py`, `tests/test_expected_fields.py`,
`tests/test_redaction_policy.py`. Документация MCP обновлена в en/ru.
Raw logs и artifacts остаются в ignored `outputs/`, `runs/` и новых basetemp.

Последний полный proving run: `audit-20261001-final2`, failing step отсутствует.
Последний узкий proving run: `audit-20261001-environment`, failing step отсутствует.
Неуверенность: причина первого navigation timeout, cross-platform/dependency floors,
native mocks, timeout descendants и внешняя product acceptance.

Следующая независимая диагностика нестабильности (новый basetemp, без interaction retry):
`uv run pytest tests/test_corpus_grading.py::test_collection_loading_waits_for_all_placeholders_and_rejects_persistent_ones -q --basetemp=.tmp-pytest-a26-navigation-next --durations=10`.
После этого следующий implementation slice — native network mocks с controls из
таблицы плана. Hosted matrix должна проверять exact clean candidate; локальная
проверка не заменяет её. Коммиты сохранены локально, push/release не выполнялись.

Продолжение на 2026-10-05: [исследования и slice Q26](2026-10-05-testing-quality-research.md),
[новый handoff](2026-10-05-testing-quality-handoff.md). Статусы и assurance выше
относятся к исходному аудиту 2026-10-01; итог нового slice фиксируется отдельно.
