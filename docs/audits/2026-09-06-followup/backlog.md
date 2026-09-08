# Очередь следующего этапа Testence

Основание: [аудит](audit.md). Нормативная приёмка: [ТЗ R1 v1.1](release-spec.md), сохраняющее R01–R24 предыдущей версии. Ни одна строка ниже не означает уже выполненную работу. Это локальная очередь для переноса в issues; внешние issues автоматически не создавались.

Роли владельцев указаны для планирования. Конкретные люди назначаются перед началом milestone. Размеры S/M/L — относительная сложность, а не дни: S локальная совместимость, M связанная группа модулей, L архитектурная/внешняя приёмка. L разбивается после design spike, до реализации.

Текущий прогресс: **T01–T15, offline-часть T16 и T17–T20 реализованы и локально проверены**;
подробности и ограничения
записаны в [M0 implementation receipt](m0-implementation.md). Для T10 реализовано ядро
origin/cookie/redirect/cache safety, для T11 — containment чтения ledger и evidence pack;
для T12 — общий pre-persist sanitizer, caps и pack manifest. Границы приёмки описаны
в [M1 security receipt](m1-security-implementation.md). Статус
станет привязан к неизменяемому SHA после review/commit. Identity/schema migration
описана в [T06 receipt](t06-identity-schema-implementation.md). Reconciliation, retry,
xdist restart и fail-closed ledger/manifest recovery описаны в
[T07–T08 receipt](t07-t08-lifecycle-integrity-implementation.md). Assertion/assurance
foundation описан в [T09 receipt](t09-assurance-implementation.md). Expected-state,
operation correlation и timing corpus описаны в
[T13 receipt](t13-expected-state-implementation.md). Immutable verdict bindings,
JSON Pointer validation и safe repair proof описаны в
[T14 receipt](t14-bound-verdict-repair-implementation.md).
[T15 receipt](t15-allure-consumer-implementation.md) фиксирует полную Allure
projection и реальный pinned consumer report. Fail-closed selective execution описан в
[T16 receipt](t16-testplan-implementation.md); live TestOps tenant gate открыт.
[T17 receipt](t17-ci-delivery-implementation.md) фиксирует раздельные CI outcomes,
JUnit/CTRF parity и идемпотентный delivery retry.
[T18 receipt](t18-application-services-implementation.md) фиксирует application CLI,
атомарную отправку verdict и synthetic consumer workflow из установленного wheel.
[T19 receipt](t19-runtime-isolation-implementation.md) фиксирует isolated-by-default
context/auth/data lifecycle, browser ownership и fresh/warm parity на Windows;
Linux/real-target role-switch acceptance остаётся внешней границей.
[T20 receipt](t20-capability-actions-implementation.md) фиксирует versioned capability
preflight, strict action semantics, platform-neutral fake и Chromium web matrix;
Linux/custom-engine acceptance остаётся внешней границей.
[T21 receipt](t21-quality-pack-implementation.md) фиксирует локальный versioned pack,
три namespace, intentional conflict/override, rollback и actionable summary;
real-repository/TMS U5 acceptance остаётся внешней границей.
Остальные части M2+
открыты с явно записанными external acceptance boundaries.

## M0. Первая очередь

| ID | P | Задача и проверяемый выход | R/F | Зависит от | Роль | Размер |
|---|---|---|---|---|---|---|
| T01 | P1 | Отформатировать два файла; согласовать dev setup с обязательным xdist-test; весь quality gate проходит | F08; R19/R20 | — | Core | S |
| T02 | P0 | Общий normalizer legacy/new statuses; corpus принимает 10 passed; metrics не создаёт flake из pass/passed | F04; R17/R18/R20 | — | Core + Benchmark | M |
| T03 | P0 | Grader отвергает exit=2/0 claims, incomplete/unknown scope; required denominator обязателен | F04; R03/R18 | — | Benchmark + SDET | M |
| T04 | P0 | Перенести crash/duplicate/-x/interruption probes в regression suite с desired expectations; сохранить исходные failing receipts | F01–F03; R01–R03 | — | SDET | M |
| T05 | P1 | Исправить README verdict и misleading TestOps/CI recipe, связать актуальный аудит; working snippets валидируются | F07/F08; R15/R20 | — | Docs + Integrations | S |

T04 добавляет защиты вместе с исправлениями, не оставляя main с намеренно падающим suite. M0 не считается завершением truth/safety; он восстанавливает пригодность проверок и честные текущие claims.

## M1. Truth и safety

| ID | P | Задача и проверяемый выход | R/F | Зависит от | Роль | Размер |
|---|---|---|---|---|---|---|
| T06 | P0 | Identity/schema ADR, `/2` models и legacy adapter; IDs/parameters/attempts одинаковы у всех consumers | F02/F08; R02/R03 | T02 | Core | L |
| T07 | P0 | Controller-owned reconciliation: crash, restart, retries, not_run, worker shards; нет false green и пропавшего selected scope | F01/F03; R01/R03 | T04/T06 | Core + SDET | L |
| T08 | P0 | Recovery/validation ledger и manifests; partial/corrupt/empty/duplicate/unknown version fail closed | F01; R03/R08 | T06/T07 | Core | M |
| T09 | P0 | Assertions и assurance gate; pass без required proof → unverified; schema parity и plan digests | F05; R04 | T06/T08 | Core + QA | L |
| T10 | P0 | Origin/cookie/redirect-safe API auth; opt-in cache TTL/role identity; login-refresh-logout negatives | F06; R06 | — | Core + Security | L |
| T11 | P0 | Resolved containment на import/export/retention; traversal/absolute/UNC/link cases не читают внешний файл | F06; R07 | — | Security + Core | M |
| T12 | P0 | Sanitize before persist, capture caps и portable manifest; canaries отсутствуют во всех sinks | F06; R07/R08 | T06/T10/T11 | Security + Core | L |

Containment и auth fixes не должны ждать завершения большой миграции identity. Общий manifest и полный safety receipt принимаются после интеграции T06–T12.

Локальная реализация T10–T12 пока не означает `Done`: нужен прогон link/path matrix на
Windows и Linux, независимый security review, browser refresh/logout integration и
retention boundary, а также visual masking screenshot и проверка произвольных PII.
Эти выходы остаются частью нормативной приёмки T10–T12.

## M2. Один законченный QA-сценарий

| ID | P | Задача и проверяемый выход | R-ID | Зависит от | Роль | Размер |
|---|---|---|---|---|---|---|
| T13 | P0 | Expected-state oracle, request correlation, deadline/window; optimistic/stale/empty/wrong-role/rollback corpus | R05/R11 | T09/T10/T12 | SDET + Core | L |
| T14 | P0 | Bound verdict, pointer resolution, proposal base hash и safe repair proof; no silent weakening | R09 | T09/T12/T13 | Agent UX + QA | L |
| T15 | P0 | Allure identity/params/attempts/fixtures/status projection; реально открыть поддерживаемый consumer report | R13 | T06–T09/T12 | Integrations | L |
| T16 | P0 | Testplan selection и namespace mapping; 1-of-8/empty/invalid plan contract; live round trip | R14 | T15; tenant для live части | Integrations + QA | L |
| T17 | P0 | CI test/quality/upload exits, explicit run identity, JUnit/CTRF mapping и retry delivery | R15 | T07/T08/T15 | Integrations + CI | M |
| T18 | P1 | doctor/init/inspect/submit application services и wheel-based synthetic demo; existing-suite opt-in smoke | R16/R20 | T09/T12–T14 | Agent UX + Docs | L |

Offline часть T16 полностью реализуема до выдачи tenant. Live часть остаётся явно непринятой без настоящего consumer receipt. M2 показывает один проект от требования до selective run и reviewed repair.

## M3. Масштаб, web и измерения

| ID | P | Задача и проверяемый выход | R-ID | Зависит от | Роль | Размер |
|---|---|---|---|---|---|---|
| T19 | P0 | Isolated context/data/role, CI process ownership и warm/fresh parity | R10 | T07/T10/T12 | Engine + SDET | L |
| T20 | P0/P1 | Strict actions + web capability matrix и fake engine conformance | R11/R12/R22 | T13/T19 | Engine + SDET | L |
| T21 | P1 | Versioned quality pack: 3 repos, conflicts/rollback, namespaces, actionable QA summary | R21 | T09/T14–T19 | QA platform | L |
| T22 | P1 | Два реальных agent clients на одном pack; install/update/submit receipts | R16 | T14/T18 | Agent UX + QA | M |
| T23 | P0 | Frozen independent corpus: 40 cases + 2 OSS SUT; grader mutants и holdout | R18 | T03/T07–T14/T20; D01 | Benchmark + внешний reviewer | L |
| T24 | P1 | Raw perf/resource/flake protocol и budgets; 10k-results/flood/warm/fresh runs | R17 | T02/T12/T19/T20/T23 | Performance + SDET | M |

## M4. Внешняя приёмка и release candidate

| ID | P | Задача и проверяемый выход | R-ID | Зависит от | Роль | Размер |
|---|---|---|---|---|---|---|
| T25 | P1 | RC CI matrix, minimum-deps, installed-wheel browser smoke, schemas/corpus/docs gates, SBOM/provenance | R19 | T15/T17/T20/T23/T24 | Release + CI | L |
| T26 | P1 | Единые support/launch manifest, EN/RU validated docs, 90-second video и one-command demo | R20/R24 | T18/T21/T22/T25 | Docs + Product | M |
| T27 | P1 | Пилот: 5 users/3 teams/2 reproduction, week-return и measured QA effort | R23 | T16/T18/T21–T26; D02 | Product + QA champions | L |
| T28 | P1 | Rights/tree-history/dependency review, реальный security channel, community/support policy | R19/R24 | D01; security fixes до final scan | Security + Maintainer | L |
| T29 | P1 | Собрать RC receipts G1–G8, повторить релевантные проверки на одном SHA, owner go/no-go и rollback | R24 | T01–T28 | Release owner | M |

### Discovery с начала этапа

- **D01:** выбрать два допустимых OSS targets, зафиксировать license/commit/reset и сценарии; назначить независимых truth reviewers. Owner: Benchmark + Maintainer. Не публиковать private targets.
- **D02:** назначить владельцев, подготовить пилотный протокол и список добровольных участников; обеспечить test tenant и доступы. Owner: Product + Integrations. Отправка приглашений требует отдельного разрешения; этот backlog не выполняет внешние действия.
- **D03:** определить support policy и действующий security contact; проверить доступность package/repository release инфраструктуры. Owner: Release + Security. Настройки и публикация не меняются автоматически.

## Шаблон issue и Done

Каждое issue содержит проблему/сценарий, R/F-ID, scope/out-of-scope, named owner, зависимости, public API/compatibility impact, consumer-facing example, adversarial cases, expected/observed и ссылки на receipts. Для code work Done: реализация + docs + meaningful consumer tests + review. Для внешней приёмки — дополнительно фактический consumer/participant receipt.

Проверки выполняются на зафиксированных версиях; receipt имеет SHA и digest inputs. Открытая критическая finding, неполный scope или отсутствующая внешняя приёмка не превращаются в PASS при закрытии issue. Final release Done определяется G1–G8, а не суммой T-ID.
