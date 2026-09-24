# Launch Thesis

Статус: **решение для исполнения**. Версия: `0.1`. Снимок: 2026-08-28.
Владелец: Product Owner. Пересмотр: после первого внешнего benchmark и пяти
наблюдаемых активаций.

Связанные артефакты: [DemoSpec](demo-spec.md) и
[Launch Benchmark Protocol](benchmark/launch-protocol.md).

## Решение

Testence не выходит на рынок как «ещё один AI-фреймворк тестирования». Мы создаём и
занимаем более узкую категорию:

> **Testence — trust layer для coding agents. Агент не закончил работу, пока не доказал,
> что пользовательский результат действительно достигнут.**

Публичный вход в категорию — одна дорогая и легко демонстрируемая проблема:

> **UI-тест прошёл. Данные не сохранились. Testence это обнаружил.**

Первый продуктовый клин — полный **Trustworthy Proof Loop**:

```text
requirement → PlanSpec → deterministic test → live proof
            → evidence → typed verdict → reviewed repair
```

До прохождения этого пути не расширяем продукт в device cloud, visual platform,
универсальный MCP-сервер, low-code editor или hosted dashboard.

## Пользователь и дорогая работа

Первичный пользователь — разработчик или небольшая продуктовая команда, уже
использующие coding agent для изменения веб-приложения. Они не хотят становиться
экспертами по ещё одному test runner. Их работа формулируется так:

> «После изменения кода докажи, что критический пользовательский путь работает,
> результат сохранился, зелёный тест не врёт, а падение объяснено правильной причиной».

Сегодня они выбирают между четырьмя неудовлетворительными альтернативами:

1. довериться компиляции, unit-тестам и визуальному просмотру страницы;
2. попросить coding agent интерактивно покликать браузер;
3. написать обычный Playwright-тест и вручную разбирать trace;
4. передать тестирование hosted AI-платформе и принять её модель владения, healing и
   хранения данных.

Testence должен выиграть не числом сгенерированных тестов, а меньшим **time to
trustworthy proof** при более низком риске false green и скрытого repair.

## Почему сейчас

| Основание | Уровень | Вывод |
|---|---|---|
| Playwright уже поставляет planner, generator и healer для нескольких coding-agent клиентов | Documented | Генерация теста и наличие agent definitions стали baseline, а не отличием |
| Agent Skills стандартизуют `SKILL.md`, progressive disclosure и переносимые ресурсы | Documented | Один канонический skill-pack реалистичнее набора независимых промптов для каждого клиента |
| В Testence уже есть append-only evidence, UI/API oracle, типы verdict, bounded pack и proposal вместо runtime healing | Hands-on | Технический фундамент соответствует trust-клину, хотя сквозной продукт ещё не собран |
| Текущий replay benchmark дал медиану 1 743,5 ms против 2 404,6 ms на одном синтетическом сценарии | Measured | Runtime не выглядит препятствием, но результат не доказывает более быстрое authoring или рыночное превосходство |
| 51 synthetic item-run прошёл с `false_green=0`, `false_red=0`, `right_reason=1.0` | Measured | Таксономия и harness работают как smoke floor; выборка пока слишком мала и синтетична для сильного публичного заявления |
| Пользователи coding agents будут платить вниманием за независимое доказательство результата | Hypothesis | Это центральная рыночная гипотеза; её нужно опровергать наблюдаемыми активациями, а не интервью без использования |

Текущие измерения находятся в [competitive benchmark](benchmark/competitive.md) и
[corpus report](benchmark/corpus.md). Они являются baseline, но не launch headline.

## Обещание и контракт результата

Входом является requirement, pull request, баг или продуктовый риск. Долговечным
выходом являются пять repo-owned артефактов:

1. **PlanSpec** с постоянными ID продуктовых утверждений, рисками, тестовыми данными и
   независимыми oracles;
2. **детерминированный тест**, исполняемый локально и в CI без модели;
3. **evidence ledger и bounded pack**, связывающие действие, UI, network и API с ID
   утверждения;
4. **typed verdict** с причиной, уверенностью, ссылками на evidence и правом
   воздержаться;
5. **reviewable proposal**, если тест действительно требует изменения, плюс минимальный
   доказательный перезапуск.

Продукт не считается agent-first, пока новый пользователь не получает все пять
результатов через coding agent без ручного изучения внутреннего DSL.

## Преимущества, которые усиливаем

| Преимущество | Пользовательская ценность | Как доказываем | Что создаёт защиту |
|---|---|---|---|
| UI + API oracle в одной сессии | Находит правдоподобный false green, когда интерфейс показывает успех, а система не изменилась | Доля seeded API-only defects, найденных с правильной причиной | Накопленный каталог oracle patterns и truth cases |
| Сквозные claim IDs | Можно понять, какое продуктовое обещание доказано или нарушено | Claim coverage и traceability completeness | Открытый контракт PlanSpec → code → evidence → verdict |
| Детерминированный replay без LLM | Быстрый, дешёвый, воспроизводимый CI | Replay latency, flake rate, отсутствие model calls | Совместимость с существующей test-инфраструктурой |
| Bounded evidence для агента | Меньше токенов и быстрее triage без свалки артефактов | Verdict accuracy, tokens и время до принятого диагноза | Версионированная evidence schema и corpus реальных падений |
| Healing как proposal | Исправление не скрывает дефект и остаётся reviewable | Unsafe-repair rate, accepted proposal rate | История решений, policy и доказательные reruns |
| Provider-neutral skills | Команда не привязана к одному coding agent | Один golden workflow в Codex/ChatGPT, Claude Code и OpenCode | Канонический skill-pack, compatibility suite и update protocol |
| Открытый truth corpus | Публичные заявления можно независимо опровергнуть или подтвердить | Независимые воспроизведения и новые внешние cases | Репутация достоверного стандарта, а не закрытый leaderboard |

Первые три публичных доказательства должны быть именно такими:

- Testence поймал false green, который прошёл UI-only проверку;
- Testence объяснил причину через claim-linked evidence, а не просто сделал тест красным;
- тот же принятый тест воспроизвёлся в CI без модели.

## Что заимствуем, а что оставляем своим

Мы используем общепринятые механики там, где уникальность не даёт ценности.

| Источник | Заимствуем | Адаптация Testence | Не копируем |
|---|---|---|---|
| [Playwright Test Agents](https://playwright.dev/docs/test-agents) | Разделение plan/generate/heal, seed test, `init-agents`, регенерация definitions при обновлении | Один proof loop, в котором plan и verdict имеют схемы, а repair требует evidence и rerun | Автоматический repair как доказательство корректности сам по себе |
| [Agent Skills specification](https://agentskills.io/specification) | `SKILL.md`, `scripts/`, `references/`, `assets/`, progressive disclosure и стандартный validator | Канонический skill-pack с тонкими клиентскими адаптерами | Длинные монолитные промпты и отдельную бизнес-логику на каждый клиент |
| [OpenCode Agent Skills](https://opencode.ai/docs/skills) | Совместимость с `.agents/skills`, permissions и обнаружение по metadata | Generic adapter сначала устанавливает стандартный путь; специфичный adapter добавляет только нужный shim | Зависимость core workflow от OpenCode config |
| [OpenAI Skills API](https://developers.openai.com/api/reference/go/resources/skills) | Неизменяемые версии и отдельный указатель default как lifecycle pattern | Локальный manifest фиксирует точную версию; канал stable меняется отдельно | Обязательный hosted registry или OpenAI API в runtime |
| [SWE-bench](https://github.com/SWE-bench/SWE-bench) | Verified subset, изолированный evaluator, raw logs и воспроизводимые задачи | `Testence Verified`: реальные OSS-приложения плюс публичные seeded patches | Один процент leaderboard без разложения false green/right reason |
| [web-platform-tests](https://web-platform-tests.org/writing-tests/index.html) и [Test262](https://github.com/tc39/test262/blob/main/CONTRIBUTING.md) | Локально запускаемый conformance corpus, metadata, positive/negative cases, lint перед вкладом | Каждый truth case с claim, ground truth, strata, expected verdict и control | Огромную матрицу браузеров до доказательства beachhead |
| [uv](https://docs.astral.sh/uv/guides/projects/) | Lockfile, one-command execution и проверяемая сборка | Frozen benchmark environment и чистая установка wheel | Собственный dependency manager |

Главное правило: **skills учат процессу; схемы и CLI обеспечивают корректность**.
То, что можно валидировать программно, не должно существовать только в Markdown.

## Канонический skill-pack и обновления

### Модель поставки

В исходниках и wheel хранится одна каноническая версия:

```text
agent-pack/
├── manifest.json
├── skills/
│   ├── testence-plan/SKILL.md
│   ├── testence-author/SKILL.md
│   ├── testence-triage/SKILL.md
│   └── testence-repair/SKILL.md
├── references/        # PlanSpec, verdict и policy contracts
└── adapters/          # только discovery paths и instruction shims
```

Skills следуют открытому Agent Skills format. Все значимые операции вызывают
структурированный Testence CLI. Клиентские адаптеры не содержат копий workflow.

### Пользовательский lifecycle

Целевой интерфейс:

```bash
testence agent install --project . --client codex --json
testence agent verify --project . --client codex --json
```

`install` создаёт repo-owned lock manifest со следующими полями:

- версия Testence, schema и agent-pack;
- выбранный adapter и фактические target paths;
- SHA-256 каждого установленного файла;
- исходная версия, локальная модификация и доступная версия;
- канал обновления (`stable` или явно выбранный prerelease).

Обновление выполняется безопасно:

1. строит manifest и diff до записи;
2. не перезаписывает локально изменённый файл;
3. применяет чистые изменения атомарно;
4. для конфликта создаёт proposal/patch и ненулевой exit code;
5. сохраняет предыдущий pack для точного rollback;
6. после обновления запускает discovery smoke test выбранного клиента.

Первая версия поставляется вместе с wheel и не требует сети. Позже registry или HTTP
catalog может ускорить распространение, но remote pack принимается только с digest,
provenance и явным обновлением. Автообновление без review запрещено.

### Матрица клиентов

| Клиент | Канонический контент | Тонкий adapter | Gate |
|---|---|---|---|
| Codex / ChatGPT | тот же Agent Skills pack | поддерживаемый plugin/skill package и ограниченный блок `AGENTS.md` | discovery, явный invoke, полный golden path |
| Claude Code | тот же pack | `.claude/skills` или plugin и ограниченный `CLAUDE.md` | те же три проверки |
| OpenCode | предпочтительно `.agents/skills`, которое клиент уже обнаруживает | `AGENTS.md` и permissions при необходимости | те же три проверки |
| Generic | `.agents/skills` | инструкция ручного подключения | schema/CLI contract tests |

Платформа считается поддерживаемой только после CI-smoke обнаружения skills и
наблюдаемого полного сценария. Наличие скопированного `SKILL.md` не считается
совместимостью.

## Launch gates

Публичный запуск разрешён, когда одновременно выполнено следующее:

- полный killer demo воспроизводится из чистого checkout одной командой без signup и
  обязательного cloud;
- четыре из пяти новых пользователей получают первый trustworthy proof не более чем
  за 15 минут без подсказок автора;
- frozen corpus не содержит известного false green или unsafe repair;
- canary secrets отсутствуют в ledger, pack, HTML и экспортёрах;
- один и тот же workflow доказан в Codex/ChatGPT, Claude Code и OpenCode;
- launch benchmark запускается одной документированной командой и публикует raw data;
- не менее двух внешних людей независимо воспроизводят demo, один из них настроен
  скептически и проверяет материал статьи;
- README, wheel, CI, `SECURITY.md`, contribution и compatibility policy готовы для
  внешнего пользователя.

Stars, просмотры и число сгенерированных тестов не заменяют эти gates.

## Публичные заявления

Порядок допустимых сообщений:

1. **Сейчас:** «Testence исследует evidence-first подход; текущие цифры относятся к
   открытому синтетическому corpus».
2. **После protocol run:** точные correctness и time-to-proof результаты с интервалами,
   raw artifacts и ограничениями.
3. **После независимого воспроизведения:** «результат воспроизведён внешними
   участниками».
4. **Только после real-app breadth:** сравнительное продуктовое преимущество.

Замер replay ([competitive](benchmark/competitive.md)) и `200×` пооперационного
эксперимента не являются заголовком launch. Они отвечают на узкие инженерные вопросы, но не на вопрос о времени достижения
доверенного результата.

## Дистрибуция

Один технический факт становится центром всех материалов, но каждый канал получает
свой угол:

- Habr: технический case «Почему UI-тест прошёл, когда данные не сохранились»;
- vc.ru: цена ложной уверенности и история продуктового решения;
- Show HN: работающий репозиторий, который можно запустить без регистрации;
- англоязычная статья: open trust contract, false greens и reproducible benchmark;
- короткое видео/X: визуальный момент green UI-only → red evidence-backed verdict.

Публикации выходят волной в течение 72 часов, а не одновременно: команда должна
успевать отвечать, исправлять onboarding и направлять обсуждение к воспроизводимому
артефакту.

## Риски и kill criteria

Стратегию пересматриваем, если подтверждается хотя бы один пункт:

- менее трёх из пяти целевых разработчиков считают проблему доверия достаточно
  болезненной после hands-on использования;
- same-session API oracle требует столько project-specific glue, что первая ценность
  стабильно занимает больше 30 минут;
- Testence не улучшает correctness или time-to-trustworthy-proof относительно хорошо
  настроенного Playwright Test Agents на одинаковых задачах;
- преимущество проявляется только на нашем синтетическом SUT;
- пользователи воспринимают evidence и PlanSpec как налог и систематически обходят их;
- Python runtime блокирует web-команды сильнее, чем trust contract их привлекает.

При срабатывании этих критериев не наращиваем feature set. Предпочтительный pivot —
открытый evidence/verdict layer поверх существующих runners, а не более широкий
самостоятельный framework.

## Порядок исполнения

1. Заморозить [DemoSpec](demo-spec.md) и truth сценария.
2. Реализовать Trustworthy Proof Loop для одного клиента, включая security/redaction.
3. Вынести канонический skill-pack и safe update lifecycle.
4. Запустить frozen [Launch Benchmark Protocol](benchmark/launch-protocol.md).
5. Исправить onboarding по пяти наблюдаемым пользователям.
6. Только после gates готовить launch wave и расширять совместимость.

Новая функция попадает перед этим порядком только если она закрывает launch gate,
улучшает центральную метрику или делает публичное доказательство честнее.
