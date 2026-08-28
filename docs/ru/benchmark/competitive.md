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

`bench/competitive/run.py` запускает Testence и Playwright Test на одном статическом
SUT и одинаковом шестишаговом сценарии. Каждый sample — новый процесс runner; в
границу входят discovery, запуск Chromium, тест, reporting и shutdown. Запуск SUT не
входит. Arms выполняются последовательно, с одним worker, без retries, trace и video;
один warm-up отбрасывается.

На Windows 11, Playwright Chromium 151.0.7922.34, Python 3.12.13 и Node 22.22.0,
семь измеренных повторов дали:

| arm | median | p95 | исходник сценария |
|---|---:|---:|---:|
| Testence | 1 743,5 ms | 1 812,3 ms | 13 содержательных строк |
| Playwright Test | 2 404,6 ms | 2 462,7 ms | 21 содержательная строка |

Медиана Testence оказалась **на 27,5% ниже** (ratio `0,725`). Это измерение
fresh-process replay на одном host, а не доказательство скорости реального suite.
Размер исходника — только прозрачный proxy,
а не время написания. Raw samples, версии и revision методики находятся в
`bench/results/competitive-replay.json`.

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
