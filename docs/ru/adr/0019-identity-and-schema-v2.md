# ADR-0019: Стабильная identity и schema v2

Статус: принято (2026-09-06)

## Контекст

Schema `/1` использовала короткую подпись теста как operational key и получила новую
lifecycle-семантику без major migration. Из-за этого cases, parameter variants и retries
могли сливаться в отчётах. Plan, pack и verdict также не имели общей привязки к run/proof.

## Решение

Writers создают ledger `testence/2`, PlanSpec `testence/planspec/2`, Verdict
`testence/verdict/2`, evidence-pack `testence/evidence-pack/2` и pack-manifest
`testence/pack-manifest/2`.

Общая identity: `project_id`, `case_id`, `variant_id`, `run_id`, `attempt_id`,
`proof_id`; событие также содержит `event_id` в виде `<worker>:<seq>`. Pytest nodeid
остаётся source locator, display name — представлением. ID scenario из PlanSpec служит
явным логическим case ID. Fallback от source для непривязанного теста не обещает
стабильность после rename. Parameters записываются как канонические SHA-256 fingerprints,
поэтому raw credentials и бизнес-данные не попадают в artifacts.

Все readers вызывают один adapter `/1` до reconciliation. Он сохраняет additive unknown
fields, нормализует status spellings и помечает недостающий legacy proof как `unverified`,
не выдумывая успешную assertion. Неизвестные major versions отклоняются до export. Result
UUID использует run/case/variant/attempt, history identity — project/case/variant.

## Последствия

Retries остаются отдельными results, явный case ID переживает rename, а validator pack и
verdict отклоняет привязку к другому run/project. Schemas `/1` остаются в package для
migration и compatibility tests; новые документы используют только `/2`.
