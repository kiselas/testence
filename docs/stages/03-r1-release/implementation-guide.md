# Пособие исполнителю этапа 3

Нормативные требования — в [ТЗ](README.md), обязательные пробы — в [матрице](acceptance.md). Этот документ помогает реализовать их без архитектурных догадок. Предлагаемые module/function names не являются уже существующим API.

Режим работы без промежуточных согласований определён в [правилах автономного выполнения](autonomy.md). Прочитай их до S3-00 и дополни ими стартовый запрос из раздела 13.

## 1. Как работать небольшими проверяемыми шагами

Одна рабочая итерация закрывает один законченный slice. Для начала S3-02 это может быть только `agent install` + `.testence` junction refusal + positive install. Не пытайся одновременно изменить installer, rollback, corpus и CI в одном diff.

Порядок каждой итерации:

1. Прочитай применимые repository instructions, задачу и её acceptance IDs. Сверь dirty state; не откатывай чужие изменения.
2. Найди entry point через CodeGraph. Ограничивай исследование продуктовым path; символ `pack` из `outputs/audit-*` — probe, не implementation. Для точного symbol используй structural lookup, для строк/сообщений — `rg`.
3. Прочитай текущий caller, domain service, schema и ближайший consumer test. Это предотвращает изменение только CLI без исправления library API.
4. Добавь минимальный regression, который падает по нужной причине. В negative test проверь не только exit/error, но и отсутствие внешних/частичных записей.
5. Исправь root cause в нижнем общем слое. CLI только переводит ожидаемые domain errors в typed output и exit.
6. Выполни focused tests и relevant consumer. После их успеха — требуемый quality subset; полный suite на границе milestone или при изменении ядра. Не повторяй всё бесконечно без новых изменений/сомнений.
7. Запиши actual command, versions, input hashes, expected/observed, exit, skipped и limitations. Обнови статус только своего slice.

Если regression оказался green до исправления, установи причину: не сработал setup, проверяется mock вместо production caller, ошибка возникла раньше исследуемого места или требование уже реализовано. Не «исправляй» тест под желаемый рассказ.

## 2. Карта существующего кода

| Работа | Откуда начать | Что не забыть |
|---|---|---|
| Path/atomic writes | `src/testence/agent/install.py`, `src/testence/application.py`, `src/testence/quality.py` | State/history/temp paths и preflight всех файлов |
| Corpus | `src/testence/benchmark.py`, `corpus/r1-correctness-v1.json`, существующие corpus runners | Registry validation не заменяет executor/evaluator |
| Contracts | `src/testence/contracts/versions.py`, loaders и `contracts/schemas/` | Python validation, JSON Schema, inventory, wheel resources |
| Demo | `src/testence/application.py:run_demo`, `tests/test_application.py` | Installed-wheel consumer, subprocess env, cleanup и pack generation |
| Build | `scripts/installed_wheel_smoke.py`, `scripts/release_artifacts.py`, `scripts/dependency_inventory.py` | Package origin, clean context, exact artifact binding |
| Release | `release/rc-manifest.json`, `tests/test_release_manifest.py`, CI | Тест текущего no-go — не универсальный validator |
| Performance | `bench/scale_profile.py`, `bench/warm_runner_latency.py`, `bench/budgets/` | Время снаружи child, raw samples и отдельный RSS |
| Skills | `src/testence/agent/skill-pack.json`, `agent/skills/` | Hash всех normative bytes, client version и managed conflicts |
| Auth | `src/testence/auth/strategies.py`, `src/testence/api.py` | Реальный refresh/logout/role/redirect transport |
| Completion | `src/testence/evidence/writer.py`, consumers/loaders | Ошибка capture/storage не превращает incomplete в verified |

Пути указаны относительно repo для навигации. Перед редактированием проверь фактическое расположение; line numbers из аудита могли сместиться. Новые файлы добавляй только после проверки, что существующий модуль не решает ту же задачу.

## 3. Path safety: практический алгоритм

Раздели три типа аргументов: явно выбранный trusted root; недоверенный relative member; явно разрешённый внешний input root. Нельзя использовать один permissive helper для всех трёх.

Планируемый helper `checked_member(root, relative, purpose)` должен:

1. Проверить, что `relative` — непустая строка по portable grammar, а не object, int, URI или path с `NUL`.
2. До `join` отвергнуть drive/UNC/device/ADS, root separator, `.`/`..`, пустые segments и неоднозначные spellings. Для новых manifests принимать POSIX slash; legacy backslash нормализовать только adapter с последующей полной проверкой. Windows reserved names и trailing space/dot также неоднозначны и недопустимы для portable artifacts.
3. Разрешить выбранный root; пройти существующие компоненты ниже root через `lstat`, обнаруживая links/reparse points. Для managed writes default — отказ; missing final component допустим, missing parent создаётся только после preflight.
4. Проверить resolved candidate через path-aware containment, не `str.startswith`. `D:/repo-evil` не принадлежит `D:/repo`.
5. Непосредственно перед effect повторить проверки root/parents/prior file identity/hash. Создать новый temporary безопасным exclusive способом в проверенном parent, flush/fsync и заменить только ожидаемый target.

`Path.is_relative_to` в Python 3.10 проверяет структуру пути и сам не раскрывает symlinks; для реального положения нужен `resolve` и отдельная политика ссылок. Python 3.10 — обязательный floor, поэтому более новые удобные методы нельзя использовать без fallback. [Python pathlib 3.10](https://docs.python.org/3.10/library/pathlib.html).

На Windows junction — разновидность reparse point; тест только `is_symlink()` недостаточен. Используй доступные в поддерживаемой Python версии `lstat` attributes/`stat` constants или узкий Win32 adapter, с тестами. Не объявляй все reparse points обычными каталогами. [Microsoft: Reparse Points](https://learn.microsoft.com/en-us/windows/win32/fileio/reparse-points).

Псевдокод ниже иллюстрирует последовательность, **не готовую защищённую реализацию**:

```text
plan = preflight_all_members(root, inputs, expected_state)
if plan.conflicts: return conflict_without_managed_changes
with exclusive_project_writer(root):
    revalidate(plan)
    transaction.stage_verified_bytes(plan)
    transaction.commit_or_recover()
```

Не утверждай, что `resolve` полностью устраняет TOCTOU. Между проверкой и effect другой процесс может сменить directory entry. Safe defaults, cooperative locks, repeated identity checks и no-follow/handle-based primitives уменьшают риск; если полная защита от hostile concurrent filesystem editor не обеспечена, явно зафиксируй границу и отклоняй обнаруженную смену. Не лечи гонку изменением всех прав пользовательского project root.

### Fixtures Windows без privileged symlink

Создай внутри уникального audit/test root `project`, `sibling` и sentinel. Junction `project/.testence → sibling` создаётся штатным `New-Item -ItemType Junction`. В production не запускай PowerShell для path validation — это только fixture setup.

Снимай hashes и listing sibling до/после команды. Проверяй CLI и прямой Python API. В cleanup сначала убирай сам link безопасной операцией, не рекурсивно его target; все resolved paths должны принадлежать test root. Не пропускай junction coverage потому, что `os.symlink` недоступен. Отдельный mandatory Linux runner проверяет symlink cases.

## 4. Транзакции: почему несколько replace недостаточно

Политика и её lock — несколько файлов. Filesystem не предоставляет универсальной атомарной транзакции над ними. Обещать можно: полный preflight, обнаружение incomplete state, детерминированный recovery и отсутствие ложного accepted state.

Минимальные состояния journal: `prepared`, `applying`, `committed`, `recovering`, `recovered`, `conflict`. Journal содержит transaction ID, project identity, old/new state digests, операции с expected before/after hashes, snapshot locations и progress. Секретное содержимое не дублируется в printable receipt.

Рекомендуемый протокол:

1. Вычислить все add/change/delete/keep и проверить **все** conflicts/overrides/compatibility до изменения managed files.
2. Получить exclusive writer lock; повторить preflight, потому что человек мог изменить файл во время планирования.
3. Подготовить immutable snapshots и incoming staged bytes; проверить их hashes. Записать durable `prepared` journal.
4. Выполнять операции с проверкой текущих bytes. После каждой durable progress update. Остальные Testence readers/policy users должны заметить in-flight journal и отказать от использования «принятого» состояния.
5. Проверить итоговые bytes; опубликовать новый config/lock в согласованном commit protocol; только после этого `committed` и success receipt.
6. При ошибке откатить только те after-images, которые ещё равны записанным hashes транзакции. Если человек уже изменил файл, остановить recovery в conflict, сохранить оба набора bytes и объяснить действия. Не затирать правку «ради атомарности».

Lock по одному PID ненадёжен: PID может использоваться заново. Нужны owner/process-start или OS locking primitive и явный recovery stale state. Выбор маленькой cross-platform lock dependency допускается с review; собственная lockfile-реализация обязана иметь contention/crash tests.

`fsync` файла не равен полной гарантии crash durability всей файловой системы. Документируй гарантии среды и recovery. Unit test с mock `os.replace` дополняет, но не заменяет child-process kill после выбранной journal phase.

## 5. Правильный rollback с overrides

Храни две независимые величины:

```text
upstream_digest = hash(pack manifest + shipped file inventory)
effective_digest = hash(installed manifest including approved overrides)
```

Rollback version label выбирает запись истории; перед записью проверяются snapshot bytes по effective inventory. Нельзя вернуть upstream digest в lock, а фактически восстановить локальную изменённую policy без отражения этой разницы.

Diff для rollback вычисляется так же, как update. Пример: v1 содержит `a`, v2 — `a,b`. Возврат к v1 удаляет `b`, только если `b` всё ещё равен v2 managed bytes. Изменённый человеком `b` — conflict. Missing `a` snapshot — ошибка **до** удаления `b`. Файл, никогда не входивший в accepted lock, не трогается.

Не снапшоть живой файл вместе со старым upstream hash, если файл уже изменён. Сначала либо подтвердить действующий override и записать effective hash, либо conflict. Legacy snapshots без trusted manifest не «исправляются» новым digest автоматически.

## 6. Corpus: не перепутай каталог, executor и evaluator

Это три слоя. Каталог описывает case; executor запускает SUT/tests; evaluator независимо сопоставляет результат с truth. Один `validate_corpus_registry` не должен объявлять завершение всех трёх.

Пример состава case `/2` (схему определить в S3-01, пример не готовый JSON):

```text
case_id, stratum, split
target_id, base_revision, variant_revision_or_patch_digest
selector {adapter, file, nodeid_or_case_key}
scenario_digest, expected_scope, truth {outcome, reason, source_ref}
reset_recipe_ref, seed, deadline_ms
inputs [{path, size_bytes, sha256}]
```

Допустимые adapters — явный allowlist; выполнение через argv array, без `shell=True`. Наличие строки в registry не даёт права выполнять неизвестный remote script. Runtime Python тестов доверенный, SUT/evidence text — данные.

Freeze inventory фиксирует bytes, а не git mtime. `git ls-files` не включает незакоммиченные новые файлы; локальный snapshot должен явно включать intended inputs или отказывать. Symlinks в переносимом frozen inventory лучше отвергать. Case sensitivity/Unicode/Windows reserved names нормализуются до проверки duplicate paths, без молчаливого слияния двух разных файлов.

Digest protocol versioned: отсортированные UTF-8 path bytes и unambiguous serialization record `{path,size,sha256}`; не склеивай строки без separators/length. Не используй Python `hash()`: он непостоянен между процессами. Registry hash не должен включать собственный freeze hash; отдельный lock решает цикл.

Пример отрицательной проверки: после freeze изменить byte source, оставить registry/lock прежними → verify отказал. Затем изменить lock digest, но не связанные review scope/receipt → acceptance всё равно отказал. Явная команда refreeze создаёт новую revision и invalidates предыдущий truth/holdout review.

Runner mutant `return passed` должен быть обнаружен evaluator даже если сам Testence summary тоже passed. Expected selected count берётся из протокола, не из observed run. Failed subprocess/empty control не удаляется из результатов. Разные параметры одного семантически одинакового case считаются repeats, если truth/protocol не обосновывают независимый риск.

Не передавай triage-агенту truth flags из registry, patch names или скрытый mode bug/control. Это утечка правильного ответа, а не помощь в анализе. Evaluator хранит truth отдельно; agent bundle содержит требование и наблюдения. После измерений публичная таблица может раскрыть truth вместе с результатами, но её нельзя использовать в том же frozen holdout для повторного tuning.

Независимость человека нельзя проверить наличием двух строк `reviewer`. Машинный validator проверяет binding/scope/signature/channel metadata; custodian/maintainer подтверждает, кто и что reviewed. Если такого доверенного основания нет — `external_pending`.

## 7. Wheel: выбранная установка и проверяемые байты

Предпочтительный orchestrator работает из build-tools environment и создаёт fresh consumer venv с `system_site_packages=False`. Он не импортирует Testence для предварительной проверки wheel. Parent валидирует artifact, делает private immutable input copy, устанавливает её, запускает child `python -I ...` из временного consumer directory.

Минимизируй наследуемую среду: не передавай `PYTHONPATH`, `PYTHONHOME`, случайные `TESTENCE_*`, `PYTEST_ADDOPTS`, agent credentials. Сохрани необходимые OS variables/temp/browser cache либо передай их явно. Зафиксируй browser executable/version в receipt. Не меняй глобальную среду пользователя.

Проверки в child:

- `testence.__file__` и distribution metadata принадлежат новому venv, не editable checkout.
- Wheel name/METADATA/version и expected candidate hash согласованы.
- Все нормативные package code/schema/skill/demo resources присутствуют и соответствуют wheel payload.
- На одном artifact выполняются library/CLI/browser/demo consumers; receipt хранит реальные observed paths, а portable public receipt удаляет ненужный локальный user path.

Installed `RECORD` — CSV с hash вида `algorithm=urlsafe-base64-no-padding`; это не hex. Hash/size могут отсутствовать, в частности у `RECORD`/`.pyc`; установка может изменить scripts и metadata. Поэтому не требуй полного тождества archive и installed tree по каждому служебному byte: проверяй нормативный payload и учитывай transformations явно. [PyPA: Recording installed projects](https://packaging.python.org/en/latest/specifications/recording-installed-packages/).

Сценарий «wheel B той же версии» должен отказать, когда candidate manifest ожидает hash A, а передан B. Если пользователь осознанно выбрал B как новый candidate, fresh install и smoke B допустимы, но нельзя выпустить receipt A. Версия не заменяет binding.

Не сравнивай два `RECORD` без чтения actual payload; обе metadata могли остаться прежними после порчи файла. При отсутствии полного evidence возвращай unverified/failed, а не fallback по package name.

## 8. Release provenance без бесконечного SHA-цикла

Правильная последовательность:

```text
source commit C (code/version/locks/tests/protocol)
    → clean build of wheel W and sdist S
    → consumer/scans/corpus receipts bound to C and W/S
    → candidate manifest M references C, W, S and receipt hashes
    → owner decision D references digest(M)
    → authorized publication of exactly W/S with M and D
```

M и D — post-build artifacts, им не обязательно быть в C. Не добавляй их в commit, требуя, чтобы его SHA осталось C. Если версия/код после C меняются — это новый candidate и новые соответствующие проверки.

Manifest validator не доверяет всем receipts только потому, что они лежат в папке `release`. Для каждого вида checks задаётся expected producer/schema/input binding/required fields. Не делай универсальный check `receipt['status']=='passed'`. Unknown producer/version/foreign candidate не принимается автоматически.

Owner decision не входит в digest того же payload, который подписывает: отдели immutable candidate body и approval record. В local synthetic tests можно подставить test trust store, но он не экспортируется как реальная подпись/approval.

## 9. SBOM и supply chain: два разных списка

`pyproject` requirements — диапазоны допустимых версий. Installed environment inventory — конкретный graph конкретной ОС/Python/extras. SBOM acceptance относится ко второму, сохраняя связь с первым.

Собирай inventory в том же consumer venv после exact install. Проверяй metadata dependencies с environment markers, не включай Windows-only dependency в Linux graph как установленную. Отдельно сохраняй build tooling и browser payload provenance. Не перемешивай глобальные пакеты `.venv` разработчика с runtime wheel.

License поля могут быть incomplete: `NOASSERTION` — неизвестность для review, не доказательство совместимости. Известные licenses не означают, что права на private fixtures автоматически есть. Реестр происхождения assets создаётся отдельно от Python dependency graph.

GitHub publishing: OIDC permission выдаётся только отдельному publish job, environment защищается review rules; registry configuration должна совпадать с repo/workflow/environment. Не ставь `id-token: write` на весь CI ради удобства. [PyPI: Publishing with a Trusted Publisher](https://docs.pypi.org/trusted-publishers/using-a-publisher/).

## 10. Demo, которое действительно объясняет продукт

Используй маленький packaged Python loopback SUT, чтобы не требовать npm install исходного benchmark. Даже synthetic SUT должен иметь независимый authoritative state. Bug mode пропускает persistence, healthy/control сохраняют; одна кнопка и один read-only oracle достаточны.

Один run ID на сценарий, отдельные data namespaces и reset. `project.name` не должен быть единственным постоянным namespace для нескольких проектов с совпадающими именами. Выбирай свободный порт через реальное bind/listen, не освобождай пробный socket задолго до запуска server — это гонка.

Fixture teardown обязателен в `finally` и при timeout. Stop только процессы/contexts, которыми владеет demo; `taskkill /IM chrome.exe` недопустим. Сохрани диагностический subprocess stdout/stderr с redaction, bounded size и schema result; JSON stdout CLI не смешивай с progress logs.

Pack создаётся штатным production path, а не копированием старого sample `pack.json`. Oracle event должен реально ссылаться на action/claim/attempt. Validated example verdict может быть шаблонным, но references вычисляются по новому pack; нельзя хардкодить его старый digest.

Отдельно тестируй запрет «ложного ожидаемого failure»: syntax error/нет браузера/упал server/истёк oracle deadline тоже могут дать pytest exit 1/2/3, но demo обязан вернуть failed.

## 11. Capture и измерения: где легко получить красивую ложь

`body = response.body(); body[:limit]` ограничивает retained output, но уже мог прочитать целиком большой body. Если выбранный adapter не позволяет bounded acquisition, safe profile пропускает body и сохраняет metadata/omission; не объявляет acquisition memory bounded. UI/required proof при необходимости использует отдельный небольшой authoritative endpoint. Это проектное решение надо явно проверить в threat/resource matrix.

Считай ring по events **и** bytes; long one-event payload иначе обходит record cap. Не включай raw secret в truncation suffix или exception. Потеря required evidence не должна исчезнуть при sanitize. Тест canary проверяет всё содержимое retained files/archives, не только top-level JSON.

Memory profiles раздели: Python traced allocation, process RSS и process-tree RSS. Browser/Node могут жить вне Python; reuse общего attached browser требует документированного baseline и не включается незаметно в fresh comparison. Инструмент замера должен хранить sampling interval и пропуски, а не выдавать sampled maximum за точный OS peak без основания.

Cold wall time измеряет parent вокруг launch→completion. Warm/cold исключения перечисляются до запуска; первая warm итерация сохраняется raw и явно исключается только из steady агрегата. p95 на трёх samples практически отражает максимум; это smoke, не полный профиль распределения. Timeouts/crashes остаются в raw и completion denominator.

Новый budget после неудачного прогона не подкручивается автоматически. Сначала назвать cause, потом отдельное reviewed изменение протокола с новой версией. Равные JSON hashes проверяют deterministic serialization, не browser flake.

## 12. Как не потерять исходные R1 требования

Аудит A01–A09 — не полный список всего R1. После закрытия девяти findings всё ещё проверить auth refresh/logout, screenshot/trace defaults, retention, actual role filters, stale requirement proofs, TestOps history, real-agent author/repair, independent corpus и pilots.

Возвращайся к таблице R01–R24 в [матрице](acceptance.md). Сначала consumer check, затем narrow fix только выявленного пробела. Нельзя автоматически переписать уже работающий lifecycle только потому, что он упомянут в старом ТЗ.

Не закрывай внешний blocker локальным Markdown. Полезный handoff при отсутствии tenant: полностью работающий offline adapter suite, pinned CLI recipe, sanitized fixture bundle, exact live commands, ожидаемые counts/links и pending access. Неполезный: повторять «нужен tenant», не сделав независимую локальную работу.

## 13. Готовый стартовый запрос для исполняющего агента

> Реализуй этап 3 Testence по `docs/stages/03-r1-release/README.md`, `implementation-guide.md` и `acceptance.md`. Начни с S3-00, затем соблюдай зависимости. Сохрани существующие изменения. Перед каждым slice воспроизведи соответствующий negative case, после исправления докажи отказ и positive consumer behavior. Не ограничивайся изменением tests/docs/status: выполняй normative behavior. Не меняй старые audit receipts. Новые commands/schema fields сначала реализуй и проверь, затем публикуй в docs. Веди короткий progress file с S3/acceptance IDs и ссылками на actual receipts. При внешнем blocker закончи всю независимую локальную работу, явно сохрани `external_pending` и продолжи доступные задачи. Не фабрикуй пользователей/review/CI receipts и не называй engineering handoff полной приёмкой R1. Публикация и внешние сообщения выполняются только в пределах уже выданного разрешения.

## 14. Формат результата одной итерации

Пиши: какая observable проблема устранена; какие paths/contracts затронуты; конкретный consumer before/after; какие checks реально прошли и что skipped; какой receipt доказывает это; что требуется дальше. Не пиши «всё готово», если прошёл только unit subset. Не оценивай собственную работу процентом без полного denominator требований.
