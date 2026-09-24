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
(`browser.clock`, `ex.clock`), эмуляция контекста (`browser.emulation`) и `browser.native` (`ex.native`). DSL использует strict locators: несколько
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

## Прямой Playwright: `ex.native`

Если DSL не выражает взаимодействие, `ex.native` передаёт `Page` Playwright внутри одного
записанного шага:

```python
with ex.native("перетащить карточку в колонку Done") as page:
    page.drag_and_drop("[data-card=42]", "[data-column=done]")
ex.expect_text(Target("testid", "done-count"), "1")
```

Шаг несёт intent, длительность и возможное падение, как любой другой, а событие ledger
`native.used` отмечает, что действия внутри не записывались по одному. Падение внутри
даёт обычный pack; healing не предлагается, потому что цель не проходила через DSL.
Блок работает в странице, а не в активном `ex.frame`; для фреймов внутри используйте
`page.frame_locator(...)`. Движок без capability `browser.native` отказывает до запуска
блока ([ADR-0027](adr/0027-native-escape-hatch.md)).
