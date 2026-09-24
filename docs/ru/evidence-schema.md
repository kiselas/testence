# Схема доказательств `testence/2` (нормативная)

Один JSON-объект на строку в `runs/<run-id>/run.jsonl`. Формат append-only, UTF-8,
окончания строк `\n` на всех платформах, fsync после каждого события. Crash safety —
сама цель и стоит около 0,5 мс на событие. Поля только добавляются внутри major version;
breaking changes повышают версию, а parsers должны явно отклонять чужие версии.

Гарантию fsync даёт операционная система. На macOS `fsync` передаёт данные накопителю,
но не сбрасывает его собственный кэш записи: для этого нужен `F_FULLFSYNC`, который
дороже на порядки. Падение или убийство процесса и там ничего не теряет, а при потере
питания могут пропасть последние события. Testence оставляет обычный `fsync` на всех
платформах, чтобы не жертвовать бюджетом на событие ради этого случая.

**Один файл на процесс, но не на запуск.** При `pytest -n` каждый worker пишет
`run-<worker>.jsonl` рядом с controller `run.jsonl` внутри одного каталога,
названного через `TESTENCE_RUN_ID`. Это не предпочтение: четыре процесса, пишущие один
файл, потеряли 27% событий и создали оборванные строки, потому что lock writer —
`threading.Lock`, не действующий между процессами согласно ADR-0012.

**Readers обязаны объединять файлы и не доверять `seq` между ними.** `seq`
начинается заново в каждом процессе и упорядочивает события только внутри одного
ledger. Raw files могут содержать отдельные `run.start`/`run.end` уцелевших процессов.
Читайте через `testence.metrics.load_run`: он объединяет события по timestamp,
нормализует legacy statuses, сверяет collection inventory с terminal events и
возвращает один логический `run.end`. Started case без terminal становится `aborted`,
а selected case, который не начали, — `not_run`.

Controller также ведёт `runs/<run>/manifest.json` схемы
`testence/run-manifest/2`. Файл атомарно заменяется после `run.start`,
`collection.end` и `run.end`; финальный checkpoint связывает project/run identity,
selected scope, exit status и каждый ledger shard через relative name, byte size и
SHA-256. Reader сохраняет полные JSONL-записи перед оборванным хвостом, но помечает
логический run как `incomplete`. Пустые или отсутствующие ledgers, running или
несогласованный manifest, смешанные identity, повторный event ID и несколько terminal
events одной попытки также создают явную проекцию `ledger.damage` и не могут стать
успешным run. Повреждение внутри записи с завершённой строкой и неизвестный major
отклоняются: безопасно интерпретировать такой prefix нельзя. Legacy `/1` без manifest
остаётся читаемым с assurance `unverified`.

## Envelope каждого события

| Поле | Тип | Значение |
|---|---|---|
| `v` | string | версия схемы, `"testence/2"` |
| `project_id` | string | namespace репозитория, не зависящий от checkout path |
| `run_id` | string | ID запуска `r-YYYYMMDD-HHMMSS-xxxxxx`, общий для workers |
| `run` | string | deprecated compatibility alias для `run_id` |
| `worker` | string | ID процесса/shard либо `controller` |
| `event_id` | string | уникальный `<worker>:<seq>` внутри run |
| `seq` | int | монотонный **внутри процесса**, начинается с 1 |
| `ts` | string | UTC ISO-8601, миллисекунды, суффикс `Z`; единственный порядок между файлами |
| `kind` | string | вид события, см. ниже |
| `test` | string? | ID теста; отсутствует у run-level событий |

Каждое test-событие также содержит `case_id`, `variant_id`, `attempt_id`, `proof_id`
и digest-only `parameters`. Полный pytest `nodeid` остаётся source locator. ID scenario
из PlanSpec служит явным логическим case ID; fallback по source не обещает пережить rename.

## Виды событий и payload

| Kind | Поля payload |
|---|---|
| `run.start` | `testence` (version), `fingerprint` {os, python, base_url, attach, worker}, optional `redaction` (`testence/redaction-policy/1`: `keys`, `allow_keys`, `url_params`, `pii` — только имена), `allure_naming` (`allure-pytest`/`nodeid`), `allure_parameters` (`values`/`digest`) |
| `run.end` | `duration_ms`, `exit_code`, `run_status`, counts `passed`/`failed`/`broken`/`skipped`/`aborted`/`not_run` |
| `test.start` | `display_name`, `file`, `code` (12-hex digest файла теста), `nodeid`, `markers`, optional `owner` PlanSpec, `risk` scenario, `requirements` и `issues`; `allure` {`full_name`, `test_case_id`, `history_id` (формулы allure-pytest), `title_path`, `package`, `suite`, `test_class`, `test_method`, `labels`, `links`, `tags`, `parameters` (замаскированные пары name/value), optional `title`, `description`, `description_html`, `docstring`, `plan_scenario` {title, claims, plan}} |
| `test.phase` | `nodeid`, `display_name`, `phase`, pytest phase status, duration и optional error/xfail/xpass metadata |
| `test.end` | `nodeid`, `display_name`, canonical `status` (`passed`/`failed`/`broken`/`skipped`/`aborted`/`not_run`), `phase`, `duration_ms`, optional `pack`/error/xfail/xpass metadata, `error_kind` (`assertion`/`oracle`/`infrastructure`/`test_code`), `error_trace` (ограниченный, замаскированный), `screenshot` (относительно прогона, `evidence.screenshots: always`) |
| `test.waits` | `waited_ms`, `ops` (count), `by_op` {op: {ms, n}}, `top` (5 самых медленных) |
| `step.start` | `step` (id), `intent` (фраза человека), `target`? (описание), `depth` |
| `step.end` | `step`, `status`, `duration_ms`, `depth`, `children`, `fingerprint`? (green runs), `error`? |
| `net` | зарезервировано; v0 хранит network в packs, inline events могут появиться после E4 |
| `console` | зарезервировано по той же причине |
| `oracle` | `name`, `ok`, `diff`? либо typed `expected`/`actual`, `observation` и связанная `operation` |
| `assertion` | `assertion_id`, `claim_id`, `oracle_kind`, `outcome`, typed/redacted `expected`, `actual` и `source` |
| `pack` | `dir` (relative), `sections_est_tokens` {aria, network, console, oracle}, `error` |
| `native.used` | `intent` — выполнен блок `ex.native`; действия внутри не записывались по одному |
| `testplan.unresolved` | `count`, `policy` (`warn`/`fail`), `entries` [{`id`?, `selector`?}] — записи test plan Allure без совпавшего теста |
| `note` | `text` и произвольные поля |
| `ledger.damage` | созданные reader поля `integrity_code`, `error` и optional shard `path`; raw ledgers не меняются |

## Execution и assurance

Статус выполнения pytest и достоверность proof являются разными осями. Reconciliation
добавляет в каждый логический `test.end` поле `assurance`: `verified`, `violated`,
`inconclusive` или `unverified`. Прошедший тест становится `verified`, только если у
связанного PlanSpec есть inventory обязательных assertions, каждая обязательная
assertion выполнилась ровно один раз и успешно, claim/oracle bindings совпали, а SHA-256
digests плана, теста и policy актуальны. Обычный `pass`, пропущенная ветвь, повторная или
неизвестная assertion и stale digest остаются `unverified`. Недоступный oracle даёт
`inconclusive`, failed assertion — `violated`. Эта проекция не меняет неизменяемый
pytest status. Optional assertions не увеличивают required denominator.

Expected-state observation записывает classification, причину, число reads и elapsed
time. Связанная operation содержит method/path, correlation или GraphQL identity,
response status и число совпавших requests. Reconciliation использует outcome
assertion; polling не меняет и не повторяет mutation.

Когда pytest-тест связан с PlanSpec через marker `testence`, writer аддитивно добавляет
`plan` (`schema`, `id`, repository-relative `path`, SHA-256 digest), `claims` и
inventory assertions. `test.start` также связывает полные digests исходника теста и
assurance policy. Старые readers могут их
игнорировать. Identity migration относится к `testence/2` и не меняет `/1` задним числом.

Два payload fields появились потому, что без них метрики были неверны. Любой
агрегатор ledger обязан учитывать оба:

- **`children` в `step.end`.** Метод ActionMap композитен, поэтому шаги вложены, а
  длительность composite уже включает children. Суммирование всех `step.end`
  учитывало миллисекунды дважды: в одном запуске 48 из 95 step starts были вложенными,
  и сумма шагов превысила длительность теста, что невозможно. Latency одного
  interaction считается по leaves с `children == 0`. В старых ledgers поля нет;
  агрегируйте их прежним способом, не угадывая структуру.
- **`code` в `test.start`.** Digest файла теста позволяет считать flakiness по
  паре `(test, code)`. Без него переход fail → pass во время authoring считается
  flaky: suite из девяти тестов показал 44,4% для четырёх сценариев, хотя ни один не
  флапал на неизменном коде.

Envelope key `test` в новых lifecycle events содержит полный pytest nodeid;
`display_name` остаётся короткой подписью для человека. Legacy events `pass`/`fail`
нормализуются в `passed`/`failed`. `nodeid` и `markers` нужны экспортёрам отчётности
([ADR-0013](adr/0013-reporting-as-export.md)): формату требуется полный адрес теста и
собственная таксономия suite. Это пример общего правила: нужные интеграции данные
становятся **новым полем ledger**, а не instrumentation тестового кода. Оба поля
необязательны при чтении: старые ledgers экспортируются с именем теста в качестве
адреса и без tags.

## Evidence pack упавшего теста

Каталог `runs/<run>/<test>/pack/`, обычные файлы, доступные любому агенту:

| Файл | Содержимое | Token budget |
|---|---|---|
| `pack.json` | машинный индекс: test, PlanSpec, claims, error, page_url, размеры секций, taxonomy и путь к verdict template | — |
| `manifest.json` | `testence/pack-manifest/2`: identity, relative path, bytes и SHA-256 каждого artifact | — |
| `TRIAGE.md` | контракт судьи: таксономия и инструкции | — |
| `verdict.template.json` | заготовка `testence/verdict/2` с точными project/case/variant/attempt/run/proof и plan/test/claim ID | — |
| `verdict.json` | типизированный verdict агента после успешной валидации; создаётся агентом, а не runner | — |
| `aria.txt` | ARIA snapshot страницы в момент падения | 8 000 |
| `network.jsonl` | полный журнал API requests с начала теста: body для non-2xx и `failure` для aborted requests | 8 000 |
| `console.txt` | errors, warnings и pageerrors | 2 000 |
| `oracle.json` | UI↔API diff, если сработал oracle | 2 000 |
| `heal.json` | предложение при drift: новый адрес, score, rationale и suggested edit ([ADR-0011](adr/0011-heal-as-proposal.md)) | — |
| `browser.json` | manifest live attach: CDP endpoint и page URL | 500 |
| `screenshot.png` | для людей; агенты начинают с текста | — |
| `full-*` | расширенный sanitized content при срабатывании budget; не более 262 144 символов | — |

Budgets применяются обрезкой с явным marker
`<truncated: full content in …>`: агент всегда отличает маленькую секцию от
обрезанной. Token count приблизителен, около 4 bytes/token; размер в bytes можно
получить из файла.

Sanitization выполняется до записи ledger или текстов pack. Structured keys для
Authorization, cookies, passwords, tokens, API/private keys, значения Bearer/Basic,
секретные query parameters и настроенные username/password Testence заменяются на
`<redacted>`. Строка ledger ограничена 16 384 символами. Manifest содержит только
имена файлов относительно pack и намеренно не включает собственный hash. Screenshot
остаётся визуальным capture и может содержать данные приложения, поэтому ограничение
alpha-кандидата на production data действует до visual masking и полного security review T12.

## Совместимость `/1`

Readers принимают `testence/1`, нормализуют legacy status spellings и сохраняют
неизвестные поля. Отсутствующие identity/proof обозначаются `legacy`/`unknown`, assurance
остаётся `unverified`; adapter не выдумывает успешное proof. Writers создают только `/2`.
Неизвестный major отклоняется до формирования отчёта или quality result.

## Таксономия вердиктов

`real_bug` · `test_bug` · `behaviour_change` · `ui_change` · `flaky_timing` ·
`environment`.
Определения находятся в `TRIAGE.md` каждого pack, поэтому артефакт самодостаточен.
Три жёстких правила: исчезнувший со страницы элемент — `real_bug`, а не drift;
исправление `ui_change` или `flaky_timing` является проверяемым diff, но не runtime
patch; если все наблюдаемые слои согласованы между собой и только тест расходится с
ними, PlanSpec отделяет `test_bug` от настоящего `behaviour_change` согласно ADR-0014.

`blocked_on` называет единственный факт, которого не хватает для окончательного
вердикта, обычно спецификацию. Вердикт с этим полем является provisional и явно это
сообщает.

`testence verdict validate <pack>/verdict.json --plan <planspec> --json` проверяет
версию схемы, совпадение plan/test/полного набора claims, правила abstention и четыре
неизменяемые привязки из template: `plan_digest`, `test_digest`, `policy_digest` и
`pack_digest`. Digest pack считается по точным байтам immutable manifest; manifest
покрывает `pack.json` и каждый captured artifact через byte size и SHA-256. Редактируемые
файлы `verdict.*` намеренно не входят в manifest, чтобы не создавать циклический digest.

Каждая evidence-ссылка обязана указывать на файл из manifest внутри pack. Fragment у
JSON или JSONL разрешается как RFC 6901 JSON Pointer с декодированием `~0` и `~1`.
Несуществующий pointer, изменённый artifact, файл вне manifest, stale digest,
cross-attempt event, внешний путь или URL приводят к fail-closed отказу.

## Связанное предложение repair

`testence/repair-proposal/1` связывает предлагаемый source diff с проверенным verdict,
семантикой PlanSpec и точным исходным состоянием файла. Команда проверки:

```bash
testence repair validate repair.json --verdict <pack>/verdict.json \
  --plan specs/<feature>.md --base tests/<test>.py \
  --pack <pack> --evidence-root <proof-root> --json
```

Только `ui_change`, `flaky_timing` и `test_bug` разрешают соответственно locator,
timing и test implementation repair. Proposal не может менять claims и обязан
сохранить protected plan digest. Требуются ровно три proof: healthy (`passed` и
`verified`), defect control (`failed` и `violated`) и harmless control (`passed` и
`verified`). Stale source base или отсутствующий proof artifact отклоняется до того,
как patch можно считать готовым к review.
