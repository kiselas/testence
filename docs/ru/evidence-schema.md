# Схема доказательств `testence/1` (нормативная)

Один JSON-объект на строку в `runs/<run-id>/run.jsonl`. Формат append-only, UTF-8,
окончания строк `\n` на всех платформах, fsync после каждого события. Crash safety —
сама цель и стоит около 0,5 мс на событие. Поля только добавляются внутри major version;
breaking changes повышают версию, а parsers должны явно отклонять чужие версии.

**Один файл на процесс, но не на запуск.** При `pytest -n` каждый worker пишет
`run-<worker>.jsonl` рядом с controller `run.jsonl` внутри одного каталога,
названного через `TESTENCE_RUN_ID`. Это не предпочтение: четыре процесса, пишущие один
файл, потеряли 27% событий и создали оборванные строки, потому что lock writer —
`threading.Lock`, не действующий между процессами согласно ADR-0012.

**Readers обязаны объединять файлы и не доверять `seq` между ними.** `seq`
начинается заново в каждом процессе и упорядочивает события только внутри одного
ledger. Перечисляйте файлы через `testence.evidence.ledger_paths(run_dir)` и читайте
через `testence.metrics.load_run`, который объединяет их по timestamp. В итоговом
запуске допустимы отдельные `run.start` и `run.end` каждого worker; worker указан в
fingerprint.

## Envelope каждого события

| Поле | Тип | Значение |
|---|---|---|
| `v` | string | версия схемы, `"testence/1"` |
| `run` | string | ID запуска `r-YYYYMMDD-HHMMSS-xxxxxx`, общий для workers |
| `seq` | int | монотонный **внутри процесса**, начинается с 1 |
| `ts` | string | UTC ISO-8601, миллисекунды, суффикс `Z`; единственный порядок между файлами |
| `kind` | string | вид события, см. ниже |
| `test` | string? | ID теста; отсутствует у run-level событий |

## Виды событий и payload

| Kind | Поля payload |
|---|---|
| `run.start` | `testence` (version), `fingerprint` {os, python, base_url, attach, worker} |
| `run.end` | `duration_ms`, `passed`, `failed` |
| `test.start` | `file`, `code` (12-hex digest файла теста), `nodeid` (полный pytest address), `markers` (отсортированные имена) |
| `test.end` | `status` ("pass"/"fail"), `duration_ms`, `pack`? (relative dir при fail) |
| `test.waits` | `waited_ms`, `ops` (count), `by_op` {op: {ms, n}}, `top` (5 самых медленных) |
| `step.start` | `step` (id), `intent` (фраза человека), `target`? (описание), `depth` |
| `step.end` | `step`, `status`, `duration_ms`, `depth`, `children`, `fingerprint`? (green runs), `error`? |
| `net` | зарезервировано; v0 хранит network в packs, inline events могут появиться после E4 |
| `console` | зарезервировано по той же причине |
| `oracle` | `name`, `ok`, `diff`? (список {field, ui, api}) |
| `pack` | `dir` (relative), `sections_est_tokens` {aria, network, console, oracle}, `error` |
| `note` | `text` и произвольные поля |

Когда pytest-тест связан с PlanSpec через marker `testence`, writer аддитивно добавляет
ко всем его событиям два optional-поля: `plan` (`schema`, `id`, repository-relative
`path`) и `claims` (точный список claim ID этого теста). Старые readers могут их
игнорировать; поэтому версия envelope остаётся `testence/1`.

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

`nodeid` и `markers` нужны экспортёрам отчётности
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
| `TRIAGE.md` | контракт судьи: таксономия и инструкции | — |
| `verdict.template.json` | заготовка `testence/verdict/1` с точными plan/test/claim ID; агент заполняет её как `verdict.json` | — |
| `verdict.json` | типизированный verdict агента после успешной валидации; создаётся агентом, а не runner | — |
| `aria.txt` | ARIA snapshot страницы в момент падения | 8 000 |
| `network.jsonl` | полный журнал API requests с начала теста: body для non-2xx и `failure` для aborted requests | 8 000 |
| `console.txt` | errors, warnings и pageerrors | 2 000 |
| `oracle.json` | UI↔API diff, если сработал oracle | 2 000 |
| `heal.json` | предложение при drift: новый адрес, score, rationale и suggested edit ([ADR-0011](adr/0011-heal-as-proposal.md)) | — |
| `browser.json` | manifest live attach: CDP endpoint и page URL | 500 |
| `screenshot.png` | для людей; агенты начинают с текста | — |
| `full-*` | необрезанные оригиналы, если budget ограничил секцию | — |

Budgets применяются обрезкой с явным marker
`<truncated: full content in …>`: агент всегда отличает маленькую секцию от
обрезанной. Token count приблизителен, около 4 bytes/token; размер в bytes можно
получить из файла.

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
версию схемы, совпадение plan/test/полного набора claims, правила abstention и наличие
каждого указанного evidence-файла внутри pack. Ссылки наружу и URL запрещены.
