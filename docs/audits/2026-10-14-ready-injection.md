# Ready PID test injection correction

The empty ready-PID control in the previous full gate979/2/1 did not inject its
fault when publication followed a false Path.exists check. A deterministic probe
exposed this path; actual native scheduling was not traced. Tests now read ready
first, then substitute empty/malformed data or one transient exception only after
success. An injected flag is required. Assignment spies always delegate actual
Windows Job ownership before their assertions, including unexpected negative
control paths. Framework runtime/deadlines/refusal claims remain unchanged.

Plan PROD-09, base ccd9d7cc666537dc62dd0c43d7468af731a3b6fc, draft PR39
https://github.com/kiselas/testence/pull/39. Changed test_process_ready.py and this
audit. Test SHA256 0df82ff38f7c18b078b7f822906f6a99229514b5197c085a001640ec1aa6584d.
All7 frozen files/runtime src unchanged. Five controlled no-process probes and
13 real targeted process tests pass; mutation bypass is rejected, no exists check
controls injection and original read-error identity is preserved.

Required checks with existing CPython3.12.14/PW1.62/pytest9.1.1, Windows/Edge,
TESTENCE_DEBUG_PORT=0, PYTHONFAULTHANDLER=1, PYTHONIOENCODING=utf-8:

* `outputs/quality-venv31214/Scripts/python.exe -B -m pytest -q -n 4 --basetemp=outputs/ready-injection-20261014-19/tmp-full`: 980 passed, 2 skipped in 298.96s (0:04:58)
* Same Python Ruff format/check `src tests bench scripts examples`, mypy `src scripts`: pass.
* Same Python `-B -m pytest examples -q --testence-headless --basetemp=outputs/ready-injection-20261014-19/tmp-examples`:5 passed/1 skipped.
* Targeted `-B -m pytest -q tests/test_process_ready.py tests/test_owned_process.py tests/test_owned_pytest.py --basetemp=outputs/ready-injection-20261014-19/tmp-targeted`:13 passed.

Last real proving run tmp-targeted/full under outputs/ready-injection-20261014-19;
compact source/commands/timing and failure receipts in sibling wiki run of same
name. Prior live runtime/visual gates bound by unchanged source hashes, no new
benchmark claim. Prior failed step empty PID DID NOT RAISE ValueError retained.
Prior hosted CI38522680933 fails independent Linux floor save/API cidr assertion;
all visual jobs pass. Save/render/native/WMI/navigation causes remain uncertain.
Next proving command `gh pr view 39 --json headRefOid,baseRefOid,statusCheckRollup`
for exact new candidate; preserve any failure, do not rerun for green. No merge/release.
