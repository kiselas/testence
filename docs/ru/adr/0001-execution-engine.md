# ADR-0001: Playwright-over-CDP как engine за фасадом

Статус: accepted (2026-08-25)

## Контекст

Runner должен управлять настоящим Chrome через DevTools Protocol в headed-режиме с
возможностью подключения triage agents, выполнять шаги за миллисекунды и выдерживать
React SPA, чьи timing-проблемы многократно мешали ручным агентным запускам: timeout
скриншота 30 секунд, «подождать 3–5 секунд и повторить», canvas zoom, съедающий клики.
Именно слой ожиданий рождает e2e flakiness: около 45% flaky web tests связаны с
async wait.

## Сравнение вариантов

| | Playwright library | Puppeteer | raw CDP client | интерактивный MCP |
|---|---|---|---|---|
| Transport | CDP для Chromium | CDP | CDP | CDP |
| Auto-wait/actionability | встроенный зрелый | частичный; нет checks для всех ops | отсутствует, пишем сами | retries агента означают LLM round-trips |
| Семантические locators | role/label/text | ограниченно | нет | через accessibility snapshot |
| ARIA snapshots | `locator.aria_snapshot()` | вручную через CDP | вручную через CDP | да, но с token cost на вызов |
| Подключение к Chrome | `connect_over_cdp` | `connect` | native | `--cdp-endpoint` |
| Network/console capture | events API | events API | вручную | ограниченно |
| Скорость шага | около миллисекунд | около миллисекунд | около миллисекунд | 10–40 с с LLM в loop, около 114K tokens/test |
| Языки | Py/TS/Java/.NET | TS, неофициальный Py port | любой | н/д |
| Лицензия | Apache-2.0 | Apache-2.0 | — | Apache-2.0 |

Ключевой факт: Playwright, Puppeteer и raw client используют один протокол — до
браузера доходит тот же `Input.dispatchMouseEvent`. Выбор определяет слой ожидания и
локаторов, но не transport speed.

## Решение

Использовать synchronous Playwright library поверх CDP **за фасадом**. Только
`testence/engine/` может импортировать её; `Engine` protocol и `Target` dataclass
образуют публичную границу. Raw CDP остаётся доступен через `new_cdp_session` для
сбора доказательств. Интерактивные MCP применяются для triage живого браузера,
оставленного runner, но никогда не как runner.

Отклонены: raw CDP из-за повторной реализации actionability waits без выигрыша
transport; Puppeteer из-за того же протокола, более слабых waits/locators и Node lock;
MCP-as-runner из-за LLM cost и недетерминизма CI.

## Последствия

- Auto-wait устраняет «sleep and retry» из ручных запусков; DSL никогда не делает sleep.
- Возможный CDP-native путь, подобный Stagehand v3, остаётся оптимизацией за фасадом, а
  не переписыванием.
- Верхние слои тестируются через fake Engine.

## Tripwire

`step_latency_ms` p95 выше 500 мс по вине driver, а не приложения, либо не менее двух
flakes в месяц, трассируемых до engine layer, требуют сравнительного эксперимента
CDP-native executor на golden suite до решения о переписывании.
