# Launch Benchmark Protocol

Статус: **предварительно зарегистрированный протокол**. Версия: `0.1`.
Снимок: 2026-08-28. Владелец: Product Owner совместно с benchmark maintainer.

Протокол должен быть заморожен до сравнительного запуска. После freeze изменения
разрешены только новой версией с объяснением; неудобный результат не является причиной
переписать правила.

Связанные документы: [Launch Thesis](../launch-thesis.md),
[DemoSpec](../demo-spec.md), [текущий competitive benchmark](competitive.md) и
[corpus](corpus.md).

## Решение, которое должен обеспечить benchmark

Launch benchmark отвечает не на вопрос «кто быстрее кликает», а на вопрос:

> **Помогает ли Testence coding agent быстрее получить корректное, проверяемое и
> сопровождаемое доказательство пользовательского результата, не маскируя дефекты?**

Порядок оценки неизменен:

1. correctness и безопасность;
2. правильность причины;
3. время до принятого доказательства;
4. стоимость и человеческое вмешательство;
5. replay performance;
6. удобство и переносимость.

Arm, не прошедший correctness gate, не может выиграть за счёт скорости.

## Предварительно зарегистрированные гипотезы

| ID | Гипотеза | Основная метрика | Kill criterion |
|---|---|---|---|
| `H1` | Testence находит больше правдоподобных false green с правильной причиной, чем UI-only baseline | false-green rate и right-reason rate на paired cases | Нет улучшения либо хотя бы один известный false green на launch-critical case |
| `H2` | Testence снижает время от requirement до review-accepted trustworthy proof относительно Playwright Test Agents | paired median TTTP | Нет улучшения либо выигрыш исчезает после добавления review time |
| `H3` | Proposal workflow отличает безопасный drift от product bug и не маскирует дефект | unsafe-repair rate, repair precision | Любой автоматически принятый unsafe repair |
| `H4` | Принятый результат переносим между agent clients | portability completion rate | Хотя бы один обязательный клиент требует fork основной workflow-логики |
| `H5` | Evidence pack ускоряет triage без потери существенных сигналов | verdict accuracy, time, tokens | Bounded pack снижает accuracy относительно raw artifacts больше чем на 5 п.п. |

`H2`, `H4` и ценность для пользователя являются Hypothesis до запуска полного
протокола. Текущие replay/corpus результаты относятся только к инженерному baseline.

## Сравниваемые arms

### Обязательные

1. **Testence Trustworthy Proof Loop** — канонический skill-pack, Testence CLI,
   PlanSpec, deterministic test, evidence/verdict и proposal policy.
2. **Playwright Test + Playwright Test Agents** — официальный planner/generator/healer,
   обычные Playwright artifacts и лучшие публично документированные практики.

Playwright является сильным code-first baseline, а не намеренно ослабленным
«ручным тестом». Его agent definitions регенерируются для установленной версии, как
требует [официальная документация](https://playwright.dev/docs/test-agents).

### Диагностический baseline

3. **UI-only accepted test** — минимальная проверка видимого результата без
   независимого oracle. Он нужен для демонстрации false-green class, но не получает
   общий product score.

### Необязательные commercial arms

Momentic и другие hosted products допускаются только после hands-on запуска на том же
SUT и requirement. `Documented` или `Vendor claim` не превращаются в измеренный ноль и
не смешиваются с локальными arms в одном рейтинге.

## Набор задач

Benchmark состоит из трёх слоёв. Один слой не заменяет другой.

### L0 — Synthetic Conformance

Назначение: быстрый детерминированный regression floor.

Launch minimum — не менее 30 независимых truth cases:

- не менее 12 `real_bug`, включая минимум 6 API-only/optimistic false greens;
- не менее 5 `ui_change`;
- не менее 3 `flaky_timing` или `environment`;
- не менее 10 healthy/harmless controls;
- минимум 6 случаев, где retry/reload может скрыть дефект;
- минимум 4 неоднозначных случая, где корректный результат — `blocked_on`, а не
  уверенный verdict.

Каждый case содержит human-readable metadata и machine-readable truth:

```yaml
id: D-acknowledged-not-persisted
requirement: blocker.create.persisted
stratum: api-only
truth: real_bug
expected_claims: [blocker.create.persisted]
forbidden_repairs: [remove-api-oracle, retry-create, weaken-persistence]
control_pair: C-create-persisted
```

Структура заимствует conformance-дисциплину
[web-platform-tests](https://web-platform-tests.org/writing-tests/index.html) и
[Test262](https://github.com/tc39/test262/blob/main/CONTRIBUTING.md): plan до широкой
реализации, metadata, positive/negative cases, локальный runner и обязательный lint.

### L1 — Testence Verified

Назначение: доказать, что преимущество не существует только на нашем SUT.

Launch minimum:

- два публичных OSS web-приложения разных стеков;
- по три задачи на приложение: creation/persistence, filter/search и update/delete;
- для каждой задачи healthy commit, один real bug patch и один harmless change;
- ground truth независимо проверяют два человека;
- task отклоняется, если requirement неоднозначен, приложение нестабильно без patch или
  evaluator знает seed только через скрытый side channel.

Из [SWE-bench](https://github.com/SWE-bench/SWE-bench) заимствуются две практики:
human-verified subset и изолированное воспроизводимое окружение с raw logs. На launch
достаточен малый verified set; репрезентативность нельзя изображать большим числом
слабых synthetic cases.

### L2 — Agent Authoring and Maintenance

Для шести L1-задач каждый обязательный arm проходит:

1. requirement → plan;
2. authoring → первый исполняемый тест;
3. live proof → review-accepted test;
4. запуск на healthy control;
5. запуск на real bug;
6. harmless drift и reviewable repair;
7. deterministic replay без agent session.

Минимум три независимые сессии на пару `arm × task`. Для headline-сравнения TTTP нужно
не менее 18 завершённых authoring sessions на arm. Если бюджет не позволяет, результат
маркируется pilot и не превращается в общее процентное заявление.

## Единица оценки и границы времени

**Time to trustworthy proof (TTTP)** начинается, когда агент получает requirement и
чистый checkout, и заканчивается, когда одновременно:

- PlanSpec прошёл schema и policy validation;
- созданный тест исполним и принадлежит repository;
- все обязательные claims имеют evidence;
- verdict соответствует ground truth или корректно воздерживается;
- reviewer принимает test diff и proof без обязательных замечаний.

Отдельно фиксируются:

- `time_to_first_runnable`;
- `time_to_first_green`;
- `time_to_first_correct_verdict`;
- `human_review_time`;
- `targeted_repair_time`.

Зелёный тест без обязательного claim либо неверный verdict не останавливает TTTP.

## Метрики

### Correctness

| Метрика | Определение |
|---|---|
| false-green rate | real-bug cases, получившие green/accepted proof, делённые на все real-bug cases |
| false-red rate | healthy/harmless controls с ошибочным red verdict, делённые на все controls |
| outcome accuracy | cases с ожидаемым outcome, делённые на все оценённые cases |
| right-reason rate | failures с правильным truth class и обязательными failed claims, делённые на найденные failures |
| abstention quality | неоднозначные cases с корректным `blocked_on` и без выдуманного verdict |
| claim coverage | обязательные PlanSpec claims с независимым proof, делённые на все обязательные claims |

### Repair safety

| Метрика | Определение |
|---|---|
| unsafe-repair rate | proposals/changes, скрывшие real bug или ослабившие обязательный claim |
| repair precision | принятые безопасные repairs, делённые на все предложенные repairs |
| repair recall | repairable UI changes с корректным proposal |
| review burden | время review и число обязательных замечаний до принятия |

### Agent economics

- TTTP и его фазы;
- agent turns, browser/tool calls, retries и manual interventions;
- input/output tokens и disclosed model cost;
- число созданных/изменённых файлов и размер review diff;
- доля tests, принятых без ручного переписывания;
- tokens на корректный verdict, а не на любой ответ.

### Replay и portability

- fresh-process median/p95 и steady-state test latency;
- flake rate на пяти последовательных повторах;
- отсутствие model/network calls к provider в deterministic replay;
- completion одного golden workflow в Codex/ChatGPT, Claude Code и OpenCode;
- число client-specific строк workflow logic;
- canary leakage count во всех artifacts.

## Экспериментальные правила

### Окружение

- фиксируются OS, hardware, browser binary, Python/Node, package versions и commit SHA;
- `uv.lock` и browser revision заморожены; запуск использует locked environment;
- L1 tasks выполняются в resettable container или эквивалентном immutable image;
- network доступ одинаков для paired arms и документирован;
- один worker используется для latency baseline; parallel runs являются отдельным
  экспериментом.

[uv](https://docs.astral.sh/uv/guides/projects/) используется как готовый механизм
lock/sync, а не заменяется собственным installer.

### Agent sessions

- одинаковые requirement, SUT, starting commit, acceptance criteria и разрешения;
- свежая сессия без переноса контекста между arms;
- одинаковая model family/snapshot и reasoning setting, где клиенты это позволяют;
- system/client overhead публикуется и не вычитается задним числом;
- порядок paired arms рандомизируется фиксированным seed;
- запрещено вмешательство автора, кроме заранее описанных permission prompts;
- wall-clock cap, turn cap и cost cap задаются до запуска;
- timeout считается неуспехом, а не молча исключённым sample.

### Stop rules и review

Reviewer использует чеклист, не знает truth label до решения и проверяет:

- покрыты ли обязательные claims;
- действительно ли oracle независим;
- можно ли воспроизвести test без agent session;
- не скрывает ли retry или repair дефект;
- достаточны ли evidence и provenance;
- отсутствуют ли секреты.

Если reviewer требует изменение, время продолжается. Необязательное стилистическое
замечание не блокирует принятие.

## Статистика

- raw samples публикуются полностью; median не публикуется без `n`;
- latency и TTTP показываются медианой, IQR и bootstrap 95% CI;
- доли показываются с Wilson 95% CI;
- сравнения L2 являются paired по task; интервал строится для paired difference;
- p95 помечается exploratory при малом `n`;
- выбросы не удаляются автоматически;
- исключение допускается только для заранее названной инфраструктурной причины и
  публикуется вместе с sample;
- failed/timeout sessions входят в completion rate;
- практическая величина эффекта важнее бинарного `p < 0.05`.

Headline `X% faster to trustworthy proof` разрешён только при correctness gate,
не менее 18 завершённых sessions на arm, положительном paired effect и отсутствии
ухудшения review burden/unsafe repair.

## Correctness и security gates

До расчёта общего преимущества обязательный arm должен:

- иметь `false_green_rate = 0` на launch-critical L0/L1 cases;
- иметь `unsafe_repair_rate = 0`;
- корректно пройти все healthy controls;
- не потерять ни один обязательный claim;
- не вывести ни один canary secret в ledger, pack, HTML, CTRF или Allure;
- воспроизвести accepted test без LLM.

Если gate не пройден, публикуется результат и failure analysis, но speed claim
запрещён.

## Публикуемый bundle

Каждый release benchmark включает:

```text
benchmark-release/
├── PROTOCOL.md
├── environment.json
├── tasks/                 # requirement, truth metadata, patches, controls
├── prompts/               # точные user/system inputs, где разрешено лицензией
├── sessions/              # transcripts, tool logs, costs, timing
├── outputs/               # plans, tests, diffs, evidence, verdicts, reports
├── results.json
├── results.csv
├── analysis.ipynb-or-script
├── checksums.txt
└── LIMITATIONS.md
```

Одна команда должна воспроизводить deterministic L0/L1 grading. Agent authoring может
требовать credentials, но evaluator, gold truth и уже опубликованные outputs — нет.

## Независимое воспроизведение

До launch:

- один внешний участник воспроизводит полный L0 и минимум одну L1-задачу;
- второй участник проверяет hero case и article claims;
- расхождения сохраняются как issues и входят в limitations;
- статус `independently reproduced` применяется только к точной версии protocol,
  corpus, product и environment.

В будущем внешний case принимается через маленький reviewable PR: truth metadata,
healthy control, defect patch, expected claims и лицензия. CI запускает lint, gold test,
canary scan и проверку determinism.

## Разрешённые launch claims

| Данные | Допустимая формулировка |
|---|---|
| Только текущий synthetic corpus | «На открытом синтетическом corpus версии X…» |
| L0 + L1 protocol | «На N frozen cases из двух OSS-приложений…» |
| L2 paired sessions | «В этом protocol median TTTP изменилась на X с 95% CI…» |
| Три client gates | «Один workflow воспроизведён в перечисленных версиях клиентов…» |
| Внешний rerun | «Результат версии X независимо воспроизведён…» |

Запрещены обобщения «не имеет false greens», «в 200 раз быстрее тестирования», «лучший
AI testing framework» и рейтинги непроверенных commercial products.

## Текущий baseline и разрыв до freeze

На 2026-08-28 уже измерено:

- replay одного synthetic шестишагового сценария; 2026-09-24 заменён замером пяти
  участников в 30 раундах на одной сборке браузера ([competitive](competitive.md)):
  Testence `3 462 ms`, Playwright Test `2 499 ms`, pytest-playwright `3 018 ms`,
  SeleniumBase `6 717 ms`, Cypress `20 141 ms` (августовские `-27,5%` двух участников
  не воспроизвелись);
- 51 synthetic item-run: outcome accuracy `1.0`, false green/red `0`, right reason
  `1.0`, heal recall `1.0`;
- authoring time, review time, cross-client portability и L1 real-app breadth не
  измерены.

Фундамент PlanSpec/verdict schemas и claim propagation готов. До protocol freeze
необходимо:

1. расширить L0 до launch minimum и добавить ambiguous abstention cases;
2. выбрать два OSS-приложения и получить разрешённые reproducible patches;
3. реализовать clean evaluator command и environment manifest;
4. зафиксировать model/client versions, caps и reviewer checklist;
5. провести один pilot, исправить только harness defects и затем объявить freeze.

Pilot data не объединяется с frozen run.
