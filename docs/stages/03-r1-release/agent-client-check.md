# Проверка R1 в Codex и Claude Code

Решение владельца от 8 сентября 2026: Codex доступен в текущей сессии;
Claude Code владелец попробует позже. Наличие клиента не означает прохождение
workflow. Предыдущий triage-only smoke остаётся историческим доказательством.

## Что подготовит исполнитель

После зелёного CI на `codex/r1-rc` скачать artifact
`testence-<полный-SHA>-candidate-distributions` этого run через `gh run download`.
Сверить wheel SHA-256 с `reproducible-build.json`. Не скачивать «latest» wheel
из другого run и не устанавливать editable source.

Для каждого клиента создать отдельный пустой каталог:

- `.tmp/agent-clients/codex`;
- `.tmp/agent-clients/claude`.

В каждом создать `.venv` через `uv venv`, установить один и тот же wheel через
`uv pip install --python .venv/Scripts/python.exe <wheel>`, установить Chromium
через `.venv/Scripts/python.exe -m playwright install chromium`. В `candidate.json`
записать полный source SHA, CI run URL, wheel path/hash и фактический Python.

Установить соответствующий managed pack:

```powershell
.venv/Scripts/testence.exe agent install --project . --client claude --json
.venv/Scripts/testence.exe agent verify --project . --client claude --json
```

Для Codex заменить `claude` на `codex`. Сохранить оба JSON и exit codes.
Не смешивать два workspace и не копировать готовый verdict между клиентами.

## Что сделать владельцу в Claude

1. Открыть **Claude Code** в подготовленном каталоге
   `D:\Projects\testence\.tmp\agent-clients\claude`.
   Обычный веб-чат Claude без файлов/терминала этот сценарий не выполняет.
2. Если клиент уже был открыт, начать новую сессию, чтобы он обнаружил
   `.claude/skills`. Разрешить работу с этим локальным каталогом и запуск
   локального Chromium.
3. Отправить приведённый ниже prompt целиком.
4. Сохранить transcript с фактической версией клиента/моделью. Передать обратно
   путь к каталогу и transcript. Секреты/полные environment dumps не нужны.

## Prompt для обоих клиентов

> Проверь Testence на установленном wheel из `candidate.json`. Прочитай
> установленные проектные skills `testence-plan`, `testence-author`,
> `testence-triage`, `testence-repair` и необходимые references. Используй
> `.venv/Scripts/testence.exe` и `.venv/Scripts/python.exe`; не редактируй
> установленный пакет и не обновляй dependencies.
>
> Создай каталог `client-evidence` и записывай команды, exit codes и пути outputs.
> Выполни `doctor --json`, `agent verify --project . --client <твой-клиент> --json`,
> затем `demo run --project demo --json`. Самостоятельно разберись в созданном
> проекте и трёх запусках demo. Объясни, какой результат подтверждён независимым
> состоянием, и почему одного UI-success недостаточно.
>
> Пройди plan → author → run → triage → proposal → review:
> сформулируй дополнительный полезный сценарий для локального demo,
> сохрани PlanSpec v2 с requirement claim и независимым oracle, проверь plan,
> напиши привязанный pytest-тест и покажи healthy green → ожидаемый defect red →
> harmless-change green. Используй только synthetic demo и reversible local data.
> Отдельные запуски должны иметь разные run IDs. Не ослабляй claims ради green.
>
> Для реального failure pack заполни verdict v2 на основании evidence,
> проверь его `verdict validate` и сохрани через `verdict submit` с точными
> `--pack`/`--plan`. Пути и digests возьми из созданных артефактов.
> Если допустим безопасный repair, подготовь видимый diff и proposal,
> выполни необходимые controls и `repair validate`. Если evidence показывает
> product bug или оснований для repair нет — явно откажись от изменения теста,
> укажи reason и review outcome; не выдумывай proposal ради галочки.
>
> Запиши `client-evidence/result.md`: source SHA/wheel hash, фактический client/model,
> прочитанные skills, команды и exit codes, ссылки на plan/test/run/pack/verdict,
> решение о repair, возникшие затруднения, ручные подсказки и оставшиеся gaps.
> Не объявляй R1 accepted и не заполняй независимые human-review receipts.

`<твой-клиент>` заменить на `claude` или `codex` перед отправкой. Если какое-либо
действие не удаётся, оставить точную ошибку и продолжить независимые проверки;
не исправлять библиотеку внутри consumer environment.

## Как принимается результат

Исполнитель проверяет hashes и оба полных workflow, валидирует plans/verdicts,
сопоставляет control outcomes и фиксирует реальные ограничения. Тест, который
обходит oracle, успешная установка skills без их применения, один только triage
или просмотр этого чата не закрывают полный agent-client gate.
