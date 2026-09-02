# ADR-0017: Event-driven готовность SPA и синхронизация mutations

Статус: accepted (2026-09-02, latency probe реализован)

## Контекст

React и похожие SPA ломают два универсальных shortcut готовности. Страница может быть
готова к работе, когда её root содержит только input, icon или canvas и поэтому не имеет
`innerText`. Одновременно polling, analytics и streams могут навсегда не дать сети стать
idle. Ожидание текста или глобальной тишины сети превращает успешные действия в latency
размером с timeout.

Same-host probe `bench/spa_latency.py` моделирует асинхронный mount root, controlled input
и API polling каждые 100 ms. До решения navigation тратила 5 048,67 ms на текст, который
никогда не появится; `Actions.fill` занимал 11,10 ms p50 из-за двух дополнительных browser
round-trips для fingerprint; fallback `networkidle` на 750 ms расходовал почти весь budget.

Дополняющий gate `bench/react_latency.py` работает с production bundle реального React
SUT через публичный DSL. Он разделяет fresh-process bootstrap, navigation, controlled-input
steps, ожидание точного POST response, видимый React commit и полный mutation round trip.
Минимум gate — три свежих процесса; документированный maintainer run использует пять.

## Рассмотренные варианты

1. Глобально уменьшить все timeout.
2. Присваивать `element.value` напрямую и обходить Playwright ради скорости input.
3. Сохранить `networkidle` с project-specific budgets.
4. Ждать локальное семантическое состояние и точный mutation response, отдельно
   оптимизируя фоновый сбор evidence.

## Решение

Выбран вариант 4.

- SPA readiness принимает текст или осмысленный non-text UI внутри известного `#root`,
  `#app`, React root либо body fallback. Это best-effort ожидание с budget 2 s; точная
  готовность следующего элемента остаётся за Playwright auto-waiting.
- `save_and_verify(expect_request=...)` ставит network mark до click и ждёт matching
  completed response после mark, затем даёт локальному UI два animation frames на commit.
  Глобальная тишина сети не нужна. `networkidle` остаётся только compatibility fallback
  без mutation signal и перед сбором bounded failure pack.
- Fingerprints зелёного запуска используют один non-waiting `evaluate_all` snapshot
  вместо `count()` и последующего auto-waiting evaluate.
- Обычный fill остаётся event-correct `locator.fill()` Playwright. `fast=True` включает
  его `force` path только после явного readiness proof; прямой DOM assignment отклонён,
  потому что может обойти состояние controlled input и события приложения.
- Capture-buffer waits отдают управление event loop Playwright квантами по 10 ms. Это
  сохраняет ответы, завершившиеся до начала wait, но убирает 50-ms observation floor,
  заметный на быстрых API.
- CI проверяет широкие абсолютные ceilings на распределениях из fresh processes. Это
  tripwires регрессий, а не сравнение машин; одиночных millisecond assertions в контракте
  нет.

## Последствия

На Windows 11, Python 3.12.13 и Playwright 1.62.0 тот же probe измерил navigation в
114,29 ms (быстрее в 44 раза), `Actions.fill` в 6,97 ms p50 (ниже на 37%), а scoped
mutation response — в 116,39 ms против 737,62 ms polling-hostile idle wait. Это same-host
diagnostic measurements, а не публичное cross-machine заявление.

На реальном React SUT уменьшение capture-buffer quantum с 50 до 10 ms изменило p95
ожидания POST response с 63 до 16 ms, а p50 полного mutation round trip — со 127,5 до
84,0 ms. В финальном snapshot launch на пяти процессах p50 mutation составила 81,9 ms,
а публичный controlled-fill step показал 15,2 ms p50 в обычном path и 14,0 ms с
`fast=True`; все поддерживаемые budgets пройдены. Raw results и
точное окружение находятся в `bench/results/react_latency.json`.

Actionability checks по умолчанию сохранены. Приложения без объявленного request signal
по-прежнему используют медленный fallback. Wait ledger хранит operation и время, поэтому
будущая регрессия видна отдельно от общей длительности теста.

## Tripwire

Пересмотреть решение, если SPA readiness возвращается до первого actionable state более
чем в 1% golden runs, response-scoped save пропускает отправленную mutation хотя бы в
одном accepted test или steady-state `Actions.fill` p95 превышает 20 ms на синтетическом
probe без работы приложения. Real-React gate также должен оставаться зелёным минимум на
трёх fresh processes. Fast path удаляется, если меняет поведение controlled input, даже
при меньшей latency.
