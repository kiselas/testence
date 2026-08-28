# ADR-0003: Собственный версионированный run.jsonl как источник истины

Статус: accepted (2026-08-25)

## Контекст

Центральный артефакт фреймворка — доказательства, оставшиеся после запуска. Агент
читает их в рамках token budget и выносит verdict, человек читает отрендеренный отчёт,
метрики агрегируются по ним. Артефакт должен переживать crash — именно тогда он нужнее
всего, быть пригодным для diff и стабильным между версиями.

## Сравнение вариантов

| | Собственный JSONL `testence/1` | Playwright trace.zip | Allure results как primary |
|---|---|---|---|
| Стабильность schema | наша versioned envelope | private и может меняться | стабильна, но имеет форму report |
| Читаемость агентом | line-per-event и first-class token budgets | нужна распаковка, size без границ | XML/JSON на test, недостаточная granularity |
| Crash safety | append-only и fsync на event | пишется при закрытии context | пишется в конце |
| Intents/fingerprints/oracle diffs | наши поля | нет | неудобно через labels |
| Human time travel | наш более простой HTML v0 | отличный Trace Viewer | Allure UI |
| Стоимость | мы владеем schema | бесплатно | бесплатно |

## Решение

Владеть `run.jsonl` со схемой `testence/1`: envelope
`{v, run, seq, ts, kind, test?}`, payload по kind, append-only, fsync на событие,
UTF-8 и `\n` на всех платформах. События green path компактны; падения прикладывают
каталог evidence pack с budget каждой секции. Нормативный документ:
[`evidence-schema.md`](../evidence-schema.md).

Playwright trace.zip может записываться дополнительно как бесплатный time-travel viewer
для людей, но никогда не парсится как data source. Allure results генерируются из
run.jsonl для TestOps и не являются источником истины.

## Последствия

- Один источник истины и три представления — agent pack, HTML report и Allure export —
  не могут расходиться.
- Мы оплачиваем schema evolution: поля `testence/1` только добавляются; breaking change
  повышает version, parser явно отклоняет чужую.
- Каждый запуск является benchmark: timings находятся в ledger, `testence metrics`
  агрегирует их.

## Tripwire

Если Playwright поставит стабильный документированный trace format, нужно сравнить
triage verdicts из нашего pack и их trace на failure corpus по `verdict_accuracy` и
`tokens_per_triage`. Проигрыш по обоим показателям означает миграцию с сохранением
envelope как adapter.
