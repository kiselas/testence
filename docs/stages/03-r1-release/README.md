# Этап 3. Завершение Testence R1 и подготовка открытого release candidate

Версия ТЗ: **3.0, 7 сентября 2026**. Целевой продукт: `0.1.0a1`, Chromium/pytest QA preview на Windows/Linux.
Статус: **готово к реализации; задачи этапа ещё не приняты**.

Это третий крупный этап работ, а не третья версия продукта и не R2. Он сохраняет R01–R24, U1–U5 и G1–G8 из [первого ТЗ](../../audits/2026-09-06/release-spec.md) и [уточнения R1 v1.1](../../audits/2026-09-06-followup/release-spec.md). Основание новых задач — [последний аудит A01–A09](../../audits/2026-09-06-result/README.md).

Пакет документов следует выполнять вместе:

| Документ | Назначение |
|---|---|
| Этот файл | Нормативные требования, границы, задачи S3-00–S3-19 |
| [Пособие исполнителю](implementation-guide.md) | Алгоритмы, интерфейсы, опасные упрощения, инструкции для менее опытного агента |
| [Матрица приёмки и порядок работы](acceptance.md) | Зависимости, отрицательные проверки, CI, receipts и переход к Done |
| [Автономное выполнение](autonomy.md) | Самостоятельные решения, ранняя проверка доступов и завершение без промежуточных согласований |
| [Текущий прогресс](progress.md) | Фактические статусы реализации и ссылки на новые проверки |
| [Готовность окружения](readiness.md) | Доступные и внешние зависимости без раскрытия секретов |

## 1. Конечный пользовательский результат

Новый QA устанавливает собранный wheel в чистую среду, выполняет одну demo-команду и получает объяснимый healthy result и обнаруженный дефект сохранения данных. Failure содержит переносимый evidence pack, HTML/Allure output и достаточные сведения для validated verdict. Агент использует тот же pack; исправление теста сохраняет исходный product failure и проходит healthy/defect/harmless proof.

Один QA применяет одну версию quality pack в трёх репозиториях: видит реальные изменения, сохраняет локальные исключения, получает конфликт до изменения управляемых файлов и может восстановить прежнюю проверенную версию. Требования, роли, проекты, попытки и TMS mappings не смешиваются.

Release candidate имеет одну проверяемую цепочку: source revision → distributions → чистые consumer installations → raw checks → gate receipts → решение владельца. Успех валидатора нельзя получить заменой действительных доказательств строками `true` и `passed`.

## 2. Исходное состояние и границы

Аудит изучал незакоммиченное дерево поверх `7be8d025f81d9116ab267c59d440e14b377cfce7`, версию `0.1.0.dev0`. Последний успешный локальный прогон: 339 passed, 2 Windows symlink skips; lint/format/types проходят. Это историческая исходная точка, не критерий приёмки нового изменения. Перед реализацией S3-00 снимает фактический новый snapshot.

Сохраняются существующие lifecycle, identity, assurance, expected-state, export и engine layers. Общие исправления внедряются в них, а не через вторую независимую модель результата. Отсутствие receipt не доказывает отсутствие реализации: сначала воспроизвести требование, затем исправлять обнаруженный gap.

Не входят: новый TMS/RBAC/dashboard, managed cloud, mobile engines, гарантированная Firefox/WebKit matrix, обязательные LLM calls при replay, переписывание на TypeScript/Rust. Исполняемый произвольный Python остаётся доверенным кодом; path containment не объявляется общей sandbox.

Новые команды, JSON fields и модули ниже — **целевые интерфейсы**. Не вставлять их в публичный quickstart как работающие до реализации и проверки `--help`/consumer fixtures. Примерные внутренние имена можно изменить в ADR с сохранением поведения. Требования приёмки так изменять нельзя.

## 3. Непереговорные свойства

1. Ошибка, отсутствующий input, повреждённый artifact или неподтверждённая независимость не дают успешный quality/release outcome.
2. Validate/read-only mode не исправляет inputs и не обновляет digests. Freeze/build/update — отдельные явные операции.
3. SHA-256 подтверждает тождество байтов, не правдивость автора. Review identity/provenance требует внешней границы доверия.
4. Ошибка preflight не изменяет пользовательские и принятые managed files. Несколько `os.replace` не считаются общей атомарной транзакцией.
5. Execution outcome неизменяем; assurance, diagnosis и review остаются отдельными сущностями.
6. Новые negative tests сначала воспроизводят реальный дефект, после исправления проверяют желаемый отказ. Старые audit probes/receipts сохраняются как история.
7. `implemented`, `locally_verified`, `rc_verified`, `accepted` различаются. Skip обязательного acceptance case не равен pass.
8. Без внешнего доступа заканчивается вся независимая локальная работа. Внешний gate остаётся непринятым; fake receipt не создаётся.

## 4. Архитектурные решения этапа

### 4.1. Контракты

Усиление структуры breaking contracts выпускается новым major: correctness corpus `/2`, release manifest `/2`, при необходимости quality lock/transaction/agent receipt. Legacy `/1` читается явным adapter и получает ограниченный статус; старые digests нельзя молча вычислять по новому алгоритму. Ledger/PlanSpec/Verdict `/2` не повышать автоматически из-за соседних изменений.

До новой схемы проверить фактический `src/testence/contracts/versions.py`, Python loaders и packaged JSON schemas. Для одинакового semantic contract validators должны одинаково принимать и отклонять общие fixtures. Запретить NaN/Infinity, дубли JSON object keys в доверенных manifests, malformed UTF-8 и неявные преобразования типов. `bool` не принимать вместо integer; JSON Schema `format` не считать автоматически включённой проверкой.

Структурная валидация отделяется от semantic validation и evidence verification. JSON Schema не проверит уникальность gate по `id`, действительность commit, hash файла или независимость reviewer. В CLI различать эти причины typed errors.

### 4.2. Общие примитивы

Предусмотреть небольшие переиспользуемые службы: проверка управляемых путей; чтение/проверка content manifest; preflight и journal файловой транзакции; receipt verification. Не строить универсальную plugin platform для этих четырёх операций. Placement и зависимости фиксируются в коротком ADR до их массового использования.

### 4.3. Версии и совместимость

Основная CI matrix сохраняет Python 3.10/3.12 × Windows/Linux; Python 3.13 на машине автора не заменяет её. Pytest/Playwright/xdist floor закреплён отдельным job, locked dependencies — отдельным. Изменение floor требует support ADR и миграции. Любая новая dev/build dependency документируется; runtime не должен тянуть SBOM/scanner/release tooling только ради CI.

## 5. Подробные пакеты работ

### S3-00. Зафиксировать исходное состояние и реестр требований

**Вход:** текущее дерево, audit A01–A09, T01–T29. **Выход:** baseline receipt и mapping R/T/A → S3 → acceptance IDs.

Снять base SHA, dirty state, diff summary, hashes релевантных исходников и versions. Уважать существующие незакоммиченные изменения. Запустить штатный baseline один раз с заранее созданным parent и новым уникальным basetemp. Не удалять чужие/старые каталоги для получения green. Записать skips и причины отдельно.

Из [проб аудита](../../../outputs/audit-2026-09-06-result/README.md) извлечь минимальные воспроизведения. Не выполнять старый probe, ожидающий дефект, как release gate. Не считать «339» целевым количеством будущих tests.

**Done:** есть воспроизводимое состояние inputs, все A01–A09 имеют назначенную задачу, сохранены результаты до исправлений. Новые Git commits не подразумеваются одной только подготовкой этого ТЗ.

### S3-01. Строгая валидация и versioned migration

**Область:** `src/testence/contracts/`, `benchmark.py`, `quality.py`, agent state, release schemas; соответствующие tests.

Определить однозначный JSON/digest protocol: relative POSIX paths, SHA-256 prefix/hex, размеры bytes, encoding, schema version, unknown fields, timestamp semantics. JSON parser должен замечать duplicate keys до построения dict. Ограничить размер manifest и числа entries перед дорогостоящими операциями. Loader не должен выполнять URL fetch/$ref resolution из недоверенного документа.

Для JSON Schema допускается проверенная библиотека с закреплённой dev/runtime ролью; не писать неполный собственный JSON Schema interpreter. Если Python domain loader сохраняется, общие positive/negative fixtures обеспечивают parity. Результат legacy migration не объявляется rc_verified.

**Done:** валидные текущие fixtures имеют документированный migration path; malformed inputs возвращают понятный ненулевой CLI exit, без traceback по ожидаемой пользовательской ошибке; schema resources находятся и из wheel.

### S3-02. Единая безопасная адресация чтения, записи и удаления

**Закрывает:** A01 и path-часть A03; R06–R08/T11. **Область:** agent installer, application scaffold/doctor/submit, quality state/history, corpus, import/export/retention.

Для repo-relative managed paths: отклонять absolute, drive-relative (`C:foo`), UNC/device, ADS (`name:stream`), `..`, пустые части и неоднозначные separator spellings до OS resolution. Проверять также Windows-formatted paths на Linux через явную portable grammar, а не только host `Path`.

Нормализовать доверенный project root один раз. Для записываемых managed деревьев применить безопасный default: запрещены symlink/junction/reparse ancestors и link targets ниже root. Root, явно выбранный пользователем, может быть разрешённым resolved каталогом; это не разрешает дочерний escape. Чтение внешнего локального quality-pack source по явному аргументу допустимо, но его entries должны оставаться внутри этого source root.

Проверка покрывает служебные `.testence`, locks, history, staging, временные файлы, а не только skills/policy. Hardlink существующего файла не должен приводить к изменению внешнего inode: managed replacement идёт новым файлом, не `write_bytes` по старому inode. Для append ledgers использовать отдельную политику отказа от неоднозначных link targets.

**Done:** PATH-01–PATH-08 из матрицы проходят на обеих ОС; ни одного изменения audit-owned внешнего sentinel; отказ до первой managed записи.

### S3-03. Файловые операции с preflight, конфликтами и восстановлением

**Закрывает:** общая основа A01/A02 и Windows write failures. **Область:** `application.py`, `agent/install.py`, `quality.py`; узкий общий transaction layer.

Операция вычисляет change plan целиком: add/replace/delete/keep/conflict, expected prior hash и incoming hash. Dry-run возвращает этот plan без мутаций. При конфликте ни один целевой managed файл не изменяется; diagnostic receipt можно писать только в заранее безопасное audit/state место, не заменяя принятый lock.

Применение имеет exclusive project writer lock, immutable before-images, staging bytes и journal. Lock нового состояния публикуется только после проверки фактического набора файлов. При process kill следующий вызов обнаруживает incomplete transaction и восстанавливает согласованное состояние либо требует явного recovery; не угадывает success. Временные файлы создаются безопасно и уникально в проверенном parent, на том же volume, что target.

File sharing failures Windows допускают ограниченные retries только для ожидаемых transient errors. Повтор проверки expected hashes обязателен перед записью; никогда не overwrite чужое изменение в retry loop. Denied permission после лимита — диагностированный failure, не `except: pass`.

**Done:** transaction fault matrix TX-01–TX-07; последовательные вызовы идемпотентны; прерывание между files/config/lock не оставляет ложный accepted state. Границы защиты от враждебной конкурентной смены filesystem описаны без обещания полноценной sandbox.

### S3-04. Целостный quality-pack update/rollback

**Закрывает:** A02; R21/T21. **Область:** `quality.py`, quality-pack/lock/sync schemas, tests.

Хранить отдельно upstream pack digest и effective installation digest после одобренных overrides. История сохраняет immutable snapshot именно принятой effective version с manifest path/size/hash. Перед rollback проверить все bytes и metadata, а не только доступность файлов или строку digest. Подмена snapshot и missing snapshot отклоняются до первой записи.

Обрабатывать весь diff: файл удалён upstream; новый файл v2 отсутствует в v1; локальное изменение/удаление; override истёк; version несовместима; incoming pack одинаковой версии с другими bytes. Удалять можно только prior-managed неизменённые bytes. Никакие пользовательские файлы не удаляются как «лишние» по glob.

Принятые overrides содержат reason/owner/expiry и точный scope. Rollback не создаёт задним числом новое разрешение на просроченное исключение: такой случай требует нового review и остаётся конфликтом. History сохраняется после rollback и не переиспользуется по одному version string.

**Done:** QP-01–QP-08, три проекта с intentional conflict; config, lock, installed bytes и receipt согласованы. Legacy history без проверяемого snapshot не получает «exact rollback».

### S3-05. Закрыть оставшиеся safety/capture/auth критерии

**Закрывает:** незавершённые R06–R08/T10–T12; это обязательная часть этапа, не только внешний review.

Выполнить browser/API login→refresh→logout→role switch matrix, два пользователя и два проекта одного origin; cache default-off, identity probe/TTL и отказ при недоступном probe. Интеграционные tests должны использовать реальный transport и browser, synthetic credentials и два локальных origins. Простого mock cookie dict недостаточно.

Body capture default-deny; admitted fields/content types и размеры задаются policy до persist. Для screenshot/video/trace safe default — disabled, пока не разрешена и проверена отдельная capture policy. Text sanitizer не обезличивает изображения. Capture omission/error записывать в manifest, а потерю required evidence — в assurance completeness. Production PII не обещать автоматически обнаруживать по regex.

Сохранить исходные R08 defaults: summary ≤16 KiB, agent text ≤256 KiB UTF-8, ring ≤2000 records и ≤8 MiB/test, admitted body ≤64 KiB, artifact pack ≤20 MiB/test, run ≤1 GiB. Все размерности именно bytes. Hard ceiling/overrides и выбранные limits входят в receipt. Диск full/denied write/dead browser не стирают исходный test failure.

Retention: dry-run plan, отказ для active/pinned runs, resolve/link/namespace validation перед deletion; отмена плана при изменении state. Safe archive import ограничивает expanded bytes, количество entries, traversal и link entries до распаковки. Защитные проверки не должны очищать project root рекурсивно.

**Done:** SEC-01–SEC-08; независимый security review после локальных proofs остаётся отдельным обязательным gate G2.

### S3-06. Corpus `/2`: исполнимый registry и content freeze

**Закрывает:** A03; R18/T23. **Область:** `benchmark.py`, `corpus/`, schemas, CLI.

Каждая запись задаёт stable case ID, stratum, target/revision, executable selector и ожидаемый scope, truth/outcome/reason, input digests, timeout/reset и split. Один source file может содержать несколько cases; уникальность означает независимые определённые сценарии/ожидания, а не запрет повторного имени файла.

Freeze manifest перечисляет registry, executor/evaluator code, scenario sources, fixtures/config/locks и target revisions. Хешируются фактические bytes и paths/size, в фиксированном порядке. Сам lock не включает собственный digest. Не хранить absolute developer paths в portable manifest. После изменения любого обязательного input validate завершается ошибкой; не обновляет freeze автоматически.

Разделить команды validate structure, verify freeze, run/evaluate, verify acceptance. Structural pass не выдаётся за measured-quality pass. Два одинаковых target declarations, несуществующие receipts, некорректные commits и incomplete execution не дают accepted. Truth/bug flags, patch labels и expected diagnosis находятся в evaluator/custodian data и не копируются в agent input/evidence. Публичный scenario manifest и скрытая truth mapping связываются scope digests; ответы не подсказываются агенту именем `real_bug_case` или environment metadata.

**Done:** COR-01–COR-08. Migration старого `/1` сохраняет исходные labels как исторические; новый corpus надо независимо сформировать/заморозить, не просто изменить schema string.

### S3-07. Независимый evaluator и действительные 40 cases

**Зависит:** S3-06; сохраняет уже исправленные evaluator guards. Формирует 20 product defects, 10 healthy/harmless controls, 5 repairable drift, 5 infrastructure/ambiguous cases. Runner mutants учитываются дополнительно, не заменяют product defects.

Executor стартует в отдельном consumer process с заданными target/revision/reset/seed. Evaluator знает own expected selected scope и truth, считывает фактический exit, terminal completeness и assertion evidence. Не использует только `summary.status` самого Testence как правильный ответ. Truth для дефекта определяется fixture/revision и независимой проверкой target, а не модельным verdict.

Выявлять default-pass runner, wrong identity, dropped oracle, missing shard/terminal, empty/crashed healthy control. При empty/unavailable authoritative oracle — reasoned abstention, не product bug и не success. Таймаут остаётся sample с failed/incomplete execution; не удаляется из denominator.

Сохранять raw cases/attempts, detection/right-reason/abstention/completion, false green/red, unsafe repair и denominators. Публиковать интервалы выбранным заранее методом. Повторы измеряют устойчивость, не увеличивают число уникальных cases. Наблюдаемый ноль false green/unsafe repair обязателен на critical subset, но не обещает нулевой общий риск.

**Done:** EVAL-01–EVAL-06, таблица всех 40 cases с executable selectors и исходами, raw receipts. Нельзя закрыть работу одним файлом из 40 деклараций.

### S3-08. Два OSS targets и независимая truth/holdout приёмка

Выбрать два действительно разных licensed web приложения на разных стэках. Для каждого: repository URL, проверенный commit, происхождение/лицензия fixtures/assets, healthy/bug/harmless revisions или reviewable patches к base commit, create/persist/search/update/delete, reproducible build/reset и synthetic seeds. Не использовать mutable `latest` как pinned artifact.

Selection memo с обоснованием доступности/лицензий можно подготовить локально; чтение публичных исходников не требует внешнего tenant. Если первый target неудобен, документировать замену до freeze. Не откладывать выбор до окончания всего кода.

Два независимых truth reviewers проверяют frozen case inventory. Holdout минимум восемь cases, не доступных tuning исполнителю после freeze; нужен отдельный custodian/restricted artifact с digest commitment. Публичные tests предыдущих итераций не становятся hidden holdout после смены поля `split`. После раскрытия публиковать результаты, для нового tuning создавать новый holdout revision.

Receipt review содержит reviewer identity, scope digest, decision, time и ссылку на внешне проверяемое review. Локальная строка имени/число reviewers не доказывают независимость. Минимум один независимый deterministic rerun; два external reproductions для полного пилота сохраняются.

**Done:** проверенные targets и фактический review/reproduction. До этого G6 incomplete, даже при green synthetic executor. Никаких придуманных подписей, людей или запусков.

### S3-09. Smoke именно переданного distribution

**Закрывает:** A04; `scripts/installed_wheel_smoke.py`, package build, CI.

Выбранный путь: parent orchestrator создаёт новый isolated venv и устанавливает точный wheel, child выполняет consumer smoke вне checkout с isolated interpreter. Не переиспользовать окружение с уже установленным Testence. До установки проверить единственность artifact, wheel metadata/ZIP integrity; после — installation result, origin, Testence import path/version и ожидаемые installed resource bytes.

Hash distribution вычисляется до установки и перепроверяется после чтения; его immutable copy служит input установки. Имя/version без hash не идентифицируют wheel. `RECORD` полезен, но сам по себе не доказывает соответствие внешнему wheel. Details и ограничения — в пособии.

Smoke покрывает public imports, schemas, skills, CLI help, browser startup, demo, report/export, bounded verdict validation и обычный pytest consumer без opt-in. Child не добавляет `src` в `sys.path`, не импортирует implementation из checkout. Output receipt фиксирует artifact hash, source candidate, interpreter, import location, dependency inventory digest и каждый check.

**Done:** WHEEL-01–WHEEL-07. Текстовый файл, чужой wheel той же версии, изменённые installed resources и missing resources не могут получить passed receipt.

### S3-10. Source provenance, resolved SBOM и sdist rebuild

**Закрывает:** A06/A09. **Область:** `release_artifacts.py`, `dependency_inventory.py`, manifests и CI.

Release build принимает clean source revision; diff/untracked build inputs запрещены. Local build имеет `dirty=true` и полный materialized source snapshot digest, не приписывает bytes голому HEAD. Build context задаётся явным inventory; outputs/.venv/credentials туда не попадают. Зафиксировать build backend/tool versions и действительные inputs.

Собирать wheel/sdist один раз для данного candidate job, передавать artifacts дальше по digest. Из sdist собрать второй wheel в чистой среде и сравнить нормативный package payload/metadata/resources. Если archive timestamps/installer transformations различаются, не обещать byte-for-byte reproducibility без отдельного подтверждения; различие кода/resources недопустимо.

SBOM проверенной среды использует resolved dependency versions, транзитивные edges, активные environment markers/extras, licenses и hashes, а не `>=` requirements. Разделить runtime, build/dev и browser/driver components; роль Node/Chromium из Playwright записать явно. Если hash происхождения компонента недоступен, не выдумывать его. Requirements metadata остаётся отдельным артефактом. Graph Windows не выдавать за graph Linux.

SPDX документ проверяется настоящим validator выбранной версии. Inventory и SBOM имеют binding к distribution, platform/python/dependency lock и тому же smoke run. Scanner findings получают severity, scope, remediation/waiver owner; unexplained critical блокирует gate.

**Done:** BUILD-01–BUILD-06; чистый source, artifact, installed runtime и receipts согласованы.

### S3-11. Исполнимый release manifest validator

**Закрывает:** A05; `release/rc-manifest.json`, release schema, `tests/test_release_manifest.py`, новый application/CLI validator.

Исторический no-go manifest остаётся неизменяемым receipt. Новый candidate manifest `/2` содержит candidate SHA/version/artifact hashes; support/tool/consumer versions; требования и gates; receipt references с digest; exemptions/limitations; machine readiness и отдельное owner decision.

Проверять G1–G8 ровно по одному; R01–R24 представлены traceability; source/dependency/corpus revisions согласованы; references существуют и hashes совпадают; invalid/missing/stale receipt не наследует passed. Не считать `all([])` доказательством полноты. Evidence profiles `local`, `rc`, `external` проверяются отдельно.

Validator возвращает `ready_for_owner_decision` только при полном выполнении технических и внешних критериев. Сам не создаёт approval владельца. `go` в финальном документе допустим только с owner decision, приложенным к точному manifest payload digest. Hash/signature — это механизм binding; доверие к owner устанавливает защищённый review/release channel.

Candidate SHA обозначает commit исходников. Сам manifest с результатами появляется после CI как отдельный artifact: не требовать commit, содержащий собственный SHA. Публикация manifest не пересобирает wheel и не меняет target SHA. Подробный порядок в пособии.

**Done:** REL-01–REL-08; валидный clean/go fixture проходит; malformed/duplicate/stale/empty/mismatched manifests не проходят. Synthetic fixture с mock trusted review проверяет только код валидатора и не становится реальным release approval.

### S3-12. Завершённый переносимый demo

**Закрывает:** A07; `application.py`, packaged demo resources, `tests/test_application.py`, docs.

Сохранить команду `testence demo run --project ... --json`. Предоставить маленький synthetic web SUT в wheel: loopback server, временная БД или явное repository state, deterministic reset. Healthy сохраняет сущность; buggy mode показывает успех без сохранения; harmless mode меняет представление, сохраняя семантику. Expected value/ID задаётся сценарием до action, не вычисляется из проверяемого ответа.

Один UI action запускает мутацию; independent read-only API oracle подтверждает состояние/identity/revision в deadline. Сценарии выдают verified/violated/verified по протоколу, а failure содержит действительный pack с событиями/claim links/capture flags и HTML/Allure/CTRF. Недоступный oracle — inconclusive и demo failure, не ожидаемый дефект.

One-command receipt содержит per-scenario exit/assurance/pack/report paths, artifact hashes и cleanup result. Ожидаемый pytest exit 1 принимается только после всех проверок ожидаемого failure. Не скрывать generic exit 1 как успех. Команда завершается в заданный deadline, останавливает только созданные server/browser processes, безопасна при повторе с новым run_id.

Для offline walkthrough можно формировать deterministic example verdict, явно обозначенный fixture-generated; он проходит обычный submit validator и не называется real-agent output. Реальные client runs — S3-13.

**Done:** DEMO-01–DEMO-08 из установленного wheel на двух ОС; README содержит работающие Bash/PowerShell команды; новый пользователь не зависит от исходников benchmark приложения и SSH.

### S3-13. Полный agent workflow и полезная очередь QA

**Сохраняет:** два real-client triage receipts как частичное доказательство; расширяет до U2/U4/U5.

Pack digest skills включает весь нормативный file inventory, не только `skill-pack.json`. Изменение SKILL.md/reference меняет digest; old managed edits сохраняются как конфликт. Init/install/verify/submit используют safety/contracts/transactions S3-01–S3-04.

На одном согласованном fixture и pinned pack два доступных реальных клиента выполняют plan → author → run → triage → proposal → reviewed replay. Можно разделить работу на несколько сессий, сохранив identities и receipts. Не симулировать два клиента двумя prompt strings одного mock. Fresh wheel demo запускается без LLM, real-client acceptance — отдельно с учётом доступов/лимитов.

Product defect не исправляется ослаблением теста. Для допустимого locator repair: reviewable diff/base hash, unchanged required claims/role/oracle, healthy/defect/harmless proof; попытки skip/retry/assertion removal — policy rejection/review, не auto-accept.

В трёх project namespaces показать pack update/rollback и QA summary: new violation, missing/stale proof, coverage gaps, flake/quarantine expiry, awaiting/rejected repair. Добавить отсутствующие role/case/owner/risk filters и связи с requirement revision. Inventory coverage считается по объявленным requirements, не по числу tests. Для этого не нужен новый TMS server: локальный summary + существующие artifacts/mappings достаточны.

**Done:** AGENT-01–AGENT-05 и U5 consumer с тремя Git repositories/synthetic credentials; live TMS mapping и команды пилота — S3-18.

### S3-14. Измерения реальной нагрузки и flake

**Закрывает:** A08; `bench/scale_profile.py`, warm/fresh benches и budgets.

Сохранить microbenchmark CTRF export под точным названием. Добавить end-to-end 10k results: emission → manifests → read/reconcile → export/report. Таймер wall time начинается снаружи child process; отдельными полями startup/run/export. Измерять peak resident memory tree и отдельно Python allocations, total artifacts и cleanup; child Node/Chromium входит в соответствующий browser resource profile.

Flood cases: 100 MiB response, long stream, 100k console events, ring overflow и тысяча failures через настоящий collector, не заранее обрезанные строки. Не материализовать весь большой body ради последующего truncation; details в пособии. Контрольный required failure/correlation должен пережить шум или получить явный incomplete, а не verified.

Raw JSONL каждой итерации: case/config/build digest, start/end/duration, counts/bytes/memory, timeout/failure, seed, cold/warm, cleanup. Формулы quantiles/intervals и exclusions фиксируются до запуска. RC timing profiles исполняются минимум 30 раз на каждый сравниваемый scenario/режим; stable cases — минимум 30 повторов каждого case с общим denominator не менее 100 case-runs. Малый PR smoke 3/5 repeats не заменяет эти измерения.

Не потерять исходные численные требования R17:

| Проверка | Обязательный предел/объём |
|---|---|
| Reference host | 4 vCPU, 8 GiB RAM, SSD; точные OS/CPU/browser versions в receipt |
| 100k events / 10k synthetic results | Export+summary ≤30 s, exporter peak RSS ≤512 MiB; browser отдельно |
| React launch budgets | ≥5 повторов для локальной приёмки; PR smoke ≥3; полный benchmark ≥30 |
| Replay isolation/parallel parity | 100 isolated cases serial и `-n 4`, одинаковые semantic outcomes; actual scaling ratio |
| Warm resource cleanup | 50 warm reruns без накопления owned pages/processes; authoring-only статус warm сохраняется |
| Stable-case flake | ≥30 repeats каждого canonical case, zero observed unexplained flake; interval и denominator |

Если reference host сейчас недоступен, выполнить доступный локальный профиль и оставить reference-host acceptance pending, не переименовывать более мощный host под нужную конфигурацию.

Existing budgets не ослаблять для green. Новые end-to-end limits фиксируются в versioned budget после отдельного calibration на названной reference machine и до acceptance runs; calibration не считается acceptance. Missing/null/NaN/Infinity, zero samples и пустой limits set дают failure. Artifact cap из R08 обязателен независимо от скорости железа.

**Done:** PERF-01–PERF-07, raw samples и честные denominators; нет отбрасывания неудобных timeouts или выбора лучшего прогона.

### S3-15. CI воспроизводит release gates из чистого checkout

Проверки делятся на быстрый PR gate, consumer matrix и RC acceptance. Fast gate: format/lint/types/contracts/unit/negative regressions, structural+content freeze, deterministic critical subset и packaging. Matrix: Python 3.10/3.12 × Windows/Linux; minimum deps отдельно; browser/xdist/link cases исполняются на поддерживаемых runners.

Installed-wheel/packaging tests не зависят от старых `outputs/audit-*`, venv автора или предыдущего job workspace. Test fixtures хранятся отдельно как маленькие synthetic inputs; build outputs передаются jobs через artifacts/digests. Один candidate build, smoke/report/scan потребляют именно его. Required jobs/skips/failed upload artifacts делают RC incomplete.

PR из fork не получает secrets, publisher permissions или live TestOps access. Отдельный manual/protected RC workflow выполняет длительный corpus/resources и external integrations только в разрешённом контексте. Pinned action refs и dependency locks обновляются осмысленно, не копируются выдуманные SHA из текста ТЗ.

Windows temporary parent создаётся до pytest; каждый запуск использует уникальный root. Не добавлять retries всего pytest ради green; transient failure сохраняется и исследуется. Playwright install и xdist extras явно присутствуют в нужных jobs.

**Done:** CI-01–CI-05, hosted matrix на candidate SHA; шаблон workflow без фактического run означает implemented, а не rc_verified.

### S3-16. Документация, права и OSS состав

Единый support manifest питает README, EN/RU guides, CLI/example validation и release support matrix. Сделать пути QA/developer/maintainer, troubleshooting ошибок/конфликтов, migration/rollback, examples обычного pytest и новых contracts. Help, snippets и ссылки проверяются исполнением, а не поиском строк.

Происхождение включённых source/assets/fixtures/datasets записывается построчно либо по однородным каталогам в inventory: origin/revision/license/modifications/distribution scope/reviewer. Не писать «project-authored» для всего дерева без проверки. Сохранить Apache-2.0; NOTICE определяется фактическими включёнными компонентами и review.

Из publication inventory исключить local venvs, `.mcp.json`, credentials, private URLs/data и внутренние agent transcripts; публичные receipts должны быть sanitized. Выполнить scan предполагаемого tree и истории, не только HEAD commits. Findings triage сохраняется; реальные secrets требуют согласованной rotation/remediation, а не удаления строки из отчёта.

Подготовить действующий SECURITY/private reporting, maintainers/support window, CONTRIBUTING/CODE_OF_CONDUCT/CODEOWNERS/templates, release notes и 90-second video по реально работающему demo. Видео демонстрирует observed failure/pack и ограничения, а не закрывает остальные gates.

**Done:** DOC-01–DOC-05. Настройки repository/security channel подтверждаются фактическим receipt владельца, не только текстом Markdown.

### S3-17. Подготовленный publishing workflow

Создать отдельный workflow build/verify/publish с защищённым environment, минимальными permissions, OIDC trusted publisher и проверкой exact tag→candidate SHA→artifact digests. Публикуется ранее проверенный artifact; publish job не пересобирает пакет.

Publisher не получает секреты в PR jobs, не использует долгоживущий PyPI token как shortcut. Имена repository/environment/workflow/package должны совпадать с фактической конфигурацией trusted publisher. Настроечные значения до выбора владельцем остаются в maintainer checklist, а не fake-working quickstart.

Dry-run проверки YAML/config/artifacts и failure paths выполняются локально/в разрешённом CI. Реальный TestPyPI/PyPI upload, public visibility и сообщения внешним участникам требуют имеющегося явного разрешения владельца; подготовка этого ТЗ его не создаёт. Если разрешение уже выдано в рабочем сеансе, повторно его не запрашивать.

**Done:** PUB-01–PUB-04; готовая проверяемая конфигурация и точная инструкция активации. `publishing_prepared` отдельно от фактического `published`.

### S3-18. Live TestOps, пилоты и внешние reviews

Завершить R14 test-tenant round trip: testplan selects 1/8 и 3/20, no accidental extra scope, pass/fail/broken/skip, parameters/retries/history, two project mappings, attachments, failure exits. Offline 401/403/429/5xx/timeout/partial-upload fixtures готовы до tenant. После ambiguous upload не обещать exactly-once без сверки remote launch; blind repeat запрещён.

Pilot: минимум пять новых пользователей, три внешние команды, две независимые reproductions. 4/5 проходят demo ≤15 минут без помощи автора; ≥2/3 добавляют второй сценарий и возвращаются следующей неделей; одна команда — single QA/three projects, одна — TestOps selective launch. Сравнение с хорошо настроенным pytest/Playwright+Allure с равным oracle доступом. Сохранить setup/review/triage time, accepted scenarios, gaps/overrides и критерии неуспеха.

Security/rights/truth review имеют конкретных исполнителей и scope digests. Агент заранее готовит scripts, sanitized fixture bundle, вопросы и форму receipt. Без участников/доступов эти задачи имеют `external_pending`, с точным перечнем зависимости и выполненной локальной части.

**Done:** EXT-01–EXT-05 по фактическим данным. Нельзя заменить неделю возврата sleep/tool automation без реальных участников, локальные tests — внешними командами, автора — независимым reviewer.

### S3-19. Финальная приёмка и передача сопровождению

Собрать exact candidate, выполнить все релевантные checks после последних изменений. Изменение code/fixtures/contracts/locks инвалидирует зависящие receipts; переиспользование допустимо только с доказанной применимостью и policy, не по совпадению имени задачи.

Сформировать manifest S3-11, G1–G8 и R01–R24 traceability, known limitations, recovery/rollback, artifact retention и owner decision. Независимый повтор последнего аудита проверяет отрицательные cases на новом candidate. Отсутствующий gate означает no-go и конкретный residual backlog.

Два отдельных результата: **engineering handoff** — локальная реализация с tests/docs/negative probes; **R1 accepted** — все gates на RC и внешняя приёмка. Первый не разрешает писать «ТЗ завершено» про второй. При отсутствии внешних условий исполнитель заканчивает engineering handoff и перечисляет оставшиеся зависимости; не расширяет scope, чтобы имитировать продолжение.

## 6. Definition of Done этапа

Этап считается полностью завершённым, когда S3-00–S3-19 приняты, A01–A09 закрыты воспроизведением исправления, исходные R01–R24 и U1–U5 подтверждены, G1–G8 accepted на одном candidate, а владелец принял решение о выпуске. Фактическая публикация — отдельное авторизованное действие после подготовки. Возможность открыть исследовательский pre-alpha не снижает эти критерии R1.

Для каждого engineering slice: implementation + docs/migration + negative/positive consumer tests + scoped review + bound receipt. Для external slice дополнительно фактические независимые данные. Размер файла ТЗ, число tests, красивый demo и количество commits не заменяют этот результат.
