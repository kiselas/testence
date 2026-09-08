# Этап 3: порядок реализации и матрица приёмки

Использовать вместе с [нормативным ТЗ](README.md) и [пособием](implementation-guide.md). Все строки ниже — требования к будущей работе, не результаты выполненных проверок.

Самостоятельные технические решения и порядок проверки внешних зависимостей — в [режиме автономного выполнения](autonomy.md). Он не ослабляет критерии этой матрицы.

## 1. Очередь и условия перехода

| Milestone | Задачи | Можно начинать после | Условие завершения |
|---|---|---|---|
| M30. Исходная точка | S3-00/S3-01 | Начало этапа | Snapshot, regression seeds, contract/migration decisions |
| M31. Безопасные изменения | S3-02/S3-03/S3-04 | M30 | Path/transaction/rollback matrix, согласованные bytes/locks |
| M32. Доказательства и safety | S3-05/S3-06/S3-07 | M31; corpus design можно готовить с M30 | Реальные capture/auth negatives, content freeze, независимый evaluator |
| M33. Реальные targets | S3-08 | Discovery с M30; freeze после S3-06/07 | Два pinned targets, настоящий truth/holdout review/reproduction |
| M34. Package и пользовательский путь | S3-09/S3-10/S3-11/S3-12/S3-13 | Shared primitives M31; demo использует S3-05 | Exact wheel smoke, demo→pack→verdict, agent/3-project flow |
| M35. Измерения и CI | S3-14/S3-15 | Принятые контракты и consumer paths | Raw RC resource/flake data, hosted support matrix |
| M36. OSS и внешняя приёмка | S3-16/S3-17/S3-18 | Подготовка с M30; acceptance после M34/M35 | Docs/scans/publishing подготовлены; reviews, TestOps, pilots фактически пройдены |
| M37. Release decision | S3-19 | Все обязательные outputs предыдущих milestones | G1–G8, R01–R24, exact candidate manifest и owner decision |

Часть задач имеет ранний foundation и позднее завершение: S3-09 сначала реализует isolated wheel harness, затем расширяется готовым demo S3-12 и agent checks; это не повод делать фиктивный demo для закрытия S3-09. S3-11 сначала реализуется и тестируется synthetic fixtures, реальные candidate receipts появляются в S3-19. S3-15 начинает исполнять новые tests по мере готовности, не ждёт конца этапа.

Не ждать внешнего reviewer/tenant для S3-02–S3-07, local parts S3-09–S3-17. Реальные calls к агентным сервисам выполняются только с доступными разрешёнными credentials/лимитами. Этот план не поручает автоматически создавать дополнительные агенты или внешние задачи.

Размеры S/M/L не переводить в часы без spike. Самые рискованные slices S3-03, S3-05, S3-07 и S3-10 сначала получают design note и один доказанный vertical slice, затем расширяются. Не обещать дату полного R1 до согласования внешних участников и week-return окна.

## 2. Статусы и отчётность

Прогресс задач: `not_started → in_progress → implemented → locally_verified → rc_verified → accepted`. Дополнительные состояния: `blocked_local` с конкретной причиной; `external_pending` после готовности независимой локальной части. Это статусы планирования, не автоматическое изменение runtime enums.

Для задачи фиксировать: ID, owner/исполнитель, входные hashes, scope завершённого slice, acceptance IDs, actual commands и receipts, оставшиеся зависимости. Начальный owner — unassigned, пока человек не назначен; не приписывать существующему maintainer независимое review без факта участия.

Unit tests могут завершить `locally_verified` slice. `rc_verified` требует соответствующего candidate/OS/dependency receipt. `accepted` дополнительно выполняет внешние/review критерии конкретной задачи. Нельзя выдавать количество реализованных S3-ID за процент готовности G1–G8.

## 3. Обязательные отрицательные и положительные проверки

### Пути: S3-02

| ID | Fixture / действие | Обязательный результат |
|---|---|---|
| PATH-01 | `.testence` junction/symlink в соседний sentinel root; init/install/quality/doctor | Отказ, внешний root и managed files не изменены |
| PATH-02 | Link ancestor в `.agents/skills`, history/staging/retention root | Отказ до записи/удаления; не обход через служебный path |
| PATH-03 | `../x`, `/x`, `D:/x`, `C:foo`, UNC/device, `name:stream`, mixed separators | Portable member grammar отклоняет на обеих ОС |
| PATH-04 | `repo` и `repo-evil`; Windows case aliases/Unicode collisions | Нет prefix containment и двух managed записей в один path |
| PATH-05 | Новый безопасный relative path с missing parent | Успех внутри root, repeated invocation идемпотентна |
| PATH-06 | Existing hardlink file и внешний sentinel inode | Replacement не меняет внешние bytes либо безопасный отказ |
| PATH-07 | Parent/prior target заменён после preflight перед commit | Обнаруженный конфликт; нет accepted receipt для подменённой цели |
| PATH-08 | Corpus/import member outside root, symlink archive entry, traversal ZIP | Отказ; наружное содержимое не читается/не извлекается в portable bundle |

### Транзакции: S3-03

| ID | Fixture / действие | Обязательный результат |
|---|---|---|
| TX-01 | Conflict в последнем из трёх файлов | Первые два не изменились; accepted lock прежний |
| TX-02 | Disk full/denied write при staging и при publication | Failure с recovery state; ни одного ложного success |
| TX-03 | Реальный process kill после каждой journal phase | Следующий вызов восстанавливает согласованность/объясняет conflict |
| TX-04 | Два concurrent apply в одном project | Один writer; второй получает typed busy/conflict, без silent overwrite |
| TX-05 | Человек меняет applied файл перед error recovery | Правка сохраняется, journal конфликтен, snapshots доступны |
| TX-06 | Windows transient replace error, затем success/timeout | Bounded retry; expected hashes перепроверены; timeout не скрыт |
| TX-07 | Dry-run и одинаковый повтор operation | Dry-run не мутирует; повтор не дублирует history и artifacts |

### Quality pack: S3-04

| ID | Fixture / действие | Обязательный результат |
|---|---|---|
| QP-01 | Изменить snapshot byte после v1→v2 | Rollback отказал до первой managed записи |
| QP-02 | Удалить один snapshot при нескольких файлах | Нет частичного rollback/удалений |
| QP-03 | v2 добавил file, rollback к v1 | Удаляется только неизменённый managed addition |
| QP-04 | Upstream удалил file; локально он изменён | Conflict; human bytes сохранены |
| QP-05 | Valid/expired/malformed overrides | Valid отражён effective digest; expired/malformed не принят |
| QP-06 | Изменить lock/hash/source/version compatibility | Refusal, не автоматический rewrite metadata |
| QP-07 | Три projects: clean, approved override, conflict | Изоляция; reviewable diff; конфликтный проект не частично updated |
| QP-08 | Повтор rollback; legacy history без доказуемых hashes | Идемпотентный valid rollback; legacy unverified/conflict, не exact success |

### Auth/capture/retention: S3-05

| ID | Fixture / действие | Обязательный результат |
|---|---|---|
| SEC-01 | Browser/API login→refresh→logout→role switch | Совпадающая declared identity; old auth не reused |
| SEC-02 | Два origins; redirect/downgrade; cookie scopes | Canary не уходит forbidden origin/path; отказ до передачи auth |
| SEC-03 | Два проекта/пользователя одного host; TTL/probe failure | Нет cross-project/role cache reuse; failure не cache hit |
| SEC-04 | Secret canaries в URL/header/body/oracle/error/console/DOM/full/archive | Нет canary во всех retained/export sinks; outcome/correlation сохранены |
| SEC-05 | Safe profile screenshot/video/trace; masked opt-in | Disabled по умолчанию; omission flags; opt-in masks проверены отдельно |
| SEC-06 | Dead browser/disk full/denied write/oversized body | Исходная failure сохранена где возможно; capture error/incomplete видимы |
| SEC-07 | Retention dry-run active/pinned/link/wrong namespace, state changes | Ни одного удаления вне выбранного безопасного eligible scope |
| SEC-08 | Malicious HTML/link/JSON/archive и archive expansion | Нет исполнения/unsafe links/escape/unbounded extraction |

### Corpus freeze: S3-06

| ID | Fixture / действие | Обязательный результат |
|---|---|---|
| COR-01 | Изменить byte scenario/evaluator/fixture/config после freeze | Digest verification fail |
| COR-02 | 40 IDs с одной и той же executable case identity | Semantic duplicate отказ; общие source files допустимы |
| COR-03 | Два одинаковых OSS declarations и placeholders | Acceptance incomplete/invalid, не accepted |
| COR-04 | Не существует receipt/commit/reset input | Diagnostic с точным missing binding; не truthy-string pass |
| COR-05 | Незаконный absolute/member path на обеих ОС | Refusal без внешнего доступа |
| COR-06 | Refreeze после source edit | Новая revision; старый review scope не принят |
| COR-07 | Validate текущей правильной freeze | Read-only успех; hash файлов до/после одинаков |
| COR-08 | Старый `/1`, unknown major, invalid types/duplicate JSON keys | Явный legacy limited mode или отказ; parity Python/JSON validators |

### Evaluator: S3-07/S3-08

| ID | Fixture / действие | Обязательный результат |
|---|---|---|
| EVAL-01 | Все 40 independent cases в declared strata | Реальное исполнение, ожидаемые outcomes/reasons, raw records |
| EVAL-02 | Empty/crashed healthy, wrong exit/selected scope | Не healthy success; sample остаётся в denominator |
| EVAL-03 | Default pass/wrong identity/dropped oracle/missing shard mutants | Каждый обнаружен независимым evaluator |
| EVAL-04 | Unavailable oracle/auth HTML/timeout | Reasoned abstention/incomplete, без выдуманного product bug |
| EVAL-05 | Known defect после locator repair; weakened assertions | Дефект обнаруживается, weakening не считается safe repair |
| EVAL-06 | Changed holdout/truth/target, leaked truth labels или отсутствует independent review | Старый acceptance не принимается; labels не доступны агенту; нужен новый scoped review |

### Wheel: S3-09

| ID | Fixture / действие | Обязательный результат |
|---|---|---|
| WHEEL-01 | Текстовый файл `not-a-wheel.whl` | Refusal до consumer passed receipt |
| WHEEL-02 | Corrupt ZIP/METADATA, несколько ambiguous dist files | Refusal с явным artifact selection error |
| WHEEL-03 | Candidate ожидает A, передан wheel B той же версии | Hash mismatch; не receipt успеха A |
| WHEEL-04 | Editable checkout/PYTHONPATH/preinstalled Testence рядом | Imports только из нового consumer venv; foreign origin refusal |
| WHEEL-05 | Missing/changed schema/skill/demo payload | Resource integrity failure, не проверка одного имени/version |
| WHEEL-06 | Валидный artifact на Windows/Linux | CLI/library/browser/demo/export/submit smoke passes вне checkout |
| WHEEL-07 | Artifact изменился во время handoff/install | Input digest mismatch; receipt не связывает разные bytes |

### Build/provenance/SBOM: S3-10

| ID | Fixture / действие | Обязательный результат |
|---|---|---|
| BUILD-01 | Dirty/untracked materialized input в release build | Refusal; local build явно dirty + snapshot digest |
| BUILD-02 | Ранее отсутствующий в HEAD source включён в wheel | Local provenance не обозначает его как clean HEAD build |
| BUILD-03 | Rebuild из sdist в чистой среде | Нормативный package payload/metadata/resources эквивалентны |
| BUILD-04 | Transitive dependency/OS marker/extras | Resolved SBOM совпадает с конкретным consumer inventory |
| BUILD-05 | Подменён inventory/SBOM/subject hash | Binding check отказал; документ валидируется по выбранной SPDX версии |
| BUILD-06 | Source/lock/tool versions и scanner triage | Действительные inputs зафиксированы; unexplained critical findings блокируют |

### Release manifest: S3-11

| ID | Fixture / действие | Обязательный результат |
|---|---|---|
| REL-01 | Неверный SHA, unknown fields/types/schema, duplicate JSON keys | Structure failure |
| REL-02 | Девять gates/повтор G1/missing G8 | Semantic failure до dict deduplication |
| REL-03 | Empty artifacts/receipts либо несуществующие references | No-go/incomplete, не vacuous success |
| REL-04 | Receipt от другого candidate/dependency/corpus revision | Stale/foreign отказ |
| REL-05 | Changed artifact/receipt bytes при прежнем hash | Integrity failure |
| REL-06 | Все checks прошли, owner decision отсутствует | Ready for owner decision, не автоматический go |
| REL-07 | Валидный clean/go fixture и валидный historical no-go | Оба структурно читаются; решения оцениваются по своим критериям |
| REL-08 | Fake approval/непроверенный producer/смена payload после review | Не принято без trusted scope binding |

### Demo: S3-12

| ID | Fixture / действие | Обязательный результат |
|---|---|---|
| DEMO-01 | Healthy actual persist | Один intended action; required oracle verified |
| DEMO-02 | Optimistic success без persistence | Violated, действительный failure pack и reason |
| DEMO-03 | Harmless view change | Healthy semantics сохранены; verified |
| DEMO-04 | Missing browser/server/syntax error/unknown pytest exit | Demo failed, не accepted intentional failure |
| DEMO-05 | API unavailable/wrong entity/role/deadline | Inconclusive/violation по truth, без шаблонного успеха |
| DEMO-06 | Перенос bundle Windows↔Linux; HTML/Allure/CTRF | Manifest/artifact links/hashes валидны; consumer output соответствует run |
| DEMO-07 | Generated example verdict + stale/foreign variant | Обычный submit принимает valid и отвергает stale/foreign |
| DEMO-08 | Повтор/new ID, timeout и прерывание | Нет collisions/leaked owned processes; cleanup status сохранён |

### Agents и QA portfolio: S3-13

| ID | Fixture / действие | Обязательный результат |
|---|---|---|
| AGENT-01 | Изменить normative SKILL/reference byte | Новый pack digest; local edit не overwritten |
| AGENT-02 | Два actual pinned client workflows | Plan/test/run/verdict/proposal/review bindings подтверждены receipts |
| AGENT-03 | Repair меняет assert/required claim/role/skip/retry | Policy review/rejection, product failure не скрыт |
| AGENT-04 | Три repositories с одинаковыми case names/разными secrets | Namespace/credentials/artifacts изолированы; update conflict и rollback безопасны |
| AGENT-05 | Stale requirement, coverage gap, flake/expiry/pending/rejected repair | Только actionable summary с работающими project/owner/risk/role/case filters |

### Performance: S3-14

| ID | Fixture / действие | Обязательный результат |
|---|---|---|
| PERF-01 | 100k events / 10k results emission→reconcile→export/report | Raw весь путь; export+summary ≤30 s и exporter RSS ≤512 MiB на reference host |
| PERF-02 | 100 MiB response и stream через реальный collector | Bounded admitted capture либо явное omission; нет неверного acquired-memory claim |
| PERF-03 | 100k console records и тысяча failures | Count/byte caps соблюдены; required proof preserved или incomplete |
| PERF-04 | Fresh/warm browser arms, 50 warm reruns, 100 cases serial/xdist | Startup снаружи child; нет накопления owned resources; semantic parity serial/`-n 4` |
| PERF-05 | Empty limits/zero samples/missing/null/NaN/Infinity | Budget validator failure |
| PERF-06 | ≥30 timings на scenario/режим, ≥30 repeats каждого canonical case, ≥100 case-runs | Полный denominator; timeout/crash не выкинуты; rates/intervals опубликованы |
| PERF-07 | Повтор serializer и browser outcomes | Serializer determinism и browser flake представлены разными метриками |

### CI/docs/publishing/external

| ID | Проверка | Обязательный результат |
|---|---|---|
| CI-01 | Fresh checkout без outputs/venv автора | Fixtures и jobs самодостаточны |
| CI-02 | Windows/Linux × Python 3.10/3.12, floor deps отдельно | Hosted receipts; mandatory skips не принимаются как green |
| CI-03 | Один build artifact между jobs | Hashes не меняются; smoke/scan/publish не пересобирают свой wheel |
| CI-04 | PR/fork и protected RC workflow | Secrets/OIDC/live targets доступны только нужным authorized jobs |
| CI-05 | Failed test/quality/upload/missing report | Финальный job не green из-за успешного export/upload |
| DOC-01 | EN/RU Bash/PowerShell quickstart из wheel | Команды реально выполняются и совпадают с support manifest |
| DOC-02 | Existing pytest без opt-in; migration обратно | Обычная семантика сохранена; TMS identity mapping не потерян |
| DOC-03 | Source/assets/fixtures/dependency publication inventory | Provenance/rights scope reviewed; secrets/private artifacts исключены |
| DOC-04 | Tree+history scans, SECURITY/support/community | Scope и findings сохранены; канал реально доступен |
| DOC-05 | Links, help, video и user paths | Нет fake-working examples; видео соответствует настоящему demo |
| PUB-01 | Exact tag→commit→manifest→wheel binding | Нельзя опубликовать непроверенный artifact |
| PUB-02 | Protected environment и trusted publisher settings | Реальная конфигурация согласована; minimal permissions |
| PUB-03 | Неуспешный gate/неподтверждённый owner decision | Publish job не получает допустимый запуск |
| PUB-04 | Dry-run против реального publish | Prepared отдельно от published; actual upload только в разрешённом scope |
| EXT-01 | Два OSS targets/truth reviewers/holdout | Реальные revisions, review scope и independent rerun |
| EXT-02 | TestOps selective run/upload/history | Sanitized remote links/counts/versions и identity доказаны |
| EXT-03 | 5 users, 3 teams, 2 reproductions | Actual participant receipts; 4/5 ≤15 минут без помощи |
| EXT-04 | Второй сценарий/week-return и single-QA/three-project | ≥2/3 команд вернулись; измерена QA работа, не только setup |
| EXT-05 | Independent security/rights review и final owner decision | Реальные reviewers/decision bound к принятому scope |

## 4. Сохранение исходных требований R1

| Исходное требование | Задачи этапа 3 и минимальная повторная приёмка |
|---|---|
| R01 lifecycle | S3-15/19: setup/call/teardown, collect, xfail/xpass, interruption/crash, no-ex consumer |
| R02 identity | S3-13/15/19: 200 variants, duplicate names, retries, project boundaries, rename mapping |
| R03 completeness | S3-05/07/15: missing shard/terminal, torn tail, unknown version, empty scope не green |
| R04 claims | S3-01/07/13: required assertions, stale plan/requirements, Python/JSON schema parity |
| R05 oracle | S3-05/07/12: expected→UI→authoritative state, correlation/deadline/role/rollback |
| R06 auth | S3-02/05: real browser/API lifecycle и isolated cache/origins |
| R07 redaction/paths | S3-02/05: all sinks, links/archives, explicit image/trace policy |
| R08 evidence budgets | S3-03/05/14: caps/storage faults/portable manifest/retention |
| R09 verdict/repair | S3-01/13: immutable bindings, unsafe weakening, review and three proof runs |
| R10 isolation | S3-05/12/14/15: context/auth/data reset, owned process cleanup, fresh/warm |
| R11 browser primitives | S3-07/12/15: strict locator/click/request/window behavior на actual Chromium |
| R12 web surface | S3-15/19: frames/popups/shadow/files/dialogs/SPA/hydration matrix из исходного ТЗ |
| R13 Allure | S3-12/15/18: actual pinned consumer, attempts/history/attachments/full outcomes |
| R14 TestOps | S3-18: offline negatives + real testplan/upload/history round trip |
| R15 CI/export | S3-15/18: separate test/quality/delivery exits, JUnit/CTRF mapping |
| R16 agents | S3-09/12/13: portable wheel skills, doctor/init/submit, real client workflows |
| R17 performance | S3-14: raw times/resources/flake + frozen budgets |
| R18 corpus | S3-06/07/08: 40 actual cases, 2 targets, truth/holdout/evaluator mutants |
| R19 distribution | S3-09/10/15/16/17: wheel/sdist, dependency floor, provenance/SBOM/scans |
| R20 docs | S3-12/16: validated install/demo/migration/support docs |
| R21 multi-project | S3-04/13/18: three repos, conflicts/overrides/rollback/QA queue/TMS mapping |
| R22 extensions | S3-01/15: fake engine conformance, unsupported capabilities fail explicitly, no Playwright types required by neutral consumers |
| R23 adoption | S3-18: participants/return/reproductions/QA effort metrics |
| R24 OSS release | S3-11/16/17/19: rights/channel/community/video/manifest/owner decision |

Ссылка на уже существующий тест допускается вместо новой реализации, если его consumer behavior действительно покрывает строку и receipt применим к candidate. Не нужно создавать тесты-дубликаты ради нового ID.

## 5. G1–G8: что именно разрешает принять gate

| Gate | Минимальный пакет evidence | Что не принимается как замена |
|---|---|---|
| G1 Truth | R01–R05/R09 consumer matrix, evaluator mutants, expected scope, assertion bindings | Общее число passed tests |
| G2 Safety | PATH/TX/SEC negatives Windows/Linux + scoped independent review | Два skipped symlink tests или текст «secure» |
| G3 Web | Real Chromium matrix, isolated/fresh/warm, owned cleanup, relevant perf | Только HTML fixture без SUT/network |
| G4 Integrations | Actual Allure consumer + TestOps tenant selection/upload/history | Golden JSON и mock upload |
| G5 Agents | Два actual clients, весь workflow, safe pack/rollback/submit/proof | Только копирование SKILL.md или два triage текста |
| G6 Quality | Frozen independent corpus, real targets/review/holdout, raw resource/flake | Registry с 40 строками, `reviewers=2`, deterministic JSON hash |
| G7 Adoption | Actual 5/3/2, second scenario/week-return, QA effort | Protocol Markdown и синтетические persona interviews |
| G8 Distribution | Exact candidate CI/artifacts/SBOM/provenance/docs/scans/channel/governance | Локальный dirty wheel и созданный publish YAML без проверки |

## 6. Receipt contract и хранение доказательств

Целевой новый `testence/acceptance-receipt/1` описать в S3-01. Ниже состав, не заполненное свидетельство:

| Поле | Семантика |
|---|---|
| `schema`, `task_ids`, `check_ids` | Версия и полный проверенный scope |
| `evidence_kind` | Unit/negative probe/consumer/hosted CI/external review/pilot; не смешивать |
| `producer` | Tool/version и actual runner identity; model/client version где применимо |
| `source` | Commit, dirty, materialized input digest; local dirty не проходит RC profile |
| `subjects` | Wheel/sdist/corpus/pack/input identities и SHA-256 |
| `environment` | OS/Python/dependency/browser/agent/consumer versions, важные capability flags |
| `command` | argv/cwd profile, sanitized environment refs, timeout, started/finished UTC |
| `expected`, `observed`, `exit_code` | Непосредственные проверяемые outputs, не только summary status |
| `status`, `skipped`, `limitations` | Pass/fail/incomplete и подробная неполнота |
| `artifacts` | Relative path, bytes, MIME, SHA-256; refs разрешаются внутри receipt bundle |
| `review` | Внешний review reference/scope/identity/decision при необходимости |

Validation проверяет schema плюс semantics конкретного check ID. Отсутствующий exit/start time/raw sample для выполненного command receipt не превращается в pass. External review не обязан иметь process exit: типы evidence различаются.

Хранить маленькие нормативные fixtures в `tests/fixtures/`/`corpus/`, transcripts/raw runs — в artifact store или явно выбранных sanitized receipt directories. Tests чистого checkout не зависят от живых folders старого `outputs/audit-*`. В Git допустимы компактные публичные manifests/receipts, но не `.venv`, browser installs, private logs и большие временные runs. До публичного release провести отдельный inventory review всех untracked intended files.

Negative probe, который до исправления вернул неправильный `passed`, хранится с audit classification `defect_reproduced`; его статус не импортируется как положительное подтверждение исправленного gate.

## 7. Проверки и команды

Эти команды существуют на исходном baseline; исполнителю нужно сверять `pyproject.toml` и CI после изменения dev tooling. Они проверяют исходники, а не все acceptance gates.

```powershell
uv sync --locked --extra dev --extra parallel
uv run ruff check src tests bench scripts
uv run ruff format --check src tests bench scripts
uv run mypy src/testence bench/react_latency.py bench/warm_runner_latency.py bench/scale_profile.py scripts/release_artifacts.py
```

Для pytest выбрать новый уникальный root и создать parent заранее. Пример PowerShell не должен повторно указывать pytest на существующий пользовательский каталог, потому что `--basetemp` очищает свой target:

```powershell
$stage3Temp = Join-Path (Get-Location) ('.tmp-pytest-stage3-' + [guid]::NewGuid().ToString('N'))
if (Test-Path -LiteralPath $stage3Temp) { throw 'Temporary target already exists' }
uv run pytest -q --basetemp $stage3Temp
```

Bash:

```bash
stage3_parent=$(mktemp -d)
uv run pytest -q --basetemp "$stage3_parent/pytest"
```

Отсутствие Playwright browser/system dependencies исправляется по существующему setup recipe до real-browser acceptance. Не отключать browser/xdist/link tests ради green. Для focused slice передавай точные test selectors, после relevant изменения общей семантики выполняй full suite и consumer matrix.

Новые corpus/release/transaction команды вводятся contract-first в S3-01 и проверяются CLI tests. Пока они не реализованы, этот документ намеренно не даёт выдуманной ready-to-run команды для их полного gate.

## 8. Итоговый handoff

Engineering handoff содержит закрытые S3/check IDs, изменение поведения, regression receipts, миграции, actual test results и residual backlog. External-pending строки называют отсутствующего участника/доступ/окно наблюдения и готовый набор команд/fixtures для приёмки.

Полный R1 handoff добавляет clean candidate SHA, exact wheel/sdist hashes, действительные G1–G8 и R01–R24 receipts, support/rollback, действующий security channel и owner decision. Если любой обязательный gate остаётся incomplete, финальный ответ прямо говорит «R1 не принят» и не заменяет это фразой «локально всё закончено».
