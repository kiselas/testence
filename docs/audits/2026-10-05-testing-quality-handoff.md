# AUD-Q26: handoff и доказательства

Дата: 2026-10-05. Plan/claim IDs и исследования:
[Q26-01–Q26-03](2026-10-05-testing-quality-research.md).

## Статус кандидата

Выполнен `git fetch origin`; live remote main:
`15ad5d23385dc64c447c7077cb280972185838a4`. Новых коммитов в origin/main нет
(проверены также live remote heads). База slice: `d527312`.
Два локальных коммита прошлого аудита и незавершённые правки сохранены.
Работа остаётся на main; push/release не выполнялись.
Implementation revision: **ebc3d7192df091cd3d48ddb8bd6ffc36a735f85b**.
Коммиты slice: `55f24fe` (deadline/provenance/doctor), `75ce003`
(actual interpreter ownership), `ebc3d71` (matching-state mutation control).
Source и тесты заморожены для final runs; последующие правки относятся к документам.

## Изменённые файлы

- `src/testence/_process.py`, `_process_gate.py`, `mcp.py`: owned deadline и structured error.
- `src/testence/engine/native_routes.py`, `engine/playwright_cdp.py`, `dsl/steps.py`,
  `oracle.py`: scoped native provenance, aborted records, cleanup, oracle explanation.
- `src/testence/engine/__init__.py`, `application.py`: FFmpeg hint и configured video doctor.
- `tests/test_owned_process.py`, `test_mcp.py`, `test_native_routes.py`, `test_native.py`,
  `test_route_mocking.py`, `test_application.py`: deadline/provenance/lifecycle controls.
- en/ru MCP и feature docs, ADR-0029/0030, research и этот handoff.

## Development evidence

Синтетические targets, loopback и ignored raw artifacts. Windows, msedge, port 0.
Все pytest-команды ниже начинаются с `uv run pytest`, basetemp не переиспользованы.

| Run / ignored log | Команда после pytest | Результат |
|---|---|---|
| `outputs/cycle2-negative.log` | `tests/test_mcp.py tests/test_application.py -q -k 'invalid_run_deadlines or run_timeout_returns or missing_video_encoder' --basetemp=.tmp-pytest-cycle2-negative` | 11 failed, 45 deselected, 2.50 s до fixes: invalid timeout, lost structured run reference, wrong FFmpeg hint |
| `outputs/cycle2-controls.log` | тот же набор, `--basetemp=.tmp-pytest-cycle2-controls` | 1 failed, 10 passed: test предполагал error summary для пустого run, inspector корректно вернул incomplete; исправлен harness |
| `outputs/quality-20261005-focused.log` | `tests/test_owned_process.py tests/test_mcp.py tests/test_application.py -q --basetemp=.tmp-pytest-quality-20261005-focused --durations=8` | 60 passed, 68.97 s; source до native/video doctor |
| `outputs/quality-native-negative.log` | `tests/test_route_mocking.py::test_native_mocking_in_a_real_browser -q --basetemp=.tmp-pytest-quality-native-negative` | outer failed, 33.66 s; внутри 4 failed, 10 passed: оба fabricated save не отвергнуты как mocked, оба abort не помечены |
| `outputs/quality-native-positive.log` | `tests/test_route_mocking.py tests/test_native.py -q --basetemp=.tmp-pytest-quality-native-positive --durations=6` | 1 failed, 8 passed, 47.25 s; внутри 2 harness failures: MockApp даёт default JSON 200 для неизвестной entity, не 404 |
| `outputs/quality-native-live2.log` | `tests/test_route_mocking.py tests/test_native.py tests/test_expected_state_corpus.py -q --basetemp=.tmp-pytest-quality-native-live2 --durations=8` | 1 failed, 21 passed, 59.06 s; harness вызвал Response.json property как метод; исправлено |
| `outputs/quality-native-live3.log` | `tests/test_route_mocking.py -q --basetemp=.tmp-pytest-quality-native-live3 --durations=5` | 4 passed, 48.05 s; nested corpus 14 passed; независимый реальный body проверен |
| `outputs/quality-native-lifecycle.log` | `tests/test_native_routes.py tests/test_native.py -q --basetemp=.tmp-pytest-quality-native-lifecycle` | 9 passed, 5.21 s; 340 model sequences, новые страницы, смена context |
| `outputs/quality-deadline-live.log` | `tests/test_mcp.py tests/test_owned_process.py -q --basetemp=.tmp-pytest-quality-deadline-live --durations=5` | 35 passed, 24.35 s; real deadline 8.43 s, incomplete ledger, listeners stopped, subsequent inspect |
| `outputs/quality-video-doctor.log` | `tests/test_application.py -q -k 'doctor_probes or missing_video_encoder' --basetemp=.tmp-pytest-quality-video-doctor` | 6 passed, 23 deselected, 0.39 s; simulated missing encoder; real video doctor добавлен затем |
| `outputs/quality-gate-redirector.log` | `tests/test_owned_process.py tests/test_mcp.py -q --basetemp=.tmp-pytest-quality-gate-redirector --durations=5` | 36 passed, 21.79 s; gate сообщает actual interpreter PID, привязка с задержкой 0.2 s закрывает redirector race; real pytest deadline 8.41 s |
| `outputs/quality-20261005-final.log` | `-q -n 4 --basetemp=.tmp-pytest-quality-20261005-final --durations=15 --junitxml=outputs/quality-20261005-final.xml` | 852 passed, 2 skipped, 287.48 s на exact clean `75ce00315e030a982d33109c17c0b1696fbb6cf0`; до усиления control ниже |
| `outputs/quality-20261005-examples.log` | `examples -q --testence-headless --basetemp=.tmp-pytest-quality-20261005-examples` | 5 passed, 1 skipped, 14.71 s; production source тот же 75ce003, только native test corpus в это время усилен |
| `outputs/quality-provenance-strength.log` | `tests/test_route_mocking.py -q --basetemp=.tmp-pytest-quality-provenance-strength --durations=5` | 5 passed, 51.86 s; nested healthy corpus 14 passed; deliberately disabled tracker: оба selected scope failed с DID NOT RAISE, как ожидает outer control |
| `outputs/quality-20261005-final2.log` | `-q -n 4 --basetemp=.tmp-pytest-quality-20261005-final2 --durations=15 --junitxml=outputs/quality-20261005-final2.xml` | 1 failed, 852 passed, 2 skipped, 267.12 s на clean `ebc3d7192df091cd3d48ddb8bd6ffc36a735f85b`, Python 3.12.4; native CPython/execnet crash, см. ниже |

Development static после edits: 224 files formatted, Ruff clean, mypy 82 files,
`git diff --check` clean. Исправлены mypy Windows-only symbols / TemporaryFile typing /
bridge name reuse и три Ruff E731 в model tests. Первый native integration run
пересекался с lifecycle edits и не относится целиком к финальному candidate.
Финальные fresh runs должны выполняться без source edits.

## Диагностика сбоя runtime

`quality-20261005-final2` упал в
`tests/test_pytest_lifecycle.py::test_xdist_workers_preserve_one_terminal_event_per_case`,
assert `result.returncode == 0`, nested subprocess exit **2147483649**.
В stderr: native access violation / `0x80000001`; стек worker проходит через
`platform._wmi_query`, `_get_machine_win32`, `xdist.remote.getinfodict`.
Затем execnet сообщил `cannot send (already closed?)`. Дамп native crash не получен.
Стек соответствует известному [CPython WMI crash 125315](https://github.com/python/cpython/issues/125315),
для которого есть [3.12 backport](https://github.com/python/cpython/pull/126203).
Это поддержанная источником гипотеза причины, не доказанная локализация по dump.

Synthetic run **r-20261005-105609-ead6bd**:
`.tmp-pytest-quality-20261005-final2/popen-gw2/test_xdist_workers_preserve_on0/parallel-runs/r-20261005-105609-ead6bd/`.
Inspect видит 8 passed / 8 unverified, но **run_status=incomplete**, manifest running,
отсутствует controller run.end, manifest/shard/digest integrity errors. Восемь точек
в stdout не превращают этот subprocess в успешный proving run.

Существующий `.venv` и системный Python не заменены. Уже установленный managed
Python **3.12.14** использован для отдельного ignored
`outputs/quality-venv31214`, созданного точной командой:

```powershell
$env:UV_PROJECT_ENVIRONMENT='C:\Users\alekkiselev\PycharmProjects\testence\outputs\quality-venv31214'
uv sync --locked --python 'C:\Users\alekkiselev\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe' --extra dev --extra parallel --extra visual
```

Лог: `outputs/quality-env31214-sync.log`. Lockfile и production source не изменены.
Дополнительные команды используют этот interpreter, не default `uv run`:

```powershell
& 'outputs/quality-venv31214/Scripts/python.exe' -m pytest tests/test_pytest_lifecycle.py -q --basetemp=.tmp-pytest-quality-runtime31214-lifecycle --durations=5
& 'outputs/quality-venv31214/Scripts/python.exe' outputs/quality-mcp-browser-probe.py
```

Lifecycle/xdist: **9 passed, 15.92 s**, `outputs/quality-runtime31214-lifecycle.log`.
Настоящий headless Edge в MCP process job: normal **3.234 s**, exit 0, run
`r-20261005-110406-db3306`; deadline **20.266 s** при timeout 20, incomplete run
`r-20261005-110409-ccc938`. В обоих случаях CDP listener остановлен; до остановки
тест соединялся с ним по loopback и проверял реальный h1 через DSL. Логи/receipts:
`outputs/quality-mcp-browser-probe.log`, `outputs/quality-mcp-browser-receipt.json`,
raw run artifacts в `outputs/quality-mcp-browser-project/runs/`.
Для воспроизведения portable suite source сохранён в компактном final receipt;
raw probe script остаётся ignored. Это UI/process proof, не backend persistence proof.

## Handoff

Последний полный proving run: **quality-20261005-runtime-final**, source
`ebc3d7192df091cd3d48ddb8bd6ffc36a735f85b`, isolated Python **3.12.14**,
**853 passed, 2 skipped, 297.95 s**, exit 0. Исходный код и тесты не менялись
между началом и завершением. Пропуски — symlink privilege WinError 1314 в
`test_export` / `test_metrics`, не выполненное доказательство этих двух сценариев.

Exact command (env: `TESTENCE_BROWSER_CHANNEL=msedge`, `TESTENCE_DEBUG_PORT=0`):

```powershell
& 'outputs/quality-venv31214/Scripts/python.exe' -m pytest -q -n 4 --basetemp=.tmp-pytest-quality-20261005-runtime-final --durations=15 --junitxml=outputs/quality-20261005-runtime-final.xml
```

Артефакты: `outputs/quality-20261005-runtime-final.log`, соответствующий `.xml`.
Examples в том же окружении: **5 passed, 1 skipped, 13.03 s**, exit 0;
skip — намеренно исключённый `demo_failure`, не незаметно пропущенная регрессия.
Команда: `& 'outputs/quality-venv31214/Scripts/python.exe' -m pytest examples -q --testence-headless --basetemp=.tmp-pytest-quality-runtime-examples`.
Лог `outputs/quality-runtime-examples.log`.
Fresh static в этом же окружении: 224 files formatted, Ruff clean, mypy 82 files.
Команды: `python -m ruff format --check src tests bench scripts examples`,
`python -m ruff check src tests bench scripts examples`, `python -m mypy src scripts`,
где python — isolated interpreter выше. Лог `outputs/quality-runtime-static.log`.

Scale gate: `uv run python bench/scale_profile.py --repeats 3 --check --output outputs/quality-20261005-scale.json`,
**passed=true**, violations отсутствуют, Windows Python 3.12.4 / source `75ce003`.
Production source `75ce003` и `ebc3d71` совпадает; последний commit усиливает tests/docs.
Warm 10k p50 **1860.66 ms**, p95 **2463.99 ms**, peak около 48 MB.
Это результат narrow synthetic gate, не обещание ускорения внешних приложений.

Последняя unexpected failing step — **quality-20261005-final2**, nested xdist
native crash на Python 3.12.4, описанный выше. Финальный runtime run не имеет
failing step. Старый сбой не удалён и не представлен как успешный retry.
Компактный [receipt](2026-10-05-testing-quality-receipt.json) связывает source blobs,
lockfile, runtime, команды, hashes ignored artifacts и portable browser probe.

Следующая отдельная приёмка — POSIX ownership/support floors и расширение native
interception corpus (HAR/service worker). Первый следующий proving command на
новом Linux/macOS host после locked sync:
`uv run pytest tests/test_owned_process.py tests/test_mcp.py tests/test_native_routes.py tests/test_route_mocking.py -q --basetemp=.tmp-pytest-quality-posix-next`.
Новый run должен иметь свой receipt с platform/runtime/revision, а не наследовать
Windows assurance. Неуверенность: POSIX/support floors, неизвестные interception
surfaces, interruption, external backend/client acceptance.
Navigation timeout прошлого аудита не объявлен устранённым; retries и повышения
его timeout здесь нет. Raw artifacts остаются в ignored outputs/runs/basetemp.
