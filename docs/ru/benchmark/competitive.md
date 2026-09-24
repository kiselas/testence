# Конкурентный бенчмарк

Снимок методики: 2026-08-28. Этот benchmark разделяет три разных вопроса, которые
нельзя честно сворачивать в одно маркетинговое число:

1. **Replay:** насколько быстро и стабильно уже принятый тест выполняется в CI.
2. **Authoring:** сколько времени, действий агента и человеческой проверки требуется,
   чтобы получить впервые принятый тест.
3. **Workflow:** насколько хорошо продукт проводит путь requirement → plan → test →
   proof → triage → reviewed repair и какие артефакты остаются после каждой фазы.

## Когорты

| когорта | продукты | что сравнивается |
|---|---|---|
| Прямые agent-native | Testence, Playwright Test Agents, Virtuoso Touchstone, Leapwork Play, Functionize Studio, Applitools Autonomous, Momentic, KaneAI, BrowserStack Agentic Low Code, Reflect | Полный цикл создания, исполнения, доказательств и сопровождения UI-тестов |
| AI/low-code альтернативы | mabl, testRigor, Katalon, Autify, ACCELQ, Testim, Tosca | Стоимость и удобство достижения того же результата другой моделью владения тестами |
| Code-first baselines | Playwright Test, Cypress, WebdriverIO, SeleniumBase, Robot Framework Browser | Скорость runner, переносимость кода и зрелость обычного инженерного workflow |
| Смежные компоненты | Stagehand, Midscene.js, Playwright MCP/CLI, Chrome Recorder, browser clouds, reporting/visual tools | Отдельные части authoring, execution, evidence или triage; не участвуют в общем рейтинге продукта |

Managed service QA Wolf сравнивается отдельным треком: он продаёт гарантируемый
результат и обслуживание, поэтому его человеко-часы нельзя смешивать с DIY-фреймворком.

## Уже выполненный replay-замер

`bench/competitive/run.py` запускает пять участников — Testence, Playwright Test,
pytest-playwright, Cypress и SeleniumBase — на одном статическом SUT и одинаковом
шестишаговом сценарии ([bench/competitive/README.md](../../../bench/competitive/README.md)).
Каждый sample — новый процесс runner; в границу входят discovery, запуск браузера, тест,
reporting и shutdown, запуск SUT не входит. Каждый участник работает в своём закреплённом
окружении, с одним worker, без retries, trace, video и скриншотов; один warm-up на
участника отбрасывается, samples берутся раундами в перемешанном с фиксированным seed
порядке.

Windows 11, 8 логических CPU, системный Chrome 153.0.8010.53 у всех участников,
ревизия `26ce56e`, 30 раундов (`bench/results/competitive-replay.json`):

| Участник | Медиана | 95% ДИ медианы | p95 | Исходник сценария |
|---|---:|---:|---:|---:|
| Playwright Test 1.63.0 | 2 499 ms | 2 356–2 866 | 3 633 | 21 строка |
| pytest-playwright 0.9.0 | 3 018 ms | 2 725–3 327 | 4 867 | 9 строк |
| Testence (Playwright 1.62.0) | 3 462 ms | 3 222–3 742 | 5 412 | 13 строк |
| SeleniumBase 4.54.11 | 6 717 ms | 6 359–7 167 | 8 593 | 12 строк |
| Cypress 15.21.1 | 20 141 ms | 19 306–20 707 | 23 219 | 10 строк |

Fresh-process replay одного шестишагового теста: Testence в 1,9 раза быстрее SeleniumBase
и в 5,8 раза быстрее Cypress, на 15% медленнее pytest-playwright и на 39% медленнее
Playwright Test. Жизненный цикл движка Playwright совпадает с чистым Playwright; разница —
в сессии и в evidence, которое записывает каждый шаг DSL. Это один host и один короткий
тест, а не заявление о скорости реального набора. Прежний снимок на двух участниках
(август 2026, bundled Chromium 151, семь повторов) показывал Testence на 27,5% быстрее
Playwright Test; здесь он не воспроизвёлся и заменён. Размер исходника — прозрачный
proxy, а не время написания.

Корпус seeded behaviours дополнительно выполнен тремя повторами: 51 item-run,
`outcome_accuracy=1.0`, `false_green_rate=0.0`, `false_red_rate=0.0`,
`right_reason_rate=1.0`, `heal_recall=1.0`. Результат остаётся saturated smoke floor:
в корпусе пока нет A-stratum и сложных multi-page/concurrent сценариев.

## Протокол authoring

Каждый продукт получает один и тот же requirement, репозиторий SUT, стартовую точку и
acceptance suite. Для coding-agent продуктов используется свежая изолированная сессия;
контекст между arms не переносится. Для hosted-продукта фиксируются plan, модель,
регион и включённые AI/healing функции.

Измеряются:

- время до первого зелёного запуска и до review-accepted diff;
- число agent turns, browser/tool calls, retries и ручных вмешательств;
- входные и выходные tokens, если продукт их раскрывает;
- количество созданных/изменённых файлов и содержательных строк;
- доля acceptance claims, реально покрытых независимой проверкой;
- время ревью и число замечаний, без исправления которых тест не принимается.

Минимум — три независимых authoring-сессии на arm. Публикуются все prompts, результаты
и причины исключения samples. LOC никогда не подменяет elapsed authoring time.

## Протокол maintenance и healing

Принятый тест прогоняется на четырёх изменениях: harmless restyle/reorder, переименование
доступного имени, настоящий behavioural defect и timing instability. Измеряются время
до диагноза, false heal, false red, правильность причины, размер diff и необходимость
человеческого одобрения. Повтор interaction запрещён там, где он скрывает дефект.

Healing получает положительный результат только если изменение видно, объяснено,
связано с evidence, проверено targeted rerun и не применено скрытно. Runtime, который
«нашёл похожую кнопку» и продолжил, не считается успешным repair без такого следа.

## Оценка workflow

Фазы оцениваются отдельно: intake, planning, discovery, authoring, live proof,
deterministic replay, evidence/triage, repair/review и portability. Вес и шкала должны
быть опубликованы рядом с баллами; неизвестная возможность остаётся `not measured`, а
не получает ноль по догадке.

Текущий вывод по официальной документации, не hands-on benchmark:

- лучший открытый repo-first baseline — [Playwright Test Agents](https://playwright.dev/docs/test-agents);
- наиболее близкий enterprise assurance workflow — [Virtuoso Touchstone](https://www.virtuosoqa.com/) и [Leapwork Play](https://leapwork.com/leapwork-play/): оба уже заявляют review/governance, evidence и детерминированное исполнение;
- сильный local/repo natural-language UX — [Momentic](https://momentic.ai/docs);
- managed outcome — [QA Wolf](https://docs.qawolf.com/qawolf/Welcome-to-QA-Wolf);
- наиболее прозрачный локально измеренный trust/replay слой в этом исследовании — Testence, но его полный agent workflow ещё не поставляется.

Общего победителя пока нет: commercial arms не запускались на одном SUT и одном плане.

## Что изменилось в конкурентной позиции Testence

Формула «AI планирует, deterministic runner исполняет» больше не уникальна.
[Virtuoso](https://www.virtuosoqa.com/) пишет о reviewable diffs, traceability и evidence,
[Leapwork](https://leapwork.com/blog/leapwork-announces-continuous-validation-platform/)
— о deterministic-by-design governance, [Functionize](https://www.functionize.com/)
— о generative intent и deterministic core, а [Applitools Autonomous](https://applitools.com/platform/autonomous/)
— о deterministic language model.

Защищаемый клин Testence теперь уже:

- open, local-first и provider-neutral владение тестами и артефактами;
- публичный seeded corpus с false-green, false-red и right-reason, а не только pass rate;
- same-session UI/API oracles;
- открытая versioned evidence schema и ограниченные packs для агента;
- reviewable source diff вместо скрытого runtime healing.

Главные P0-пробелы: закончить requirement → plan → author → proof → verdict → repair,
реализовать redaction/security policy, стабилизировать portable skills/CLI, расширить
cross-browser и опубликовать воспроизводимый authoring benchmark. Visual/a11y, trace
viewer, failure grouping и сложные browser flows остаются P1.
