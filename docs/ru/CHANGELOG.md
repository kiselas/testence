# История изменений

Проект готовится как alpha-кандидат. До первого tagged release значимые изменения
группируются в `Unreleased`; совместимость не гарантируется.

## Unreleased

### Исправлено

- Evidence: перехват сети с более чем одним запросом очищался только текстовыми
  правилами, поэтому поле с паролем в теле запроса могло попасть в `network.jsonl`
  открытым текстом. JSON Lines теперь очищаются построчно.
- Жизненный цикл: неудачный старт браузера оставлял процесс драйвера Playwright
  запущенным, по одному на каждый упавший прогон. `start()` освобождает созданное.
- `switch_page()` не переустанавливал перехватчики, из-за чего для второй вкладки
  разделы сети и консоли в evidence pack оставались пустыми.
- `TESTENCE_DEBUG_PORT=0` показывал `127.0.0.1:0` в манифесте триажа. Движок резолвит
  реальный свободный порт, и к браузеру с местом падения снова можно подключиться.
- `.env`, `testence.json` и `testence.toml` читаются как UTF-8 с необязательной меткой
  порядка байтов: файл, сохранённый редактором Windows, больше не теряет первый ключ.
- Битый файл настроек сообщает имя файла и позицию вместо трассировки, а относительная
  навигация без `base_url` называет недостающую настройку.
- Пустой `TESTENCE_BROWSER_CHANNEL` сохраняет умолчание пакета вместо запуска без канала.
- Умолчательный селектор кнопки отправки формы логина находит и `<button>` без явного
  `type`, который по спецификации HTML отправляет форму.

### Изменено

- `testence init` записывает readiness-маппинг для сгенерированного плана, поэтому
  `plan prepare` в только что инициализированном проекте отвечает `ready`.
- `testence doctor` запускает настроенный канал браузера вместо проверки пути к
  bundled-исполняемому файлу и сообщает команду, которая чинит ошибку. Проверка
  называется `browser`.
- `testence --version` печатает установленную версию.
- Ссылки в README абсолютные и работают на PyPI, а quick start идёт по пути
  `pip install testence`, которому не нужен клон репозитория.
- CI запускает и линтит `examples/`, на который ссылается опубликованный quick start.

- `TESTENCE_BROWSER_CHANNEL` теперь задаёт канал и для `Settings` и движков, создаваемых
  напрямую, минуя `Settings.load`: машина, на которой не стартует bundled Chromium,
  может гонять браузерные тесты на `msedge` или `chromium-headless-shell`; явные
  аргументы и умолчания CI не меняются.

## 0.1.0a1 — release candidate

- Контекст iframe теперь одинаково применяется к locator actions, JavaScript evaluation
  и predicate waits; разрыв был обнаружен на preview сайта NextDish.
- Ручной PyPI workflow больше не подставляет dispatch inputs напрямую в shell, а перед
  публикацией проверяет имя и версию внутри wheel и sdist.

### Сентябрьский аудит перед релизом

- Добавлена команда `testence plan prepare`: она до открытия браузера проверяет по
  каждому сценарию возможности engine, обязательные oracle-адаптеры, credentials,
  файлы и HTTP/JSON-фикстуры. Явные argv-рецепты могут подготовить зависимости,
  изолированный target или синтетический seed и всегда перепроверяются. Skill-pack
  0.1.4 требует этот gate перед discovery.
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
