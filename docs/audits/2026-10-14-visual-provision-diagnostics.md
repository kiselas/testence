# Visual baseline authoring diagnostics candidate

The macOS installed-client CI run38453828470 failed its first baseline screenshot
with a5000ms timeout before replay. Its log could not identify overview/dialog or
the capture ordinal. This candidate adds bounded stdout call observations to the
separate authoring harness; accepted replay and framework runtime are unchanged.

Plan/claim PROD-08-DIAG; base 3802546ee19d1db5a670b6329b89865539ad8756; draft
https://github.com/kiselas/testence/pull/39. Changed provision.py/new regression test
and this audit. Source hashes: provision e9406a48553c1fde9089f9128aff840ad7ffb62874344e0c556345572e74c0cd,
test 1b0de6caf48cd2c8a7aec33a0eb648eb1d7f0bfb956d727cf160912f866b66c3.
All7 frozen files and stock run.py unchanged. Two pre-edit injected failures
demonstrate missing state/ordinal logging; six controls preserve exception identity,
capture counts/cleanup, stability, and handling of malformed/failed observation
or closed output sink. No screenshot retry or altered timeout/options.

Validation on CPython3.12.14/PW1.62.0/pytest9.1.1, Windows/Edge, debug port0,
PYTHONFAULTHANDLER=1/PYTHONIOENCODING=utf-8:

* `outputs/quality-venv31214/Scripts/python.exe -B -m pytest -q -n 4 --basetemp=outputs/visual-diagnostic-20261014-18/tmp-full`: 1 failed, 979 passed, 2 skipped in 320.27s (0:05:20)
* Same Python Ruff format/check `src tests bench scripts examples`, mypy `src scripts`: pass.
* Same Python `-B -m pytest examples -q --testence-headless --basetemp=outputs/visual-diagnostic-20261014-18/tmp-examples`:5 passed/1 skipped.
* Local owned loopback authoring/visual gate:2 fresh child runs/8 original authoring
  capture calls;24 expected unmodified mutation controls, frozen baseline digests.

Last live local IDs desktop/mobile; raw artifacts/logs at
`outputs/visual-diagnostic-20261014-18/live`; compact commands/timings/results in
sibling wiki `runs/visual-diagnostic-20261014-18`. No current live gate failed step.
Current full failed step: test_process_ready::test_invalid_ready_pid_never_assigns_or_releases[empty],
DID NOT RAISE ValueError; marker once. Existing test checks exists before read,
allowing invalid injection to be bypassed; deterministic synthetic probe establishes
that path, not the actual native schedule. Ready test/runtime remain unchanged.
Prior actual macOS failed step capture_baseline/_stable_capture/Page.screenshot
remains unresolved. New diagnostic failure is a fresh timestamped record with the
same propagated error; unavailable snapshot is never backend or pixel proof.
Resource timing entries do not enumerate all pending requests. This adds one
read-only snapshot per state outside the capture deadline and may affect scheduling.
Windows success does not establish macOS cause or installed-wheel acceptance.

Next proving command: `gh pr view 39 --json headRefOid,baseRefOid,statusCheckRollup`; inspect new
exact-head CI's setup4.log only if needed. Candidate remains draft; no merge/release.
