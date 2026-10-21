# Click/fill engine-call evidence

PROD-02 engineering candidate, base `e46bbbdcb3284f61dcd858ebec6d39479d45d2c8`.
Generic intent wrappers could not be distinguished from primitive click/fill by
their execution records. Built-in click/fill now stamp the DSL producer, runtime
engine type and requested method in step.start/end, with dispatch states
`not_called`, `raised`, `returned`. The start records intent; a matching end is
required for a completion conclusion. The descriptor contains no input arguments.

Capability and method lookup failures stay not_called; an invoked method exception
is raised. Default fill preserves the legacy signature; fast operations retain
their existing weakening. Native escape hatches and generic wrappers stay distinct.
This is producer metadata under a trusted source/version contract, not native-event
attestation, initial-state observation, product success or backend proof. Missing
annotations/ends cannot prove an action never ran. Assurance is unchanged.

Changed files: DSL recorder, pack judge instructions, optional step operation shape
in the event schema, regression controls, English/Russian format/changelog docs;
this handoff and compact validation/OSS receipts. Frozen corpus/test files unchanged.

## Proof and handoff

Exact commands, hashes, environment, timings and source-bound pack checks:
[validation](2026-10-13-step-operation-validation.json),
[OSS receipt](2026-10-13-step-operation-oss.json).
Windows/Python 3.12.14/Playwright 1.62.0/Edge with ephemeral CDP ports.
Full fresh pytest: 927 passed, 2 skipped. Targeted/live DSL: 89 passed; final
boundary controls: 66 passed. Examples: 5 passed, 1 skipped. Ruff/mypy passed.
One OSS repeat requires 14 verified / 2 violated and no integrity errors, plus
typed returned click before the failed bound assertion in both defect packs.

Before the fix, regression failed at missing operation. Initial fake-engine controls
used invalid capability spelling `dom`; the harness was corrected to Capability.DOM.
Both failure receipts remain in the adjacent wiki. An interruption control proves
the engine can be invoked after start while leaving no end: do not infer absence from
the initial not_called field. The schema rejects a fabricated native_dispatched state.

Last run: `outputs/product-operation-20261013-10/oss`, expected failed steps
Selection is visibly checked (`a.checkbox.on`) and Password is revealed
(`a.password.show`). Ledger and full packs remain under that ignored output tree.
The validation receipt binds their projections and source/manifest hashes.

Remaining uncertainty: third-party/monkeypatched executor contracts, other
primitives, initial state when required by a claim, model benefit and independent
acceptance. Rollback removes optional operation metadata; existing replay dispatch,
claims, locators and retry policy are preserved. This is a candidate pending CI/review.

Next proving command (new output path, same Edge/ephemeral-port settings):

```powershell
outputs/quality-venv31214/Scripts/python.exe -B bench/oss/run.py --repeats 1 --output outputs/operation-next
```
