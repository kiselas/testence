# Failure-pack execution history

PROD-01 engineering candidate, 2026-10-13. Base revision:
`0fcc46c398a778807791acfcdefa95c8a0ce28be`. Failure packs previously contained
page/network/oracle snapshots but omitted the already recorded execution chain.
They now include manifested `events.json` for the same test and proof identity,
with any bound proof digests checked. The owning writer checkpoints its flushed
shard; later appends and other workers are excluded.

The additive `testence/pack-events/1` artifact retains allowlisted step, assertion,
oracle and evidence-strength records within 64 events, 4,000 estimated tokens and
a 1 MiB source read. It preserves valid JSON and explicitly reports omitted bytes,
records and invalid records. Runtime secrets and configured redaction are reapplied;
source traces, parameters and unrelated payload fields are excluded. Source byte
references and artifact hashes are diagnostic provenance, not additional assurance.
No pre-state, native dispatch or exact handler mechanism is inferred.

Changed implementation: `triage/history.py`, `triage/pack.py`, writer checkpoint,
event budget, schema inventory and packaged schema; regression controls in
`tests/test_pack.py`; English/Russian format documentation and changelogs.
The seven frozen corpus/test files remain unchanged.

## Verification

[Validation receipt](2026-10-13-pack-events-validation.json) records final commands,
environment, timings and all eleven implementation/documentation file hashes.
Windows, patched Python 3.12.14, Playwright 1.62.0, Edge channel, ephemeral CDP ports.

- Ruff format/check and mypy passed.
- Targeted pack/contracts/redaction: 77 passed.
- Fresh `pytest -n 4`: 912 passed, 2 skipped, 328.84 s pytest / 330.344 s owned command.
- Headless examples: 5 passed, 1 skipped.
- [Fresh OSS receipt](2026-10-13-pack-events-oss.json): one repeat, all 16 expected
  outcomes; 14 verified, 2 violated; no integrity errors. Healthy/defect/restored/restyle
  process wall times: 11.606 / 16.066 / 8.400 / 8.295 s. One repeat is not a latency claim.
- Checkbox failure pack: 7 events, 6,709 bytes, successful action seq 14–15 before
  failed bound assertion seq 17. Password: 9 events, 8,592 bytes, action seq 68–69
  before assertion seq 71. Every projection matches original ledger bytes and all
  manifest artifacts match their hashes.

Initial reproduction failed at missing `events.json`. Additional NaN/Infinity
controls failed strict JSON reading before switching to the existing strict reader;
they now produce partial history and preserve other records. Initial damage controls
closed the writer too early and failed at pack-event emission; corrected controls
simulate failed reads while keeping the writer open. These initial failures and the
first 910-pass full run are retained locally, not presented as final verification.
General non-finite-value policy in the original ledger remains a separate question.

## Handoff

Last run: `outputs/product-pack-20261013-09/oss`, defect run ID `oss-defect-1`.
Exact expected failed steps: `Selection is visibly checked` and `Password is revealed`.
Full ledger/packs are under that ignored output tree. Compact projection checks are
in the validation receipt; full local research receipts are in the adjacent wiki.
The OSS harness reuses run IDs across separate output roots: provenance here is the
specific path plus source/pack hashes, not proof-ID uniqueness across old runs.

Remaining uncertainty: omitted early history in large runs; generic-step operation
provenance; claim-dependent initial-state needs; model classification benefit;
cross-platform CI and independent acceptance. This is an engineering candidate.

Next proving command, with a new output directory:

```powershell
$env:TESTENCE_BROWSER_CHANNEL='msedge'
$env:TESTENCE_DEBUG_PORT='0'
outputs/quality-venv31214/Scripts/python.exe -B bench/oss/run.py --repeats 1 --output outputs/pack-events-next
```

Rollback is removal of this additive artifact/assembly hook; old packs remain readable.
