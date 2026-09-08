# Как Testence должен получить первых пользователей

Дата: 6 сентября 2026. Это продуктовые гипотезы и план проверки, а не доказанная рыночная статистика. Технические условия публичного релиза — в [ТЗ](release-spec.md), факты о текущем состоянии — в [аудите](audit.md).

## Позиционирование

**Testence — открытый фреймворк, с которым QA управляет качеством нескольких веб-проектов, а разработчики и AI-агенты создают и поддерживают проверяемые UI-тесты. Результаты остаются в Allure/TestOps и вашем CI.**

Краткий английский вариант для будущего README:

> Agent-assisted UI testing, governed by QA.

Подзаголовок:

> Define the quality rules once. Let developers and agents build verifiable tests. Keep your Allure history and CI workflow.

Последнее предложение становится публичным обещанием только после TestOps migration/history acceptance. Сегодня допустима формулировка «Allure results export is implemented; full TestOps workflow is under validation».

Технический термин evidence contract полезен в документации. Первый экран должен объяснять работу и результат человека: меньше ручного триажа, проверяемые изменения тестов и ясный scope проверки. «Самый современный», «лучший AI testing» или «заменяет QA» не дают пользователю проверяемой причины попробовать продукт.

## Кто внедряет, кто работает, кто получает пользу

| Роль | Задача | Причина принять Testence |
|---|---|---|
| QA/SDET, QA lead | Задать риски, стандарты assertions, тестовые данные и исключения | Одни правила для нескольких проектов; сравнимые результаты и меньше ручных разборов |
| Разработчик | Проверить свою функцию/PR без ожидания отдельного автора autotest | Агент использует утверждённый workflow и выдаёт обычный repo-owned test |
| Coding agent | Получить ограниченный scope, исполнить тест и аргументировать вывод | Узкий CLI, typed artifacts, проверяемые ссылки и полезная ошибка вместо неоднозначного текста |
| Engineering manager | Ускорить обратную связь без роста пропущенных регрессий | Измеримый review/triage effort, новые принятые сценарии и повторное использование |
| CI/TMS maintainer | Сохранить инфраструктуру и историю | Additive migration, стабильные case IDs, корректные статусы и vendor receipts |

Начальный сегмент: продуктовые web-команды с существующей автоматизацией/CI, Allure и небольшим QA-ресурсом, готовые использовать Python/pytest. Это уже достаточно широкий рынок для проверки гипотезы. Не позиционировать R1 как no-code для полностью ручного QA или замену enterprise TMS.

Следующая аудитория — TypeScript/Playwright команды. Для неё главный барьер может быть Python runtime, а не интерфейс агента. Проверить это на интервью; при устойчивом барьере строить evidence/reporter adapter к существующему runner, а не переписывать ядро заранее.

## С чем пользователь сравнит продукт

| Альтернатива | Уже есть по первичным документам | Какой вопрос должен выиграть Testence |
|---|---|---|
| Playwright Test Agents + качественные тесты | Planner, generator, healer и создание обычного исполняемого кода | Меньше ли времени QA тратит на приемку покрытия и безопасное сопровождение? [Agents](https://playwright.dev/docs/test-agents) |
| pytest/Playwright + Allure 3 Agent Mode | Агентный анализ результатов существующей test command, skips/retries/evidence | Что добавляет исполнимая policy/claim/oracle, помимо отчёта? [Agent Mode](https://allurereport.org/docs/agent-mode/) |
| Stagehand | Cached actions и сочетание AI automation с code | Доказан ли пользовательский outcome и безопасен ли maintenance? [Caching](https://docs.stagehand.dev/v3/best-practices/caching) |
| Midscene | Vision-based automation, reports, cache, web/mobile APIs | Почему явно проверяемые assertions/evidence удобнее для данного QA workflow? [Reference](https://www.midscenejs.com/reference/) |
| Существующая команда без нового framework | Свои fixtures, Page Objects, checks, TMS mappings и опыт | Окупается ли migration и второй проект, а не только красивый первый demo? |

Не утверждать, что конкуренты не могут выполнить API-check, не имеют evidence или всегда вызывают модель на каждом шаге. В этом аудите сравнительные agent runs не проводились. Уникальность предлагаемой комбинации ещё предстоит доказать.

## Два demo вместо большого feature tour

### Demo A — «UI сказал успех, данные не сохранились» · 90 секунд

Показать одну точную бизнес-операцию: expected entity → UI success → ошибочная persistence → независимая проверка → конкретный failed claim в Allure. Затем тот же тест на healthy control и CI replay без модели. Дефект — открытая версия patch, приложение — локальное, без signup и чужих данных.

UI-only baseline назвать ограниченной проверкой toast/card, а не полноценным Playwright competitor. Рядом предоставить сильный baseline с API oracle: функция Testence — сделать такой стандарт повторяемым и доступным агенту, а не монополизировать GET-запрос.

Изменить текущий DemoSpec под QA: result открывается в Allure, связан с case/requirement и показывает, что именно нужно решить QA. Пользователь видит evidence и delta теста, а не изучает внутренние planes.

### Demo B — «Один QA, три проекта» · 4–6 минут

QA меняет общую quality policy. Разработчик/агент в первом проекте добавляет тест; во втором возникает locator drift; в третьем TestOps запускает выбранный regression subset. QA видит три проекта, нужных owners, missing proof и один reviewable repair в существующем отчёте.

Обязательный момент: в одном проекте policy update конфликтует с локальным override. Testence сохраняет изменение пользователя и показывает решение, которое требуется принять. Это демонстрирует реальную эксплуатацию, а не массовое копирование prompts.

## Пилот до широкого launch

Набрать три внешние команды через личные приглашения владельца продукта. Целевые профили:

1. QA/SDET и существующий pytest/Playwright + Allure suite.
2. Один QA на несколько web-проектов и разработчики с coding agents.
3. Команда с Allure TestOps, параметризацией и selective CI launches.

Одна команда может покрывать несколько профилей, но внешних команд всё равно должно быть три. Включить хотя бы одного скептически настроенного SDET. Приглашения и доступы — отдельное действие пользователя; этот документ никому не отправлен.

### Протокол наблюдения

- Зафиксировать baseline: текущий test workflow, QA minutes и регрессионные кейсы, а не общий субъективный вопрос «понравилось?».
- Не менее пяти новых пользователей проходят установку и Demo A без подсказок автора; observer записывает затруднения и вмешательства.
- Каждая команда переносит один существующий scenario с сохранением TMS case identity и добавляет один новый critical scenario.
- На второй неделе команда выполняет изменение/repair и повторный запуск сама. Именно этот момент проверяет устойчивое использование.
- Один QA выполняет U5 на трёх проектах; считается время подключения второго/третьего, разбора failures и поддержки policy.
- Если oracle проектно-специфичен, время реализации adapter включается в onboarding; не вычитать его из стоимости Testence.
- Собирать данные добровольно из project/CI artifacts. Обязательной скрытой telemetry нет.

### Продуктовые метрики

| Метрика | Определение | Предварительный порог R1 |
|---|---|---|
| Activation | Самостоятельно получен корректный proof + читаемый Allure result | 4 из 5 новых пользователей ≤15 минут на demo |
| Real-project adoption | Подключён существующий test с сохранённой case identity | Все 3 команды; blockers записаны |
| Return usage | Второй сценарий/repair и новый самостоятельный run на следующей неделе | ≥2 из 3 команд |
| QA effort | Суммарные минуты review+triage+maintenance на один принятый critical scenario | Предварительная гипотеза: снижение ≥20% без потери correctness; измерить парно, малый пилот не превращать в общую рекламу |
| Additional-project effort | Hands-on время QA для второго и третьего проектов | Записать оба значения; целевой ≤60 минут при готовых стандартных auth/seed adapters |
| Accepted proof | Покрытый required scope с проверенными assertions и корректным outcome | 100% release-critical claims в принятых пилотных задачах |
| Unsafe behavior | False green, secret leak, unsafe repair, неверный TMS project | 0 наблюдённых release-critical случаев |
| Support burden | Количество и минуты подсказок автора, workaround patches | Не скрывать; hand-held результат не считается self-serve activation |

Пороги — продуктовые решения этого ТЗ. Они не взяты из исследований рынка и могут пересматриваться только до следующей заморозки протокола, с объяснением причины.

## Как сравнивать качество, не подыгрывая себе

Три arm на одинаковых requirements и версиях приложений:

1. Текущий качественно настроенный pytest/Playwright + Allure workflow команды.
2. Доступный agent workflow поверх Playwright/Allure.
3. Testence с теми же oracle access и test permissions.

Для agent arms: одинаковая доступная модель/snapshot и лимиты, свежие сессии, случайный порядок paired tasks, одинаковый доступ к данным. Ground truth и seeded patches скрыты от агента. Не вычитать setup, review, failures, retries или инструментальные расходы из времени одного arm.

Публиковать completion rate, false green/red, right reason, abstention, unsafe repair, human review minutes, agent tokens/tools и TTTP. Корректное abstention не равно завершённому proof: считать его отдельно, иначе агент, всегда отвечающий «не знаю», победит метрику.

Headline о сокращении времени допустим только после correctness gate, не менее 18 независимых authoring sessions на arm (6 задач × 3), paired effect с uncertainty и раскрытых failed/timeout sessions. При цензурировании временем нельзя считать медиану только успешных runs общей производительностью: отдельно success-only latency и completion/timeout, либо заранее выбранная censored analysis. Малые серии — pilot, не leaderboard.

## Что выпустить для обнаружения и первой установки

- README EN с понятным QA outcome, working demo, Allure screenshot, командой установки, support matrix и ссылкой на limitations.
- Репозиторий demo с healthy/defect patches, licensed data, ожидаемым результатом и CI artifacts.
- Статья «Почему зелёный UI-тест не доказывает сохранение» с сильным baseline, reproduction и объяснением expected-oracle contract.
- Статья/видео «Как QA контролирует тесты, которые пишут разработчики и агенты», показывающая multi-project workflow и TestOps.
- Migration recipe: один существующий pytest case, сохранение external ID/history, rollback и реальная цена установки.
- Release benchmark bundle: commands, versions, raw data, grader, corpus licenses, confidence intervals и ограничения.
- 3–5 небольших contributor issues: новый truth case, mapping fixture, documentation example; рядом ожидаемый результат и способ локальной проверки.

Открытая лицензия, отсутствие обязательного аккаунта и интеграция с привычным workflow — свойства продукта. Каналы не компенсируют их отсутствие.

### Волна публикаций

| Когда | Материал | Признак успеха |
|---|---|---|
| До launch | Пилотные issues, тестирование install, внешний review demo | Исправлены повторяющиеся onboarding blockers |
| День 0 | GitHub release + package + reproduction, технический пост в подходящем сообществе | Независимые clone/install/run |
| Дни 1–3 | Habr/англоязычная статья, короткий demo, Show HN при готовом self-serve пути | Осмысленные questions/issues и реальные сценарии |
| Дни 4–14 | Публичные fixes из обратной связи, guide по migration и Allure/TestOps | Второй запуск, второй scenario, внешние contribution |
| Недели 3–6 | Разбор пилота, честные цифры, расширение только востребованного adapter | Возвращающиеся команды и сниженная нагрузка на QA |

Не рассылать одинаковый рекламный текст по многим сообществам. Отвечать доказательствами и минимальным working example. Stars и views — вспомогательные сигналы обнаружения; недельные активные проекты, повторные scenarios и adoption без помощи автора ближе к ценности.

## Условия пересмотра стратегии

- Большинство пилотов получает ту же пользу после небольшого улучшения своего Playwright/Allure workflow и не возвращается к Testence.
- PlanSpec/policy воспринимаются как дополнительная бюрократия; QA систематически отключает completeness gates.
- Стоимость auth/seed/oracle adapters превышает экономию сопровождения.
- Python stack блокирует основную долю подходящих web-команд.
- Интеграция требует отказаться от case history, manual cases или существующего CI процесса.
- Улучшение видно только на собственной синтетической странице или слабом UI-only baseline.

Ответ на эти сигналы — уменьшить объём обязательного framework и предложить открытый proof/policy/evidence adapter к существующим runners. Это направление следует проверять раньше native mobile, собственного browser cloud или новых AI функций. Добавлять features без повторного использования продукта не решает проблему принятия.
