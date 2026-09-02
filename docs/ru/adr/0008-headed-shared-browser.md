# ADR-0008: Headed Chrome с открытым CDP port как общая основа

Статус: accepted (2026-09-02, lifecycle shared browser измерен)

## Контекст

Кто владеет браузером? Классический e2e запускает приватный, обычно headless, браузер
на один run и уничтожает его. Нашему triage loop при падении нужно обратное: страница
**в состоянии падения** является самым ценным доказательством, и агент или человек
должен иметь возможность подключиться после запуска.

## Сравнение вариантов

| | Headed Chrome, open CDP port | Headless, private runner | Fresh browser на test |
|---|---|---|---|
| Live triage после падения | attach через `--cdp-endpoint` или devtools MCP | невозможно, state уничтожен | невозможно |
| Переиспользование logged-in profile | да, `connect_over_cdp` | нет | нет |
| Наблюдение разработчиком | да, требование продукта | нет | нет |
| Скорость | примерно headless, E5 измерит | самая высокая | самая низкая |
| CI | через `xvfb-run` в Linux | native | native |

## Решение

- По умолчанию используется **headed** системный Chrome с `channel="chrome"`,
  запущенный с `--remote-debugging-port`, либо подключение к существующему через
  `--testence-cdp` с переиспользованием profile и cookies.
- При падении session **оставляет браузер живым**, а каждый evidence pack содержит
  `browser.json` с CDP endpoint и page URL — attach protocol для любого MCP/CDP
  client. Runner отключается, но не уничтожает место события.
- Context имеет scope session, page переиспользуется, capture buffers сбрасываются на
  test. Per-test contexts и parallel shards предусмотрены ID run/test во всех events.
- Ownership задаётся явно. Запущенный или persistent engine закрывает созданный им
  context; CDP-attached run берёт context launcher'а взаймы и отключает только свой
  Playwright client. На зелёном run он не закрывает logged-in context.
- CI использует тот же headed mode под `xvfb-run`. Live triage — локальная функция,
  CI failures разбираются по evidence packs; они обязаны быть достаточными по H3.

## Последствия

- Один browser обслуживает deterministic runner и interactive agent tools; в triage не
  требуется сначала воспроизводить сбой.
- Shared long-lived browser накапливает state; marker/cleanup discipline контракта
  SeedAdapter и reset taps на test ограничивают влияние.
- Windows работает headed напрямую, Linux CI использует стандартный слой xvfb.
- На production-built React профиле пять fresh процессов с launch-per-run показали
  3 208,11 ms p50. Пять процессов, подключённых к одному shared browser, показали
  2 022,56 ms p50 (ниже на 37%); bootstrap p50 снизился с 2 584,47 до 1 475,00 ms.
  Старт shared browser стоил 1 240,15 ms один раз, поэтому same-host профиль выходит
  в плюс со второго повторного run. Это diagnostics development loop, а не
  cross-machine claim.

## Tripwire

E5 измеряет headed против `--headless=new` на golden suite. Если headed добавляет
более 25% wall-clock в CI **и** за квартал ни одному CI failure не потребовался live
attach, CI может перейти на headless-new при сохранении headed локально. Любое
расхождение behavior между режимами фиксирует этот case в headed везде и сохраняется
как evidence.

Attached latency budget должен оставаться зелёным минимум на трёх fresh pytest
processes, а второй attach обязан сохранить context launcher'а. Если reuse экономит
менее 15% после пяти повторных runs на двух поддерживаемых hosts, рекомендация по
скорости снимается, но attach сохраняется для authentication и triage.
