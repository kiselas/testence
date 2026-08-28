# Дорожная карта

Roadmap строит Testence как **agent-native UI verification**: coding agent является
основным оператором, а детерминированное исполнение, проверяемые артефакты и политика
владельца остаются границей доверия. AI должен снижать стоимость написания и триажа,
не превращая каждое действие CI в медленный и недетерминированный вызов модели.

## P0 — безопасная основа публичной альфы (2–4 недели)

### Безопасность доказательств

- Ввести единый pipeline редактирования URL, query values, cookies, authorization
  fields, form data, JSON bodies, console messages и экспортируемых артефактов.
- По умолчанию запрещать захват body с учётом content type и размера; полный захват
  должен включаться явно.
- Добавить canary-секреты и golden tests, доказывающие, что они не попадают в ledger,
  pack, HTML, Allure или CTRF.
- Сделать кешированные browser sessions opt-in, ограниченными permissions, истекающими
  и явно помеченными как чувствительные. Описать удаление и поведение в CI.
- Добавить `SECURITY.md` и threat model для evidence, CDP endpoints и сохранённых
  браузеров.

### Воспроизводимый релиз

- Сделать pytest, Ruff и mypy зелёными; закрепить явный набор lint rules.
- Добавить CI для Windows/Linux и поддерживаемых версий Python, smoke tests editable
  install и wheel.
- Добавить build metadata, URLs проекта, `py.typed`, changelog/release automation и
  проверку установки пакета в чистом окружении.
- Добавить `CONTRIBUTING.md`, code of conduct и публичную compatibility policy API/схем.
- Добавить `testence doctor` для проверки Python, browser/CDP, профиля, TLS и возможности
  записи артефактов.

### Минимальный агентный продукт

- Определить версионированные схемы PlanSpec и verdict с ID утверждений, сохраняющимися
  в исходниках теста и событиях журнала.
- Поставлять один переносимый пакет Agent Skills для plan, author, triage и repair;
  клиентские инструкции оставить тонкими адаптерами.
- Добавить `testence agent init` с dry-run/manifest файлов, инструкциями проекта,
  синтетическим seed-тестом и без копирования секретов.
- Добавить структурированные CLI-операции для проверки плана, ограниченного запуска,
  поиска failure pack и валидации verdict. Их JSON-контракты станут основой MCP.
- Определить принадлежащую репозиторию permission policy для согласованных targets,
  seed mutations, доступа к evidence и предложений, меняющих исходники.
- Доказать полный golden path хотя бы в одном coding agent: запрос → reviewed plan →
  сгенерированный детерминированный тест → live proof → verdict с доказательствами.

### Честный benchmark

- Сделать синтетический SUT/corpus воспроизводимым в CI одной командой.
- Записывать browser, OS, hardware, revision корпуса, число повторов и confidence
  intervals.
- Публиковать false-green, false-red и right-reason рядом с latency; не переносить
  текущий пооперационный результат 200× на уровень suite.

**Gate для `0.1.0a1`:** очищенное дерево, redaction tests, зелёные quality gates,
чистая установка wheel, публичная benchmark-команда и один локальный end-to-end пример
под управлением агента. Агент может напрямую использовать CLI; MCP server для этого
gate не обязателен.

## P1 — переносимый и полный агентный цикл (4–8 недель)

### Работа с несколькими агентскими клиентами

- Проверить одинаковые переносимые skills в Codex/ChatGPT, Claude Code и OpenCode;
  публиковать тонкие setup adapters только там, где различаются правила обнаружения.
- Добавить необязательный MCP server над стабильными контрактами CLI/application.
  Инструменты должны быть узкими и ориентированными на задачи, а не раскрывать каждый
  внутренний helper.
- Завершить planner → plan review → controlled discovery → generator → live-проверка
  selectors/assertions → детерминированный тестовый код.
- Сохранить трассируемость от requirement и плана через сгенерированный тест до журнала.
- Позволить пользователю остановиться после любой фазы, проверить артефакты и продолжить
  совместимым агентом.

### Агентный триаж

- Группировать связанные падения, отделять продуктовые дефекты от environment/setup и
  показывать неопределённость вместе с `blocked_on`.
- Сохранять provider-neutral runner: model adapters принадлежат необязательному analysis
  package или agent tooling, но не execution core.

### Проверяемый healing

- Превратить fingerprints и оценку кандидатов в полный proposal UX: объяснение,
  confidence, evidence, diff исходников, целевой перезапуск и accept/reject.
- Отслеживать принятые и отклонённые предложения, измерять precision/recall на drift и
  defect controls.
- Никогда не переписывать тест скрыто во время CI.

**Gate для `0.2`:** один проект и те же артефакты проходят golden path через
Codex/ChatGPT, Claude Code и OpenCode, включая структурированный verdict падения и
проверяемый patch локатора.

## P2 — создать защитный ров в UI-тестировании (8–12 недель)

- First-class проекты Chromium, Firefox и WebKit, viewports и device profiles.
- Visual assertions/diffs и accessibility checks с интеграцией в evidence pack.
- Trace/timeline UI, связывающий намерение действия, разрешение локатора, DOM/ARIA,
  network, console, screenshot и API oracle.
- Надёжная работа с iframes, shadow DOM, popups, tabs, dialogs, uploads/downloads и
  websocket flows.
- Multi-user и multi-session сценарии с изолированными seed data.
- Расширения auth для storage state, OIDC/MFA hooks и email/SMS test adapters.
- История flakes, quarantine со сроком/владельцем, repeat policies и clustering падений.

**Gate для `0.3`:** публичный корпус покрывает эти UI-примитивы, а минимум два реальных
open-source приложения работают в cross-browser CI matrix.

## P3 — экосистема и масштабирование

- Стабильные plugin contracts для engines, auth, seed adapters, exporters, evidence
  filters и triage providers.
- Sharding, remote browser providers, Docker image и переиспользуемые CI workflows.
- Change-aware test selection и coverage mapping от поверхности продукта к specs/tests.
- Историческая аналитика flakes, семейств падений и качества evidence.
- Руководства миграции с Playwright/pytest и необязательные адаптеры Stagehand или
  Midscene для discovery; продвигаемым артефактом остаётся детерминированный код.
- Независимо воспроизводимые сравнения benchmark и не менее двух внешних design partners,
  использующих Testence на реальных приложениях.

**Gate для `1.0`:** стабильные public API и evidence schema, документированные
миграции, security review, cross-browser, внешние пользователи и отсутствие известных
критических пробелов корректности или приватности.

## Что пока не следует строить

- Собственное облако браузеров и устройств.
- Универсальную платформу API-тестирования: сначала API должен обслуживать UI-seeding
  и независимые oracles.
- Скрытый self-healing.
- Обязательный hosted dashboard или обязательного model provider.
- Действия на естественном языке в стандартном пути CI.
