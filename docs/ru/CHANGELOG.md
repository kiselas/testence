# История изменений

Проект находится на стадии pre-alpha. До первого tagged release значимые изменения
группируются в `Unreleased`; совместимость не гарантируется.

## Unreleased

### Сентябрьский аудит перед релизом

- Добавлена опциональная визуальная регрессия с SHA-256 эталона, явным viewport,
  исходным/текущим/diff-кадрами в пакете и inconclusive при недоступных доказательствах.
  Клиентская эмуляция из wheel выполняется в Linux/Windows CI.
- Skill-pack 0.1.2 описывает автономное визуальное доказательство и границы эмуляции;
  healing больше не заменяет селекторы состояния простым адресом элемента. См.
  [результаты визуальных и клиентских испытаний](../audits/2026-09-13/visual-client/README.md).

- Добавлена привязка проверки видимости к assertion/claim IDs с результатами
  verified/violated/inconclusive и проверками недоступного браузера.
- Добавлены закреплённые AdminLTE/Tabler, негативные и безвредные контроли, замеры,
  общие инструкции агентам и визуальное исследование в skill-pack 0.1.1.
- Свободный CDP-порт `0` сохраняется при загрузке настроек и создании движка.
- Исправлены временные ошибки удаления транзакций Windows и завершение worker в crash-тесте.
- Ошибки corpus теперь возвращают ненулевой exit code; добавлены отдельные каталоги
  результатов и корректное ожидание исчезновения всех placeholders. См.
  [аудит и оставшуюся приёмку](../audits/2026-09-13/README.md).

### Добавлено

- Детерминированное исполнение Playwright-over-CDP за протоколом engine.
- Pytest DSL с намерением, exact-by-default assertions и fingerprints элементов.
- Append-only evidence ledger `testence/1`, ограниченные evidence packs и
  single-file HTML report.
- Расширяемые стратегии аутентификации и API client с общей browser session для
  UI-to-API oracles.
- Проверяемые предложения locator healing; упавший шаг никогда не получает silent
  rebind.
- Process-sharded evidence для необязательного `pytest-xdist`.
- Экспортёры Allure и CTRF, рендерящиеся из ledger.
- Синтетические mutation corpora для проверки false green, false red и качества healing.
- Reference compute kernels за версионированным optional-native ABI.
- Версионированные контракты PlanSpec и verdict с трассировкой claims через pytest,
  ledger, evidence packs и отчёты.
- Версионированный набор Agent Skills для `plan`, `author`, `triage` и `repair` с
  метаданными Codex и безопасным контрактом cross-client обновления.
- Профиль production-built React и multi-process performance-budget gate для navigation,
  controlled inputs и mutation synchronization.
- Отдельный shared-browser CDP профиль и budget для повторных agent-authoring runs.
- Opt-in warm modes для `bench` и `watch`, переиспользующие Python и pytest с reload
  проектных модулей между изолированными sessions.

### Изменено

- Text assertions по умолчанию используют exact matching; containment задаётся явно.
- Evidence metrics считают latency листовых шагов и не дублируют вложенные actions.
- Метрики interaction flake используют identity теста и digest кода.
- Network capture записывает aborted requests как first-class evidence.
- SPA readiness распознаёт non-text controls внутри асинхронно mounted roots вместо
  пятисекундного ожидания только `innerText`.
- Signalled save oracles синхронизируются по scoped mutation response вместо глобального
  `networkidle`; fingerprint capture использует один non-waiting browser evaluation.
- Form fill получил opt-in `fast=True`, сохраняющий input events и пропускающий уже
  доказанные предыдущим readiness gate actionability checks.
- Network capture waits отдают управление event loop квантами по 10 ms; на поддерживаемом
  real-React профиле p95 наблюдения быстрого POST response снизился с 63 до 16 ms.
- CDP-attached runs больше не закрывают context launcher'а. На поддерживаемом профиле
  p50 fresh run снизился с 3,21 s при launch-per-run до 2,02 s с shared browser.
- Warm pytest sessions на каждой итерации сбрасывают run ids, fixtures, auth и evidence
  writers, сохраняя одно Playwright/CDP engine connection. На поддерживаемом
  React-профиле p50 bootstrap снизился с 2,81 до 0,45 s, а p50 всего run — с 3,45 до
  1,13 s.

### Безопасность и гигиена релиза

- До инициализации репозитория удалены локальные credentials, browser profiles,
  сгенерированные run data и application-specific черновые материалы.
- Публичные примеры используют только зарезервированные example domains и синтетические
  приложения.

## Примечания к benchmark

Сохранённые файлы результатов E1, I3 и kernels — воспроизводимые snapshots, а не
продуктовые заявления. Hardware, browser, runtime и target latency существенно влияют
на числа; новые релизы должны публиковать точную команду и окружение вместе с любым
результатом.
React gate запускается командой `python bench/react_latency.py --repeats 5 --check`;
его широкие ceilings ловят timeout-shaped регрессии, но не являются cross-host speed claim.
