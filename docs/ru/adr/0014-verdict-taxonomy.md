# ADR-0014: Verdict для изменения поведения и явное abstention

Статус: accepted (2026-08-27)

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
- `behaviour_change`: продукт согласован, но ведёт себя не так, как ожидает тест;
- `ui_change`: изменился address элемента или presentation contract;
- `flaky_timing`: падение объясняется timing или nondeterminism;
- `environment`: причина в availability target, configuration или version mismatch.

`blocked_on` при необходимости называет недостающий факт для завершения provisional
verdict, обычно актуальную specification или change record. Судья не должен выводить
намерение только из отсутствия ошибок.

Grouping failures отделён от classification verdict и остаётся будущей работой.

## Последствия

Evidence packs самодостаточны и несут доступную taxonomy. Добавление verdict меняет
accuracy baselines, поэтому revisions benchmark публикуются вместе со scores.

## Tripwire

Синтетический corpus обязан содержать controls согласованного изменения и согласованно
ошибочные defects. Если recall `behaviour_change` растёт за счёт ошибочной
классификации реальных defects, prompt должен требовать positive cross-layer evidence
и чаще использовать `blocked_on`.
