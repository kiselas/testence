# ADR-0018: Тёплый pytest process для authoring loop

Статус: accepted (2026-09-02, opt-in и measured)

## Контекст

После переиспользования browser свежий attached React run всё ещё тратил около
1,5–1,8 секунды на bootstrap Python и pytest. Повторный вызов `pytest.main()` в одном
interpreter убирает эту стоимость, но без явного lifecycle он небезопасен: проектные
модули остаются в cache, globals plugins переживают run, run id привязан к process, а
wait summaries могут смешиваться между sessions.

## Решение

- `watch --warm` и `bench --warm` — только authoring modes. Они не запускают
  произвольные команды и принимают лишь прямые `pytest` или `python -m pytest`.
- Каждая итерация создаёт новую pytest session. Она заново создаёт fixtures, engine
  attachment, auth context, evidence writer и каталог run.
- Перед второй и последующими итерациями импортированные проектные модули из
  настроенных reload roots удаляются из `sys.modules`, затем import caches
  инвалидируются.
- Модули Testence и `__main__` защищены от выгрузки, чтобы control plane runner'а не
  смешивал старые объекты с заново импортированными globals фреймворка.
- Каждая session получает новый run id; pytest plugin очищает wait summary при старте
  session.
- Browser persistence остаётся отдельной CDP-задачей из ADR-0008.
- Warm process сохраняет один Playwright/CDP engine между pytest sessions. Key по
  settings browser connection заменяет engine при изменении конфигурации; остановка
  runner закрывает его. Auth, capture buffers и evidence остаются session- или
  test-scoped.

## Последствия

Fixture boundary показал, что повторное подключение Playwright/CDP engine было
крупнейшим оставшимся управляемым компонентом bootstrap. На поддерживаемом real-React
профиле p50 bootstrap свежего attached process составил 2 807,64 ms, а p50 steady warm
bootstrap — 447,18 ms: снижение на 84,1%. P50 всего run снизился с 3 446,94 до
1 132,93 ms (67,1%). Gate использует p50 и относительное снижение; при пяти samples
p95 равен одиночному максимуму и остаётся диагностикой, чтобы ambient host load не
создавал ложную регрессию.

Warm mode не обещает isolation на уровне process операционной системы. Process-global
state сторонних plugins или модулей вне reload roots может сохраниться. Поэтому release,
CI, corpus и финальная validation по-прежнему используют свежие processes.

## Tripwire

Отключить warm mode, если rerun видит устаревший сохранённый код, общий каталог run или
пережившую session-scoped fixture. Пересмотреть рекомендацию, если снижение bootstrap
меньше 15% на пяти runs на двух репрезентативных hosts. Любое расхождение correctness
между warm и fresh modes исключает warm mode из рекомендуемого authoring path.
Отключить сохранение engine, если restarted browser или изменение configuration может
оставить stale connection, либо если warm и fresh modes расходятся по auth/capture state.
