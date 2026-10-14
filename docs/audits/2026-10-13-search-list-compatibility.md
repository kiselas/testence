# Search/list candidate compatibility

PROD-05-COMPAT follows the input-role candidate in PR39. Original CI run38427037605
failed wrong-list-element in all three dependency floor jobs. Playwright1.49 gives
search with any list attribute an implicit combobox role even without a datalist.
The fingerprint's searchbox address then resolves zero elements. Tested GitHub
merge22eddf60a6a51a509321982cf633887c68c54f33 has the same tree as head5c6b4e7.

Candidate scanning now uses testid or escaped CSS ID for implicit search with
unresolved list, omitting candidates without either. Semantic fingerprints,
explicit roles, valid datalists and ordinary search retain their behavior. No
runtime rebind, baseline rewrite or dependency increase. The original same-control
assertion remains. Reference:
[Playwright1.49 roleUtils](https://raw.githubusercontent.com/microsoft/playwright/v1.49.0/packages/playwright-core/src/server/injected/roleUtils.ts).

37 browser controls plus fingerprint/heal/single-evaluation checks give67 passed.
Ruff format/check and mypy pass; examples5 passed/1 skipped. Fresh OSS gives14
verified/2 violated with no integrity errors. Seven frozen files unchanged. Exact
commands, timings, source hashes and outcomes:
[receipt](2026-10-13-search-list-compatibility.json).
Local Playwright1.62 does not substitute for actual1.49 hosted qualification.

Full local check remains failed:962 passed/2 skipped/2 failures. Nested xdist in
test_plugin_opt_in returned4294967295; faulthandler records0x8007000e followed by
access violation, with CPython3.12.14 platform._wmi_query reached from host._query.
The stack identifies executing code, not the complete native causal mechanism.
test_save_and_verify's oracle saw UI cidr=null versus API id=None/default cidr
10.0.0.0/24; the missing UI result's cause is unestablished. No unchanged full
rerun replaces these failures. Earlier native failures remain preserved.

Original ordinary Windows/Python3.10 hosted job separately failed login navigation
with ERR_NO_BUFFER_SPACE in native route-mocking setup; three installed-wheel jobs
were skipped downstream. Neither failure is repaired by this address change.

Changed engine, tests and en/ru changelogs are bound in the receipt. Raw synthetic
outputs: outputs/product-verification-20261013-13. Last live run oss-defect-1 has
expected Selection is visibly checked/a.checkbox.on and Password is revealed/
a.password.show failures. Internal methodology stays in the adjacent wiki.

Next gate is exact-head PR39 CI after publishing this candidate:

```powershell
gh pr view 39 --json headRefOid,baseRefOid,statusCheckRollup
```

Inspect floor and Windows3.10 results without replaying unchanged jobs for green.
Investigate host.py WMI thread and the oracle request/render boundary separately.
No global platform monkeypatch, retries, oracle weakening, merge or release.
