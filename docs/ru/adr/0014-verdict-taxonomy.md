# ADR-0014: Verdict для изменения поведения, ошибки теста и явное abstention

Статус: accepted (добавлен PlanSpec-aware `test_bug`, 2026-08-28)

## Контекст

Не прошедшее expectation не всегда означает product defect. UI, API и network могут
согласованно показывать новое поведение, пока тест кодирует старую specification.
Называть это `real_bug` неверно; `ui_change` тоже не подходит, если addressing
элемента не изменился.

Evidence не может доказать намеренность согласованного изменения, поскольку
specification может находиться вне pack. Контракту нужны и отдельное наблюдение, и
канал abstention.

## Решение

Набор verdict:

- `real_bug`: наблюдаемые слои расходятся или запрошенная операция не работает;
- `test_bug`: продукт и актуальный PlanSpec согласованы, но реализация теста
  противоречит им;
- `behaviour_change`: продукт согласован, но отличается от актуального PlanSpec или
  ожидания теста;
- `ui_change`: изменился address элемента или presentation contract;
- `flaky_timing`: падение объясняется timing или nondeterminism;
- `environment`: причина в availability target, configuration или version mismatch.

`test_bug` требует положительного evidence, что хотя бы один claim PlanSpec прошёл;
просто менять assertion до зелёного результата недостаточно. `blocked_on` при
необходимости называет недостающий факт для завершения provisional verdict, обычно
актуальную specification или change record. Судья не должен выводить намерение только
из отсутствия ошибок.

Grouping failures отделён от classification verdict и остаётся будущей работой.

## Последствия

Evidence packs самодостаточны и несут доступную taxonomy. Добавление `test_bug` меняет
accuracy baselines, поэтому revisions benchmark публикуются вместе со scores и включают
хотя бы один control ошибки реализации теста.

## Tripwire

Синтетический corpus обязан содержать controls согласованного изменения, ошибки
реализации теста и согласованно ошибочные defects. Если recall `behaviour_change` или
`test_bug` растёт за счёт классификации реальных defects, prompt должен требовать
positive cross-layer и PlanSpec evidence и чаще использовать `blocked_on`.
