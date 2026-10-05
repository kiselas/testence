# AUD-Q26: handoff и доказательства

Дата: 2026-10-05. Plan/claim IDs и исследования:
[Q26-01–Q26-03](2026-10-05-testing-quality-research.md).

## Статус кандидата

Выполнен `git fetch origin`; live remote main:
`15ad5d23385dc64c447c7077cb280972185838a4`. Новых коммитов в origin/main нет
(проверены также live remote heads). База slice: `d527312`.
Два локальных коммита прошлого аудита и незавершённые правки сохранены.
Работа остаётся на main; push/release не выполнялись.
Implementation revision и окончательные проверки будут привязаны после fresh runs.

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

Development static после edits: 224 files formatted, Ruff clean, mypy 82 files,
`git diff --check` clean. Исправлены mypy Windows-only symbols / TemporaryFile typing /
bridge name reuse и три Ruff E731 в model tests. Первый native integration run
пересекался с lifecycle edits и не относится целиком к финальному candidate.
Финальные fresh runs должны выполняться без source edits.

## Handoff

Последний implementation proving run: quality-native-live3, failure отсутствует.
Последний lifecycle run: quality-native-lifecycle, failure отсутствует.
Последняя failing step: quality-native-live2, `fresh.json()` TypeError в новом test
harness; property исправлена, native corpus прошёл. Production и harness failures
разделены. Полный набор и обязательные gates ещё предстоят.

Следующая proving command:
`uv run pytest -q -n 4 --basetemp=.tmp-pytest-quality-20261005-final --durations=15 --junitxml=outputs/quality-20261005-final.xml`.
Также обязательны examples и narrow scale gate. Неуверенность: POSIX/support floors,
неизвестные interception surfaces, interruption, external backend/client acceptance.
Navigation timeout прошлого аудита не объявлен устранённым; retries и повышения
его timeout здесь нет. Raw artifacts остаются в ignored outputs/runs/basetemp.
