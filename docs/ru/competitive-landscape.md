# Конкурентный ландшафт

Снимок состояния: 2026-08-28. Обзор опирается на документацию продуктов, а не на
vendor benchmarks или маркетинговые заявления о скорости.

## Структура рынка

Рынок разделяется на три группы:

1. test runners с агентным планированием, генерацией и исправлением;
2. управляемые AI-native платформы тестирования;
3. SDK браузерных агентов, которые можно встроить в тестовую систему, но которые сами
   не являются полноценными test runners.

Testence находится на границе первой и третьей групп, но предлагает более точную
категорию: **agent-native UI verification**. Coding agent является основным оператором,
а Testence предоставляет под ним переносимый детерминированный контракт исполнения и
доказательств. Сейчас этот агентный цикл всё ещё является проектным контрактом, а не
законченным пользовательским workflow.

## Прямые конкуренты

| Продукт | Модель | Сильнейшие возможности | Вывод для Testence |
|---|---|---|---|
| [Virtuoso Touchstone](https://www.virtuosoqa.com/) | Коммерческий enterprise assurance workflow | Требования и документы превращаются в reviewable diffs и трассируемые тесты; исполнение заявлено детерминированным, изменения не публикуются без одобрения, решения оставляют evidence | Самый близкий конкурент по новой trust/evidence формулировке. Testence должен доказывать преимущество открытостью, local-first владением, same-session oracles и публичным correctness corpus |
| [Leapwork Play](https://leapwork.com/leapwork-play/) | Коммерческая agentic continuous-validation платформа | Планирование и генерация из кода/требований, deterministic TypeScript/Playwright, governance, reporting, approvals и self-healing | Формула agentic authoring + deterministic execution уже стала enterprise baseline; открытые артефакты и переносимость должны быть измеримыми отличиями Testence |
| [Functionize Studio](https://www.functionize.com/) | Коммерческий автономный testing agent | Plain-language authoring, root-cause analysis, healing и proprietary generative-intent/deterministic-core архитектура | Конкурирует той же границей reasoning/execution, но с hosted knowledge layer; Testence должен выигрывать auditability без обучения закрытой модели на каждом run |
| [Applitools Autonomous](https://applitools.com/platform/autonomous/) | Коммерческая no-code E2E платформа | Plain-English authoring, deterministic language model, Visual AI, API и cross-browser проверки | Делает visual evidence и deterministic natural-language replay ожидаемыми; отсутствие visual/a11y в Testence — продуктовый пробел, а не необязательное украшение |
| [BrowserStack Agentic Low Code](https://www.browserstack.com/docs/low-code-automation/test-recording/browserstack-ai/agentic-testing) | Agentic authoring на browser/device cloud | Generate → refine → automate → validate → heal, real devices, full version history и intent-aware healing | Задаёт планку self-validation и масштаба; Testence не обязан владеть cloud, но должен поставлять чистый remote-provider контракт и полную историю решений |
| [SmartBear Reflect](https://support.smartbear.com/reflect/docs/en/recording) | Коммерческая AI/no-code платформа | Recording и natural-language steps, API/visual/email/SMS flows, reusable segments и адаптация runtime | Сильный benchmark для manual-QA UX. Testence должен сохранить явный код и review вместо скрытой адаптации, не уступая в end-to-end широте критичных web flows |
| [Playwright Test Agents](https://playwright.dev/docs/test-agents) | Open-source runner и определения planner, generator и healer для coding agents | Понятные планы, генерация исполняемых тестов, live-проверка селекторов/assertions и цикл ремонта с установкой для VS Code, Claude, Codex и OpenCode; зрелый runner уже поддерживает cross-browser, traces, parallelism и большую экосистему | Базовая точка сравнения. Testence не победит одной формулой «Playwright плюс агент»; нужны более сильные доказательства, безопасность и история детерминированного replay |
| [Momentic](https://momentic.ai/docs) | Коммерческая AI-native платформа; читаемый YAML хранится с проектом | Natural-language authoring, web/iOS/Android, local/CI execution, agent maintenance, кеширование шагов, отчёты, видео и traces | Задаёт планку удобства authoring и maintenance; Testence может отличаться local-first кодом, нейтральностью к провайдеру и отсутствием вызовов модели при replay |
| [QA Wolf](https://docs.qawolf.com/qawolf/Welcome-to-QA-Wolf) | Управляемый testing service на Playwright/Appium-коде | AI-assisted создание покрытия, управляемые запуск и сопровождение, web/mobile и широкие workflow-интеграции | Конкурирует результатом и сервисом, а не только функциями фреймворка. Testence должен оставаться принадлежащим разработчику и компонуемым, а не копировать managed QA service |
| [mabl](https://help.mabl.com/hc/en-us/articles/31649455424660-Create-tests-with-generative-AI) | Коммерческая low-code платформа | Prompt-based создание browser, mobile и API тестов, visual assertions и semantic auto-healing | Повышает ожидания к visual testing и простоте создания; healing в Testence должен оставаться проверяемым и измеримым, а не скрыто менять тесты |
| [testRigor](https://testrigor.com/docs/language/) | Коммерческая natural-language платформа | Тесты на обычном английском для web, mobile, desktop и API с интеграциями реальных workflows | Показывает широту, ожидаемую enterprise QA. Testence сначала должен выиграть более узкую UI-first нишу разработчиков, а не охватывать все платформы |
| [KaneAI](https://www.lambdatest.com/video/product-update-july-2024) | Коммерческий agentic authoring в облачной тестовой платформе | Natural-language планирование, authoring и эволюция вместе с масштабным browser/device execution | Testence нужны чистые контракты CI/sharding и переносимые артефакты, даже если он сознательно не владеет device cloud |

## Смежные open-source проекты

| Продукт | Что это | Отношение к Testence |
|---|---|---|
| [Midscene.js](https://midscenejs.com/) | Vision-driven автоматизация UI с действиями, assertions и extraction на естественном языке, интеграции Playwright/Puppeteer | Возможный необязательный backend для authoring/discovery и конкурент в AI-native UI interaction. Testence не должен требовать vision или модель в обычном CI |
| [Stagehand](https://docs.stagehand.dev/v3/first-steps/introduction) | SDK автоматизации браузера, объединяющий код, `act`, `extract`, `observe` и автономных агентов | Скорее примитив автоматизации, чем тестовый фреймворк. Кешируемые и воспроизводимые действия подтверждают разделение AI-discovery и детерминированного исполнения в Testence |

## Уже существующие отличия Testence

Подробная методика и текущие локальные результаты находятся в
[конкурентном бенчмарке](benchmark/competitive.md). Возможности из vendor-источников
не считаются измеренными, пока соответствующий arm не выполнен на общем SUT.

- **AI компилирует, runner воспроизводит.** Исполнение детерминировано и в обычном пути
  не использует SDK модели или вызов model provider.
- **Evidence — поверхность продукта.** Версионированный append-only журнал,
  ограниченные evidence packs, состояние UI, сигналы console/network и API-oracles в
  той же сессии предназначены и людям, и агентам.
- **Healing проверяем.** Предлагаемое изменение локатора — diff с доказательствами, а
  не скрытый runtime rebind.
- **Корректность измерима.** Синтетический корпус содержит дефекты и безвредные controls,
  поэтому можно оценивать false green, false red и падения по неверной причине.
- **Local-first и provider-neutral.** Пользователь владеет Python-тестами и может
  независимо выбирать coding или triage agent.

Категория и краткое позиционирование:

> **Agent-native UI verification.** Testence — слой верификации между coding agent и
> веб-приложением: агент планирует, создаёт и поддерживает тесты; Testence
> детерминированно воспроизводит их и возвращает структурированные доказательства,
> по которым агент может вынести вердикт.

Публичное обещание: **дайте coding agent описание функции — получите проверяемый план,
детерминированные UI-тесты и вердикты с доказательствами.**

## Существенные пробелы

### Что необходимо закрыть до публичной альфы

- Нет полного цикла bootstrap агента → PlanSpec → discovery → generation → proof →
  triage → reviewed repair.
- Нет переносимых Agent Skills или стабильных типизированных CLI/MCP-контрактов.
- Для body сетевых запросов/ответов и локальных сессий нет документированной политики
  редактирования и работы с секретами. Пока это не исправлено, сбор доказательств
  небезопасен для чувствительных приложений.
- Static quality gates не зелёные, публичная матрица CI/release отсутствует.
- Доказан только узкий путь Chromium/CDP; Firefox/WebKit и управляемый browser lifecycle
  не являются first-class.
- Публичный benchmark полезен как инженерное доказательство, но остаётся синтетическим
  и слишком мал для сравнительных продуктовых заявлений.

### Ожидаемая широта UI-тестирования

- visual comparison и accessibility assertions;
- trace/timeline viewer и группировка падений;
- iframe, shadow DOM, downloads/uploads, dialogs, popups и multi-tab;
- responsive/device profiles и cross-browser проекты;
- несколько пользователей/сессий, email/SMS/MFA hooks и богатый lifecycle test data;
- test selection, sharding, quarantine и история flakes.

### Стратегическая сдержанность

Testence не должен конкурировать, помещая действия на естественном языке внутрь каждого
шага CI. Это уничтожает преимущества скорости, воспроизводимости и auditability.
Agentic или vision-driven действия могут быть authoring-time compiler либо явным opt-in
fallback, результат которого кешируется, проверяется и переводится в детерминированный
код.
