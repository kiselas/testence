# ТЗ Testence R1 v1.1: доверенный QA workflow и OSS release candidate

Дата: 6 сентября 2026. Основание: [повторный аудит HEAD `7be8d02`](audit.md).
Целевая версия продукта: `0.1.0a1`. Статус: **спецификация следующего этапа, предложенная к реализации**.

Этот документ актуализирует порядок и детализацию [R1 v1.0](../2026-09-06/release-spec.md). Все R01–R24, U1–U5 и G1–G8 сохраняют обязательность и исходные критерии. Требования не считаются выполненными по факту наличия похожего модуля. Новые требования уточняют выявленные gaps; масштаб R1 не понижается молча. Конкретная очередь — [backlog](backlog.md).

**Это не R2.** Основной пользовательский результат прежнего R1 ещё не принят. Firefox/WebKit, visual/a11y adapters, TypeScript adoption и mobile остаются последующими направлениями.

## 1. Результат для пользователей

QA/SDET задаёт repo-owned правила и ожидаемые результаты для нескольких проектов. Разработчик или coding agent создаёт обычные pytest-тесты. Testence исполняет их без обязательных LLM calls, сохраняет полные факты, проверяет достаточность доказательств и доставляет результаты в Allure/TestOps/CI. Исправление теста представляет собой проверяемый diff, а решение о качестве не зависит от уверенности модели.

Следующий этап должен дать пять законченных возможностей:

1. Новый пользователь устанавливает wheel и проходит synthetic demo без внутренних доступов; видит один достоверный green и одно объяснимое failure.
2. Новый тест принимается по expected assertions и sensitivity proof на healthy/defect/control, а не только по успешному запуску.
3. Любой выбранный case и любая попытка имеют однозначный исход, включая worker crash, abort и неисполненный остаток.
4. QA выбирает scope в TestOps и получает результаты именно этого scope с сохранённой историей и всеми attempts.
5. Один QA применяет одну версию quality pack в трёх репозиториях и разбирает общую очередь решений без смешивания credentials или сырых артефактов.

### Границы

Включены: Chromium web на Windows/Linux, pytest integration, evidence/proof/policy, Allure Report/TestOps, CTRF и pytest-native JUnit recipe, CLI/skills, переносимый OSS package.

Исключены: свой TMS/RBAC сервер, hosted dashboard, managed cloud, свой browser driver, Android/iOS engines, переписывание на Rust/TypeScript, обязательные LLM calls в replay, автоматическое изменение требований, полноценная API/load testing platform. Browser permissions и arbitrary Python не становятся безопасными только благодаря config policy: граница доверия исполняемому коду сохраняется.

## 2. Архитектурные решения этапа

Сохранить engine/evidence/export separation и pytest-native DSL. Вынести общий application layer `collect`, `run`, `inspect`, `validate`, `submit`, `export`, используемый CLI и agent integrations. Имена сервисов — целевой контракт; это не список уже доступных команд.

### 2.1. Identity

| Поле | Обязательная семантика |
|---|---|
| `project_id` | Repo-owned namespace, независимый от checkout path |
| `case_id` | Логический case; явный ID переживает rename |
| `variant_id` | Канонические параметры browser/role/data; секреты не включаются открытым текстом |
| `run_id` | Один запуск; уникален и явно передаётся consumers |
| `attempt_id` | Отдельная попытка case+variant; retry не перезаписывает предыдущую |
| `event_id` | Уникальность в run с worker и sequence |
| `claim_id`, `assertion_id` | Требование и конкретная исполняемая проверка |
| digests | Plan, test, policy, pack и SUT revision; unknown явно обозначен |
| external IDs | TMS namespace → case ID; не смешиваются разные проекты |

Полный pytest nodeid остаётся source locator. Display name не является ключом коллекции, пути, verdict или истории. Result UUID включает run/case/variant/attempt; history identity стабильна по документированным параметрам. Все потребители используют один normalizer/model.

### 2.2. Два независимых результата

Execution: `passed`, `failed`, `broken`, `skipped`, `aborted`, `not_run`; phase и xfail/xpass/retry/quarantine reason хранятся отдельно.

Assurance: `verified`, `violated`, `inconclusive`, `unverified`. `passed` без required proof остаётся `unverified`. Недоступный oracle не классифицируется как product bug автоматически. Diagnosis не переписывает immutable execution outcome.

`verified` требует завершённого scope, всех обязательных успешно исполненных assertions, допустимой policy и достаточного evidence. Optional assertions не увеличивают required denominator. Skipped/quarantined/retried результаты сохраняют причины и не скрывают исходную failure.

### 2.3. Миграция

Целевые контракты: ledger `testence/2`, PlanSpec `/2`, Verdict `/2`, versioned run/pack/policy/proposal manifests. Legacy `/1` читается compatibility adapter; spellings `pass/passed`, `fail/failed` нормализуются на входе всех readers. Недостающие proofs не восстанавливаются выдуманными событиями: legacy evidence отмечается `unverified`.

Не добавлять несовместимую семантику в `/1` без явной migration. Один compatibility corpus проверяет Python/JSON validators, metrics, report, exporters, corpus grader и packaged examples. Digests обнаруживают рассогласование, но не являются доказательством честности произвольного Python-кода.

## 3. Пакеты работ и измеримая приёмка

Каждый пакет заканчивается демонстрацией consumer-сценария и receipt с SHA, версиями, командой, expected/observed, exit и артефактами. Unit tests дополняют, но не заменяют эти проверки.

### E01. Завершённое выполнение и единая правда о результате

**Приоритет P0.** R01–R03, часть R13/R15/R17/R18/R20. Основание F01–F04/F08.

Доработать уже внедрённые hooks. На collection фиксировать collected/selected/deselected и причины. На finish связывать controller и worker facts с manifest выбранных cases/attempts. Различать worker terminal и окончательный run terminal: один run получает одну итоговую сводку. Worker crash относится к конкретной выполнявшейся попытке; выбранный, но не начавшийся case получает `not_run` с причиной.

Отсутствие terminal event никогда не даёт `passed`. Unknown status, пустая директория, неполный run, corrupt ledger или отсутствие worker shard не дают успешного quality exit. Reader восстанавливает целые записи до оборванного хвоста с явным damaged/incomplete status; corruption посередине не игнорируется. Collision ID отклоняется до выполнения.

**Обязательные acceptance fixtures:**

- Все lifecycle outcomes из R01: до/после `ex`, teardown, collection error/skip, no-ex, xfail и оба xpass, нулевой scope.
- Два одноимённых `test_save`: один failed и один passed остаются двумя cases во всех consumers.
- `-x`: из трёх selected один failed и два not_run; Ctrl+C/KeyboardInterrupt: started aborted и объяснённый остаток. Программная и реальная process-interruption проверки учитывают особенности ОС.
- Worker crash при `-n 2` и `-n 4`, restart/retry и missing shard: результат crashed attempt не green; последующая успешная попытка не стирает первую.
- 200 parameter variants, Unicode, длинные совпадающие префиксы, два проекта, rename с case_id; counts/paths/attempts не сливаются.
- Wrong/duplicate/missing events, export во время записи, unsupported schema: диагностированный отказ или incomplete, никогда success.
- Legacy `pass` и новый `passed` при одинаковом test/code не создают flake; 10 synthetic passed cases остаются healthy для corpus. Empty/crashed control отклоняется evaluator.

**Выход:** fixture → ledger → reconciled summary → HTML/Allure/CTRF/JUnit mapping дают согласованный результат. Если формат не имеет native `aborted/not_run`, mapping явно документирован и metadata сохраняет причину. JUnit можно получать штатным pytest; runtime exit и полнота проверяются общим quality gate.

### E02. Безопасная авторизация и артефакты

**Приоритет P0.** R06–R08 и часть R10. Основание F06, A12/A18/A19.

API использует allowlisted origins и cookie domain/path/secure semantics. Redirect на другой origin и HTTPS→HTTP не получает credentials. Синхронизировать login/refresh/logout/role между browser и oracle. Cache выключен по умолчанию; opt-in cache scoped по project/origin/role/environment/strategy, с TTL, identity probe, понятной invalidation и OS permissions.

Один sanitizer на persist boundary обрабатывает ledger, packs, request/response/URL, console, DOM/ARIA, traceback, config, exports, reports, `full-*`, logs. Screenshot/trace получают отдельную политику capture/masking/omission; отсутствие redaction для binary не маскируется обещанием безопасного pack. Если безопасный capture невозможен, артефакт не публикуется, proof completeness уменьшается.

При read/import/export/retention проверять resolved containment, traversal, absolute/UNC paths, symlink/junction. У каждого артефакта — размер, digest, type, captured/omitted/truncated reason. Caps применяются при acquisition, а не после полной загрузки большого body в память. Потеря evidence не подменяет pytest outcome.

**Приёмка:** synthetic canary suite для всех sinks; foreign-origin/redirect/cookie/role negative tests; path attacks на Windows/Linux; malformed cache и expired identity; отказ диска/permissions; network/console flood и large body в объявленных caps; экспорт переносимого pack без чтения за его пределами; retention preview и удаление только разрешённых task artifacts. Никаких реальных секретов в fixtures.

### E03. Исполнимые требования, expected-state oracles и безопасный repair

**Приоритет P0.** R04/R05/R09 и proof-часть R11/R18.

PlanSpec хранит requirement revision, risk, actor/role, preconditions, seed/cleanup references, expected outcomes, assertion/oracle inventory, scenarios и exclusions. Assertion event несёт expected/actual либо typed redacted values, claim IDs, oracle kind/source, outcome, time и source location. Binding case к claim отдельно от доказательства исполнения assertion.

Persistence oracle делает fresh authoritative read конкретной сущности и сравнивает с expected predicate из требования. Сопоставление request с action учитывает mark, method, origin/path и predicate/correlation ID, включая GraphQL. Для eventual consistency повторяются безопасные reads до deadline; mutation не повторяется. Negative checks имеют observation window. Пустой/HTML/unauthorized/stale oracle не считается доказательством.

Verdict привязан к run/case/variant/attempt и digests plan/test/policy/pack. Проверяются JSON Pointer и event references, включая их принадлежность нужной попытке. Недоверенный текст артефакта не становится инструкцией агенту. Repair содержит base hash, diff, причины, изменённые claims/locators и proof runs. Утверждения, роль, scope, skip/retry policy и required evidence нельзя ослабить под видом locator repair.

**Приёмка:** пустое тело, неисполнённая assertion branch, duplicate/unknown claim, обязательный missing oracle → не verified; optimistic success, stale equal UI/API, wrong entity/role, aborted mutation, delayed commit/rollback, 401/403/404/500 → корректная классификация. Несуществующая evidence pointer и stale digest отклоняются. Repair проходит healthy/defect/harmless proof, не скрывает исходный product defect; при отсутствии доказательств формируется reasoned abstention.

Для critical journey planner рассматривает happy/negative, equivalence/boundaries, decision table/permissions, state transitions, persistence, concurrency/idempotency, metamorphic properties, mutation/control и fault injection. Неприменимость объясняется. Это выбор рисков, не механическая генерация всех комбинаций. Coverage строится по явно выбранному requirement inventory; новая revision помечает старое proof как potentially stale.

### E04. Надёжный web runtime и эксплуатационные границы

**Приоритет P0 для R10/R11, P1 для остального обязательного scope.** R10–R12/R17/R22.

Изолированный context/test-data namespace по умолчанию в CI; session browser reuse допустим при доказанной изоляции. Auth/seed/cleanup adapters имеют владельца и lifecycle. Attached/warm — явный authoring profile; он не принимает владение чужим browser и не убивает его при cleanup. Собственные browser/context/ports закрываются после failure и interrupt в CI.

Strict targets отвергают неоднозначность. `first`, `force`, fast readiness и другие ослабления — явный opt-in с записью в evidence и влиянием на assurance. Добавить/довести conformance: frame, open shadow DOM, popup/multiple page, upload/download, dialog, keyboard/focus, scroll, download ownership. Неподдерживаемый capability даёт typed error на preflight, не silent skip.

Platform-neutral contracts session/action/observation/evidence/export отделены от optional DOM/network/frames/files/visual/native capabilities. Fake engine без CDP/DOM должен пройти общий lifecycle/export conformance; browser-only action на нём корректно отвергается. R1 поставляет только web backend.

**Приёмка:** Chromium на Windows/Linux; serial/xdist parity; повторная смена роли/проекта; reverse-order runs и isolated data cleanup; отсутствие оставленных собственных процессов в CI; fixtures всех заявленных web capabilities. Warm против fresh сравнивается по эквивалентному scope, состоянию и proof.

Resource/latency protocol фиксируется до оптимизаций: n, raw samples, окружение, caps RSS/CPU/disk/artifact size, p50/p95, cold/warm и failure storm. Проверять как минимум 10k synthetic exported results и профиль больших bodies. Численные resource caps определяются первым profile и фиксируются в budget-файле до gate; отсутствие утверждённого budget не даёт PASS. Текущие benchmark budgets не ослабляются без отдельного обоснованного изменения. Оптимизации не покупают скорость пропуском assertions или isolation.

### E05. Allure/TestOps/CI как законченный пользовательский путь

**Приоритет P0.** R13–R15, часть R19/R20/R21. Зависит от E01/E02/E03.

Allure projection включает case/history/result identities, params, owner/risk/requirements/issue links, all attempts, fixtures и redacted attachments. Экспорт детерминирован, повтор не дублирует результаты. Нужен consumer test с реальным закреплённым Allure Report, а не только JSON goldens.

TestOps adapter читает `ALLURE_TESTPLAN_PATH`, валидирует версию, namespace, IDs/selectors и разрешает scope до execution. Invalid/empty/unresolved/ambiguous selection не превращается в запуск всего suite. Пустой scope допускается только явной documented no-op policy. Выполняются только выбранные случаи и корректные variants.

Uploads привязаны к явному run/launch/job-run, проверяют outcome/status и сохраняют receipts; повтор должен иметь определённую idempotent семантику. Результат upload не скрывает failure теста или proof. CLI/CI отдельно фиксируют test exit, quality exit и delivery outcome; финальный job не становится green после successful upload failed/incomplete run. `latest directory` не используется как identity.

**Приёмка:** plan выбирает 1 из 8 → ровно 1 выбранный test; пустой/невалидный plan → fail closed; один case в двух variants и retry → корректная история. Repeated export/upload, upload timeout, wrong project и missing attachments имеют проверяемые исходы. Реальный TestOps test tenant подтверждает select → CI → upload → launch/history links, со скриншотами или sanitized API receipts и версиями consumers. Synthetic fixtures не заменяют этот gate. JUnit/CTRF проверяются на том же lifecycle inventory.

Текущий документ не разрешает включать production integrations или отправлять сообщения внешним командам. Нужный тестовый tenant и доступ предоставляет владелец перед live acceptance; до этого можно полностью реализовать offline fixtures и CI recipe.

### E06. Onboarding, portable agents и один QA на трёх проектах

**Приоритет P1, обязателен R1.** R16/R20/R21, пользовательская часть R23.

Целевые команды (пока требования к API, не работающий quickstart): `testence doctor --json`, `testence init`, `testence run`, `testence inspect`, `testence verdict submit`, `testence agent init/status/update`. Синтаксис фиксируется в CLI contract ADR до реализации. Изменения файлов имеют manifest и поддерживают reviewable update/rollback; секреты генерируемым scaffold не передаются.

Doctor объясняет missing browser, Python/runtime compatibility, writable paths, unsupported capabilities и конфликт config. Human output actionable; JSON envelope versioned, errors typed, exit codes стабильны. Existing pytest project без opt-in сохраняет обычное поведение, без неожиданных capture/config требований. Lifecycle для opt-in case не требует fixture `ex`.

Quickstart из wheel/HTTPS не зависит от Git/SSH login, internal SUT или обязательных незапакованных fixtures. Одинаковые validated examples генерируют README, EN/RU guides и CLI help references. Пользователь получает deterministic demo green и intentional failure/pack/report. Два реальных agent clients на закреплённых версиях работают с одним versioned pack; managed submit валидирует binding и review state.

Quality pack хранит policy, owner/risk labels, oracle recipes, fixture interfaces и selection conventions. Version pin + checksum/compatibility; override имеет reason/owner/expiry. Requirements/TMS принадлежат QA; code/policy Git; execution immutable run; diagnosis/repair — proposals. Import создаёт mapping/diff и конфликтный отчёт, не overwrites QA/Git source.

**Приёмка:** U1/U2/U4/U5; три независимых repo/project IDs с одинаковыми именами cases, разными credentials/TMS/owners. Обновление pack порождает три понятных diff и один intentional conflict; rollback сохраняет историю. QA видит only-actionable summary: new violation, missing/stale proof, flake/quarantine expiry, awaiting/rejected repair, coverage gap. Фильтры project/owner/risk/role/case работают. Cross-project artifact/auth access отвергается.

### E07. Независимое доказательство качества и полезности

**Приоритет P0 для достоверного evaluator; P1 для полного пилота.** R17/R18/R23.

Сначала устранить оба дефекта grader: false green на empty/crashed control и false red на `passed`. Затем зафиксировать protocol/truth labels до tuning; evaluator проверяет own expected scope, pytest exit, terminal events, assertions и source truth независимо от summary Testence. Mutants самого runner — default pass, wrong identity, dropped oracle — обязательно обнаруживаются.

Минимум **40 уникальных correctness cases**: 20 product defects, 10 healthy/harmless controls, 5 repairable drift, 5 ambiguous/infrastructure. Повторы не являются новыми cases. Включить F01–F07, optimistic UI, lost update, delayed rollback, auth/role, wrong entity, stale data, empty oracle, duplicate locator, swallowed first click, aborted mutation и capture failures.

Плюс **2 licensed OSS приложения на разных стэках**, каждое с create/persist, search/filter, update/delete; healthy/bug/harmless revisions. Зафиксировать commits, licenses, containers/fixtures и reset. Два человека ревьюят truth; hidden holdout не используется для tuning после freeze. Private targets не публикуются как demo.

**Technical acceptance:** zero observed false green на release-critical defects и zero unsafe repair; healthy controls проходят; incomplete не green; ambiguous даёт reasoned abstention. Публикуются detection/right-reason/abstention/completion rates, denominators, intervals и raw samples. «Ноль наблюдений» не обещает нулевой риск для всех приложений. Независимый reviewer воспроизводит deterministic subset.

**Product acceptance:** 3 внешние команды, одна — single QA/three projects; 5 новых пользователей; 4/5 проходят demo ≤15 минут без помощи автора; ≥2/3 команд самостоятельно добавляют второй сценарий и возвращаются на следующей неделе; одна выполняет TestOps selective launch; 2 независимых reproduction. Измеряются setup effort, QA review/triage minutes, accepted scenarios, gaps и review overrides относительно well-configured pytest/Playwright+Allure с равным доступом к API oracle.

Выбор OSS targets и поиск согласованных пилотов начинаются в discovery, не после последнего инженерного PR. Контакты/согласия организует владелец. При провале критериев — исправление onboarding/scope и повтор acceptance либо остановка рекламного launch; результаты не переписываются задним числом.

### E08. Публичный репозиторий, дистрибуция и сопровождение

**Приоритет P1, обязателен R1.** R19/R20/R24.

Сохранить Apache-2.0 как уже принятое решение. Подготовить реестр included assets/fixtures/datasets/dependencies с происхождением и правами; NOTICE при необходимости. Tree/history secret scan до публикации, dependency/license inventory и triage findings. Если найдены реальные секреты, владелец проводит rotation и remediation history; удалить строку из текущего дерева недостаточно. В публичные demo допускаются synthetic или разрешённые данные.

Доработать существующие CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, CODEOWNERS, templates, roadmap: действующий private reporting channel, конкретные maintainers, support window, versioning/deprecation/migration/rollback policy. SECURITY не считает канал существующим только по тексту «when available». GitHub private vulnerability reporting включается отдельно в настройках репозитория; зафиксировать факт доступности и ответственного. [GitHub Docs](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configure-for-a-repository).

CI включает Windows/Linux × минимальный поддерживаемый Python и закреплённый основной; dependency-minimum job отдельно от locked job. Проверяются format/lint/types/unit, consumer lifecycle/xdist, browser conformance, schema parity, critical corpus, budgets, snippets/links, wheel/sdist и installed-wheel smoke вне checkout. Нет ложного обещания поддержки всех будущих dependency versions из-за `>=`.

Release pipeline строит wheel/sdist и SBOM, сохраняет checksums, changelog и provenance. Подготовить trusted publishing с минимальными job permissions и protected release environment; наличие build step не означает публикацию. PyPI attestations связывают distribution digest с publisher identity, но не гарантируют качество runtime. [PyPI attestations](https://docs.pypi.org/attestations/), [security model](https://docs.pypi.org/attestations/security-model/).

**Приёмка:** fresh user проходит install/demo/report без Git/SSH credentials; wheel содержит обязательные schemas/skills/resources; sdist rebuild проверен; docs EN обязательны для внешнего UX, RU нормативно согласованы; все promised commands валидированы, отсутствуют `|| true` с потерей exit и placeholders в работающем quickstart. 90-second video и one-command demo воспроизводимы. Нет untriaged known critical dependency/security findings. Maintainer и рабочее окно объявлены; release owner принимает decision по receipts.

## 4. Очерёдность и конечность объёма

| Milestone | Содержание | Условие выхода |
|---|---|---|
| M0. Совместимость текущего HEAD | Format, corpus status normalizer, false-green evaluator guard, lifecycle reproductions, docs correction | Локальные quality checks зелёные; новые reproductions стали regression guards; текущие риски явно видны |
| M1. Truth и safety | E01/E02 + assertion/proof foundation E03 | F01–F06 закрыты consumer proof; schemas/identity зафиксированы; G1/G2 receipts |
| M2. Вертикальный QA-сценарий | E03/E05/E06 для одного проекта | Plan → test → defect proof → pack → verdict/repair → selective TestOps launch проходит end to end |
| M3. Масштаб и web acceptance | E04, оставшаяся E06, E07 corpus | Windows/Linux conformance, 3 repos, 40 cases + 2 OSS SUT, resource budgets, 2 agent clients |
| M4. Внешняя приёмка и OSS RC | E07 pilot, E08 final, повтор всех gates на RC | Все G1–G8 на одном RC, release manifest и owner decision |

Docs/package/scans развиваются с M0; OSS/pilot discovery начинается сразу. M1 не должен ждать внешнего tenant. Полный G4 и G7 без внешних подтверждений не закрываются. Это порядок командной работы, не поручение запускать параллельных агентов.

Роли до старта milestone назначаются конкретным людям: core maintainer, SDET, security reviewer, integrations owner, QA/product owner, release maintainer. Независимое review измерений и приёмки не заменяется самопроверкой автора. Даты и размер команды согласуются после M1/schema spike; прежний ориентир сроков не является обязательством. Не расширять milestone соседними feature requests без пересмотра scope.

## 5. Release gates

Нумерация прежняя. Gates исполняются на одном RC SHA; более ранние receipts сохраняются как история и при необходимости переисполняются. Без доказанной применимости receipt не переносится автоматически через изменения runtime, schema, fixture или зависимости.

| Gate | Требование выхода | Минимальный receipt |
|---|---|---|
| G1 Truth | Lifecycle/identity/completion/claims/oracle достоверны | Consumer matrix, crash/collision/missing-proof mutants, summary reconciliation |
| G2 Safety | Credentials и retained artifacts изолированы | Canary/origin/path/cache/retention suite + review |
| G3 Web reliability | Заявленная web matrix и cleanup работают | Windows/Linux Chromium, serial/xdist, contexts/data/process receipts, fake engine |
| G4 Integrations | Allure/TestOps/CI/multi-project mapping принят | Реальный Allure consumer и test-tenant selection/upload/history receipt |
| G5 Agent workflow | Два клиента используют один безопасный контракт | Версии, plans/tests/runs/verdicts/proposals, review/proof receipts |
| G6 Measured quality | Frozen corpus и budgets приняты | 40 cases, 2 OSS SUT, raw samples, evaluator mutants, independent reproduction |
| G7 Adoption | Onboarding и повторное использование доказаны | 5 sessions, 3 pilots, week-return, TestOps и single-QA/3-project acceptance |
| G8 Distribution | Пакет, docs, security/governance готовы | RC CI, wheel/sdist smoke, scans/inventory, security channel, release manifest |

**R1 Done:** код + docs + consumer tests + review + receipt, принятые R01–R24 и G1–G8. Счётчик passing tests/closed issues или video сам по себе не закрывает gate. P0 gaps не waiver-ятся производительностью или marketing readiness.

## 6. Release manifest и решение о публикации

Версионируемый manifest содержит:

- RC SHA/tag, package versions, wheel/sdist SHA-256, build provenance/SBOM references;
- schema/support/dependency/browser/agent/consumer versions;
- R-ID/G-ID → receipt с expected/observed, командой, exit, датой, owner/reviewer;
- corpus/protocol/truth/OSS fixture revisions, frozen holdout status;
- known limitations, migrations, rollback, security channel и support owner;
- release decision: `go` либо `no-go`, принявший владелец и основания.

Открытие исследовательского pre-alpha репозитория и объявление готового R1 различаются по обещаниям. Если владелец решит открыть исходники до R1, необходимы отдельная security/rights readiness и честные limitations; это не закрывает G1–G8 и не даёт права заявить QA alpha ready. В рамках настоящего ТЗ готовится RC; само ТЗ не является разрешением публиковать packages, менять remote visibility или отправлять внешние сообщения.

## 7. Что должно остаться после этапа

Поддерживаемый Chromium/pytest продукт с доказанным качеством результатов, безопасным evidence и законченным QA workflow; package и документация для независимого пользователя; регрессионная защита критических ошибок; воспроизводимые данные качества/полезности; понятные правила участия и сопровождения.

Переход к R2 выполняется отдельным решением после приёмки R1 и подтверждённого спроса. Следующие кандидаты — Firefox/WebKit, approved visual baselines, a11y adapter и TypeScript adoption. Mobile требует отдельной capability matrix, инфраструктуры и пилотов; он не является условием текущего OSS RC.
