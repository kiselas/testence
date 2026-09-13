# Записи архитектурных решений

Каждое значимое решение фиксируется здесь вместе с действительно рассмотренными
альтернативами и **tripwire** — измеримым условием пересмотра. Решение без tripwire —
убеждение, а не инженерное решение.

Статусы: `accepted` · `proposed (experiment pending)` ·
`superseded by ADR-XXXX`.

| # | Решение | Статус |
|---|---|---|
| [0001](0001-execution-engine.md) | Playwright-over-CDP как engine за фасадом | accepted |
| [0002](0002-core-language.md) | Python для ядра фреймворка | accepted (E1 measured) |
| [0003](0003-evidence-format.md) | Собственный версионированный run.jsonl как источник истины | accepted |
| [0004](0004-dom-representation.md) | ARIA snapshot как DOM-формат доказательств | proposed (E2 pending) |
| [0005](0005-html-report.md) | Автономный single-file HTML report | accepted |
| [0006](0006-no-llm-in-runner.md) | Без LLM в execution path; provider-neutral contracts | accepted |
| [0007](0007-licensing-and-dependencies.md) | Apache-2.0 и только permissive dependencies | accepted |
| [0008](0008-headed-shared-browser.md) | Headed Chrome с открытым CDP port как общая основа | accepted |
| [0009](0009-kernel-boundary.md) | Граница compute kernels для будущих native/Rust backends | accepted (seam only) |
| [0010](0010-modular-authentication.md) | Модульная auth, form login по умолчанию, config-driven targets | accepted |
| [0011](0011-heal-as-proposal.md) | Self-healing как проверяемое предложение, но не runtime rebind | accepted (measured on corpus) |
| [0012](0012-parallel-execution.md) | Параллельное исполнение process shards с безопасными evidence и seeding | accepted |
| [0013](0013-reporting-as-export.md) | Reporting integrations как exporters из ledger | accepted (seam implemented) |
| [0014](0014-verdict-taxonomy.md) | Verdict для изменения поведения и ошибки теста; `blocked_on` для abstention | accepted |
| [0015](0015-agent-native-interface.md) | Переносимый agent control plane над детерминированным runner | proposed (golden path pending) |
| [0016](0016-plan-verdict-contracts.md) | PlanSpec и verdict как версионированные proof-контракты | заменено 0019 |
| [0017](0017-event-driven-spa-latency.md) | Event-driven SPA readiness, mutation waits и input fast path | accepted (measured) |
| [0018](0018-warm-authoring-runner.md) | Тёплый pytest process для authoring loop | accepted (measured, opt-in) |
| [0019](0019-identity-and-schema-v2.md) | Стабильная identity и миграция schema v2 | accepted |
| [0020](0020-application-cli-contract.md) | Явный onboarding/submission CLI с manifests | accepted |
| [0021](0021-isolated-runtime-ownership.md) | Изоляция state по тестам и явное владение browser | accepted |
| [0022](0022-engine-capability-negotiation.md) | Версионированные capabilities и strict action preflight | accepted |

| [0023](0023-visual-baseline-proof.md) | Визуальный контракт с фиксированным эталоном и клиентская эмуляция | implemented (engineering) |

Формат: Контекст → Рассмотренные варианты → Решение → Последствия → Tripwire.
Имена метрик определяются рядом с их реализацией и benchmark-документацией.
