# Input role fingerprints and candidate identity

PROD-05 candidate, base `38265796597e22b3933b4112efdbaeb94a31f78c`.
A checkbox addressed by its proper role produced a fingerprint with `role=textbox`.
The candidate scan reused that fingerprint to offer `Target(role=textbox, name=Agree)`,
which did not locate the original input. A fresh browser regression reproduced this.

The shared one-evaluation fingerprint function now derives supported implicit roles
from normalized input type, respects resolved datalists and keeps explicit role
precedence. Unsupported implicit-role inputs use existing address fallback. No new
round-trip, locator healing, assertion change or stored-fingerprint migration is added.
This is a scoped input heuristic, not complete accessibility-role/name computation.
Mapping reference: [W3C ARIA in HTML Recommendation](https://www.w3.org/TR/2026/REC-html-aria-20260811/).

## Evidence

32 fresh synthetic checks cover role/candidate identity: checkbox/radio, textual and
typed controls, normalized types, datalists and malformed references, valid explicit
roles, unsupported inputs with IDs, and hidden-candidate exclusion. Together with
existing fingerprint/heal/single-evaluation controls: 62 passed. Format, lint and
mypy passed; headless examples 5 passed/1 skipped. The seven frozen files are unchanged.

[Validation receipt](2026-10-13-input-fingerprint-roles-validation.json) separates
scoped evidence from all full-gate attempts. [OSS receipt](2026-10-13-input-fingerprint-roles-oss.json)
records one repeat: 14 verified/2 violated, all four phases contain correct checkbox
and radio fingerprints, and defect pack manifest hashes match. Existing authored heal
corpus is run without editing its items or overwriting its earlier results; its actual
outcome is retained in the validation receipt. No new model trial or independent
acceptance is claimed. Existing stored fingerprints should get a new accepted green
baseline before judging proposals after the role change.

## Local full-gate limitation

The local required full suite has **not passed**. First run: 958 passed, 2 skipped,
one empty-plan nested pytest returned 4294967295 instead of 4; its ledger stopped
after collection.start. Isolated empty-plan passed. A 42-test ownership diagnostic
passed, with no cross-test pytest membership in 21 observed job closures; that does
not explain the original termination.

An initial diagnostic full run accidentally inherited a local plugin into consumer
environments and produced 25 failures/11 setup errors. The instrumentation was corrected
to CLI-only activation; the next full run had 957 passed, 2 skipped, one CLI native
access violation (3221225477) and one 2-second local navigation timeout. Both passed
in isolated diagnosis with faulthandler enabled. These are retained unresolved failures,
not a demonstrated host or process fix and not evidence that changing fingerprint
roles caused them. No repeated unchanged full run is substituted for those results.

The draft requires clean hosted CI and review; none of these receipts approves release.
Diagnostic plugins and methodology remain in the adjacent local wiki.

## Handoff

Changed implementation: `src/testence/engine/playwright_cdp.py`; regression controls
`tests/test_fingerprint_roles.py`; English/Russian changelogs; this audit and its JSON
receipts. Raw synthetic artifacts remain under ignored `outputs/product-fingerprint-20261013-12/`.
Last live run: `oss/runs/oss-defect-1`; expected failed steps Selection is visibly
checked/a.checkbox.on and Password is revealed/a.password.show. Role/candidate
checks do not prove pre-state or backend effects. Exact commands, source hashes,
environment, timings and failure paths are in the validation receipt.

Next proving command, with a new basetemp and optional faulthandler:

```powershell
$env:TESTENCE_BROWSER_CHANNEL='msedge'
$env:TESTENCE_DEBUG_PORT='0'
$env:PYTHONFAULTHANDLER='1'
outputs/quality-venv31214/Scripts/python.exe -B -m pytest -n 4 -q --basetemp=.tmp-pytest-input-roles-next
```

Run it when new causal or integration evidence justifies another full gate. Rollback
restores the previous shared mapping; no old evidence/store is rewritten automatically.
