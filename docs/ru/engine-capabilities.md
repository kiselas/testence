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
frames, popups, upload/download и dialogs. DSL использует strict locators: несколько
совпадений дают failure, пока автор явно не укажет `Target(..., nth=N)`. `fast=True` —
явное ослабление actionability. Оно записывается в `step.start` и переводит иначе
verified attempt в `unverified` для review.

Внутри `with ex.frame(...)` locator actions, `eval_js` и `wait_for_predicate_js`
используют один активный iframe. После выхода восстанавливается предыдущий page или
вложенный frame scope. Операции с session и network остаются page-level.

Adapter может реализовать `CapabilityProvider`, `LifecycleEngine` и `EvidenceEngine`
без импорта Playwright. Platform-neutral fake проверяет lifecycle, evidence и export,
а browser action возвращает `UnsupportedCapability` с operation, required capability
и available set. Старые custom engines сохраняют прежний composite interface как путь
миграции, но не считаются conformant до объявления capabilities.
