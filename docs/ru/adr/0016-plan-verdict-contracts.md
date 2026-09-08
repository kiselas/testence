# ADR-0016: PlanSpec и verdict как версионированные proof-контракты

Статус: заменено ADR-0019 (контракт `/1` остаётся compatibility input)

## Контекст

Agent-first workflow должен сохранять смысл требования между разными clients и
запусками. Prose-план удобен человеку, но не позволяет pytest проверить claim coverage.
Одного marker в тесте недостаточно: он не хранит продуктовый контекст и сценарии.
Неструктурированный ответ triage-агента невозможно безопасно связать с конкретным
PlanSpec, тестом и evidence pack.

При этом execution path согласно ADR-0006 должен оставаться provider-neutral и не
зависеть от LLM или SDK JSON Schema.

## Рассмотренные варианты

1. YAML front matter и произвольные Markdown-разделы.
2. Отдельные JSON/YAML-файлы без человеческого документа.
3. Markdown с одним fenced JSON-блоком и опциональный standalone JSON.
4. Хранить claims только в Python decorators/markers.
5. Принимать свободный текст verdict и извлекать структуру после ответа модели.

## Решение

Выбран вариант 3 для PlanSpec и строгий JSON для verdict.

- PlanSpec содержит ровно один блок `testence-planspec` со схемой
  `testence/planspec/1`; Markdown вокруг него остаётся человеческим контекстом.
- Публичная JSON Schema draft 2020-12 поставляется в wheel. Runtime-валидатор использует
  stdlib и дополнительно проверяет межобъектные инварианты: уникальность ID, coverage
  обязательных claims и ссылки сценариев.
- Pytest marker `testence(plan=..., claims=[...])` связывает тест с repository-relative
  PlanSpec. Collection отклоняет путь наружу и неизвестные claims.
- Evidence writer добавляет `plan` и `claims` ко всем событиям связанного теста. Те же
  поля попадают в pack index, exporter model и HTML report.
- Failure pack создаёт `verdict.template.json`. Агент сохраняет заполненный
  `testence/verdict/1` как `verdict.json`; validator требует точного совпадения plan,
  test и полного набора claims, а также существования evidence-файлов внутри pack.
- Воздержание является данными: `verdict: null` допустим только с непустым `blocked_on`.
  Runner создаёт доказательства и template, но не выносит модельный verdict.

## Последствия

- Claim ID становится стабильным join key между требованием, кодом, ledger, pack,
  report и решением агента.
- Контракт одинаков для Codex/ChatGPT, Claude Code, OpenCode, CLI и будущего MCP.
- JSON внутри Markdown чуть многословнее YAML, зато не требует нового runtime dependency,
  однозначно парсится и совпадает с transport-форматом инструментов.
- Изменение обязательных полей или смыслов требует новой версии schema; новые optional
  ledger fields остаются совместимыми с `testence/1`.
- Сохранение/подпись verdict и policy approvals остаются отдельным следующим слоем.

## Tripwire

Пересмотреть форму PlanSpec, если на не менее чем 30 golden-path задачах более 10%
планов нельзя выразить без дублирования критичного контекста в prose или median-время
исправления schema errors превышает две минуты. Пересмотреть marker binding, если в
корпусе из 1 000 связанных тестовых запусков хотя бы один accepted test теряет plan или
claim в ledger, pack либо report.
