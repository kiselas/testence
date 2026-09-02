# История изменений

Проект находится на стадии pre-alpha. До первого tagged release значимые изменения
группируются в `Unreleased`; совместимость не гарантируется.

## Unreleased

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

### Изменено

- Text assertions по умолчанию используют exact matching; containment задаётся явно.
- Evidence metrics считают latency листовых шагов и не дублируют вложенные actions.
- Метрики interaction flake используют identity теста и digest кода.
- Network capture записывает aborted requests как first-class evidence.

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
