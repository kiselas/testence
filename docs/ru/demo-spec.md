# DemoSpec: «Зелёный тест, ложный результат»

Статус: **контракт реализации**. Версия: `0.1`. Снимок: 2026-08-28.
Владелец: Product Owner совместно с maintainer demo repository.

С 8 сентября 2026 `testence init` создаёт конфигурацию с `headed: false`.
Demo запускается без графического дисплея на Linux CI. Для визуального просмотра
в отдельном onboarding-проекте можно явно выбрать `headed: true`.

Этот документ задаёт один launch demo. Любое изменение сценария должно сохранять
центральную причинность и оставаться совместимым с
[Launch Thesis](launch-thesis.md) и
[Launch Benchmark Protocol](benchmark/launch-protocol.md).

## Цель

За первые 90 секунд зритель должен увидеть и понять три факта:

1. обычная UI-only проверка зелёная;
2. пользовательский результат на самом деле не достигнут;
3. Testence находит расхождение, связывает его с продуктовым утверждением и даёт
   проверяемый вердикт.

После расширенной демонстрации зритель также должен убедиться, что принятый тест
воспроизводится без LLM, а изменение теста не применяется скрытно.

## Аудитория и desired reaction

Основная аудитория — разработчик, использующий Codex/ChatGPT, Claude Code или OpenCode.
Он знает Playwright на уровне обычных e2e-тестов, но не обязан знать Testence.

Желаемая реакция:

> «Я тоже считал toast и карточку достаточным доказательством. Это конкретный класс
> false green, а отчёт показывает не просто падение, а почему результат ложный».

Нежелаемая реакция:

> «Авторы специально написали плохой Playwright-тест, чтобы выиграть у Playwright».

Поэтому UI-only тест называется baseline pattern, а не «тест конкурента». Его код,
requirement и ограничения показываются полностью.

## Сценарий приложения

Публичный demo repository содержит маленькое приложение **Release Board**:

- пользователь создаёт blocker с названием и severity;
- UI оптимистично добавляет карточку и показывает `Blocker created`;
- browser отправляет `POST /api/blockers`;
- независимая истина доступна через `GET /api/blockers/:id` в той же сессии;
- приложение имеет явные, версионированные defect patches и healthy control.

Основной seeded defect — `acknowledged-but-not-persisted`:

1. `POST` отвечает success и возвращает ID;
2. UI сохраняет карточку в client state и показывает toast;
3. запись отсутствует в authoritative storage;
4. `GET` для того же пользователя возвращает `404` либо список без ID.

Это правдоподобная модель optimistic UI, ошибочной транзакции, асинхронной записи или
расхождения между write/read path. Defect реализуется минимальным публичным patch, а не
скрытой логикой benchmark harness.

## Requirement и PlanSpec

Единый пользовательский запрос для video, live demo и benchmark:

> «Проверь создание release blocker. После сохранения карточка должна появиться в UI,
> запись должна существовать для текущего пользователя и оставаться доступной после
> нового чтения. Подготовь долговечный тест и докажи результат».

Минимальные утверждения PlanSpec:

| ID | Утверждение | Источник доказательства |
|---|---|---|
| `blocker.create.requested` | browser отправил согласованный create request | network event |
| `blocker.create.visible` | новая карточка видна пользователю | semantic UI snapshot/assertion |
| `blocker.create.persisted` | запись существует в authoritative storage | same-session API oracle |
| `blocker.create.consistent` | значения UI и API согласованы | UI/API diff |

Агент может добавить сценарии, но не может удалить `persisted` или заменить его только
toast-проверкой. Plan review делает эту потерю видимой до генерации теста.

## Две линии доказательства

### Baseline UI-only

Публичный baseline проверяет отправку формы, toast и карточку. На основном defect он
должен стабильно проходить. Это демонстрирует класс ограничения, а не рейтинг продукта.

### Testence proof

Тест выполняет тот же пользовательский путь, но дополнительно:

- сохраняет intent и claim IDs;
- подтверждает, что create request ушёл;
- читает API как тот же пользователь;
- сравнивает ID, title и severity с UI;
- при расхождении строит bounded evidence pack;
- возвращает `real_bug`, а не предлагает повторить click или ослабить assertion.

Обе линии используют один target, одно состояние, один browser family и одинаковые
тестовые данные.

## Storyboard

### Hero cut — 90 секунд

| Время | Экран | Содержание |
|---:|---|---|
| 0–10 s | Requirement | Один запрос coding agent: реализовать долговечную проверку создания blocker |
| 10–22 s | PlanSpec | Четыре claim ID; выделяется `persisted` и независимый API oracle |
| 22–35 s | Split view | UI-only baseline зелёный; приложение показывает toast и карточку |
| 35–48 s | Truth reveal | API/read storage не содержит запись; зрителю показывается точный defect patch |
| 48–68 s | Testence report | Красная Proof Card: failed claim, UI state, request, API `404`, diff и `real_bug` |
| 68–82 s | Agent action | Агент меняет продуктовый код, а не тест, и запускает минимальный scope |
| 82–90 s | Final proof | Все claims зелёные; подпись «Plan with AI. Replay deterministically. Judge by evidence.» |

Монтаж не скрывает ожидание или retry. Ускоренные участки явно помечаются, рядом
доступна непрерывная запись реального времени.

### Live demo — 5–7 минут

1. Клонировать чистый demo repository и показать одну команду bootstrap.
2. Выполнить `testence agent install --project . --client <client>` и показать manifest созданных
   файлов, не читая их вручную.
3. Передать агенту requirement и согласовать короткий PlanSpec.
4. Показать сгенерированный repo-owned test и claim IDs.
5. Запустить baseline и Testence на frozen defect.
6. Открыть локальный report через ссылку из структурированного CLI output.
7. Попросить агента исправить причину; показать diff приложения.
8. Выполнить targeted rerun, затем тот же тест без агента обычной CI-командой.

Целевой bootstrap-интерфейс, который ещё предстоит реализовать:

```bash
uv sync --locked
uv run testence doctor
uv run testence agent install --project . --client codex --json
uv run testence demo run --project testence-demo --json
```

Если launch package допускает более короткую безопасную команду, она может заменить
первые две строки, но locked environment и диагностика должны остаться доступны.

### Extended proof — 12–15 минут

После основного исправления активируется `accessible-name-changed`:

- поведение приложения корректно, но семантическое имя кнопки намеренно изменено;
- Testence классифицирует падение как `ui_change`;
- repair формируется как source proposal с evidence, confidence и target scope;
- пользователь принимает diff;
- Testence выполняет targeted rerun и связывает его с proposal.

Этот эпизод доказывает разницу между real bug и безопасным UI drift. Он не входит в
первые 90 секунд, чтобы не размывать главный false-green момент.

## Proof Report как визуальный герой

Главный кадр — не терминал и не chatbot. Это локальный self-contained report с тремя
синхронизированными областями:

```text
┌──────────────────── Proof Card ────────────────────┐
│ real_bug · high confidence · claim persisted      │
├──────────────┬──────────────────┬──────────────────┤
│ User intent  │ Evidence timeline│ Independent truth│
│ create item  │ click → POST 201 │ GET → 404        │
│ UI: visible  │ toast → UI card  │ diff: missing ID │
├──────────────┴──────────────────┴──────────────────┤
│ Next safe action: fix product · rerun 1 test      │
└────────────────────────────────────────────────────┘
```

Обязательные свойства:

- один экран отвечает «что обещали, что произошло, почему verdict такой»;
- claim ID остаётся видимым от PlanSpec до final proof;
- evidence имеет provenance и timestamps;
- redaction status виден, canary values никогда не отображаются;
- report открывается локально без аккаунта и внешней сети;
- raw JSONL и machine-readable verdict доступны рядом, а не спрятаны.

## Truth и честность демонстрации

Demo считается недействительным, если выполняется хотя бы одно условие:

- baseline и Testence получают разное состояние или requirement;
- defect включён только для baseline arm либо скрыт от опубликованного repository;
- verdict заранее захардкожен под имя сценария;
- в видео показан другой run, чем приложенные raw artifacts;
- Testence исправляет assertion так, чтобы настоящий defect стал зелёным;
- failure обнаруживается только потому, что Testence знает seed flag;
- секреты или пользовательские данные попадают в report.

Для каждого публичного run публикуются commit SHA, scenario ID, environment manifest,
PlanSpec, source diff, test, ledger, verdict и report checksum.

## Demo assets

Перед launch должны существовать:

- отдельный публичный demo repository;
- healthy control и два маленьких reviewable defect patches;
- одна команда запуска на Windows, Linux и macOS либо честно заявленная матрица;
- записанный real-time run и 90-секундный cut;
- статичный screenshot Proof Card для README и статей;
- ASCII/текстовый fallback для терминала;
- raw artifact bundle с checksums;
- script, который повторяет только детерминированную часть без coding agent;
- раздел «limitations and how this demo can mislead».

## Acceptance criteria

Demo готов, когда:

- пять последовательных frozen runs дают одинаковый outcome и right reason;
- baseline зелёный, Testence красный на главном defect и оба зелёные на control;
- новый пользователь воспроизводит сценарий не более чем за 10 минут без signup;
- coding agent получает первый trustworthy proof не более чем за 15 минут;
- Testence после product fix становится зелёным без ослабления claims;
- extended drift даёт proposal, но не скрытое изменение;
- canary scan всех артефактов зелёный;
- два внешних человека воспроизводят demo по README;
- весь hero cut можно проверить по опубликованному одному run ID.

## Что не входит в launch demo

- сравнение десятка коммерческих платформ;
- cross-browser matrix как главный сюжет;
- visual regression, mobile device cloud или accessibility audit;
- длинная генерация набора из десятков тестов;
- MCP как обязательное условие;
- hosted dashboard;
- заявления `200× faster` или «нулевые false greens вообще».

Эти функции могут появляться в deep dive, только если уже доказаны, но не должны
отвлекать от единственного сообщения: **зелёный UI ещё не является доказательством
достигнутого результата**.

## Порядок реализации

1. Зафиксировать demo repository, requirement, claims и два truth patches.
2. **Готово:** реализовать PlanSpec/verdict schemas и claim propagation.
3. Собрать один полный flow в одном coding agent.
4. Сделать Proof Card и redaction gate.
5. Добавить baseline runner и frozen demo command.
6. Провести пять внутренних и два внешних воспроизведения.
7. Только после этого записывать финальный hero cut.
