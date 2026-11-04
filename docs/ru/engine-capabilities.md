# Возможности engine и строгие действия

Проверьте выбранный backend до collection:

```bash
testence capabilities --project . --json
```

Команда выдаёт `testence/engine-capabilities/1`. Scenario в PlanSpec может потребовать
capabilities, например `browser.dom`, `browser.frames` или `browser.files`; если backend
не объявляет их все, collection завершается ошибкой до исполнения.

Playwright backend R1 объявляет lifecycle, session, navigation, DOM и open shadow DOM,
network/WebSocket, screenshot, accessibility, JavaScript, keyboard/focus/scroll,
frames, popups и вкладки, upload/download, dialogs, поддельные таймеры
(`browser.clock`, `ex.clock`), эмуляция контекста (`browser.emulation`), записываемая подмена запросов
(`browser.network_mock`, `ex.route`), записываемый шлюз WebSocket
(`browser.websocket_mock`, `ex.ws_gate`) и `browser.native` (`ex.native`). DSL использует strict locators: несколько
совпадений дают failure, пока автор явно не укажет `Target(..., nth=N)`. `fast=True` —
явное ослабление actionability. Оно записывается в `step.start` и переводит иначе
verified attempt в `unverified` для review.

`ex.open(route, intent=None)` (`browser.navigation`) открывает маршрут самым быстрым
корректным способом: если страница уже показывает приложение на origin `base_url` (его
корень что-то отрисовал), маршрут передаётся собственному роутеру приложения, как при
клике по внутренней ссылке; иначе (первая навигация, другой origin, маршрут вне
`base_url`, несмонтированное приложение) — загрузка документа. Возвращает `navigate`
или `goto`, а `step.end` шага записывает это в поле `navigation`. Клиентская навигация
сохраняет состояние смонтированных компонентов: кейс про первую загрузку использует
`ex.goto`.

После загрузки документа движок проверяет, отрисовало ли приложение хоть что-то
(`wait_until_rendered`). Под DSL проверка ждёт следующего шага: шаг с target её
пропускает, потому что ожидание собственного элемента — более сильный сигнал готовности
(`wait_until_rendered(skipped)` в журнале ожиданий); шаг без target (проверка URL,
скриншот, oracle, `ex.native`) сначала выполняет её; проверка, которая осталась к концу
теста, выполняется тогда. Движок, вызванный напрямую без DSL, проверяет сразу после
`goto`, как раньше.

`ex.reset_storage(keys, intent=None, *, session=False)` (`session`) удаляет названные
ключи `localStorage` (или `sessionStorage`) и возвращает, сколько из них было задано;
при `page_reuse: module` очищает то, что предыдущий тест оставил на общей вкладке.

`ex.expect_settled(target, intent=None, *, timeout_ms=None)` (`browser.dom`) ждёт,
пока `getBoundingClientRect` цели не совпадёт в двух кадрах `requestAnimationFrame`
подряд и прямоугольник не окажется целиком внутри viewport. Применяйте перед замером
всего, что выезжает с анимацией: выдвижная панель видима с первого кадра, поэтому её
ширина после `expect_visible` — ширина переходного состояния. Кадры считаются в
странице за один round trip; ожидание — запись `expect_settled` в журнале ожиданий.
Элемент, который не останавливается или остаётся вне viewport, падает как assertion с
последним прямоугольником в сообщении.

Внутри `with ex.frame(...)` locator actions, `eval_js` и `wait_for_predicate_js`
используют один активный iframe. После выхода восстанавливается предыдущий page или
вложенный frame scope. Операции с session и network остаются page-level.

Adapter может реализовать `CapabilityProvider`, `LifecycleEngine` и `EvidenceEngine`
без импорта Playwright. Platform-neutral fake проверяет lifecycle, evidence и export,
а browser action возвращает `UnsupportedCapability` с operation, required capability
и available set. Старые custom engines сохраняют прежний composite interface как путь
миграции, но не считаются conformant до объявления capabilities.

## Прямой Playwright: `ex.native`

Если DSL не выражает взаимодействие, `ex.native` передаёт `Page` Playwright внутри одного
записанного шага:

```python
with ex.native("расписаться на панели подписи") as page:
    box = page.locator("canvas#signature").bounding_box()
    page.mouse.move(box["x"] + 10, box["y"] + 10)
    page.mouse.down()
    page.mouse.move(box["x"] + 120, box["y"] + 40, steps=8)
    page.mouse.up()
ex.expect_enabled(Target("role", "button", name="Submit"))
```

Шаг несёт intent, длительность и возможное падение, как любой другой, а событие ledger
`native.used` отмечает, что действия внутри не записывались по одному. Падение внутри
даёт обычный pack; healing не предлагается, потому что цель не проходила через DSL.
Блок работает в странице, а не в активном `ex.frame`; для фреймов внутри используйте
`page.frame_locator(...)`. Движок без capability `browser.native` отказывает до запуска
блока ([ADR-0027](adr/0027-native-escape-hatch.md)).
