# Release evidence

`rc-manifest.json` and `rc-manifest-v2.json` retain historical, **no-go**
development snapshots. Their `outputs/` paths point into retained local evidence
bundles, which are intentionally excluded from source control. They are not the
manifest for the current branch HEAD.

On a fresh checkout their structure can be inspected with
`testence release validate release/rc-manifest-v2.json --structure-only --json`
(expected exit 3: no-go). Full verification requires the original bundle and
must never substitute `--structure-only` for artifact verification.

Current candidates are built by CI from a clean SHA. Download the immutable
candidate-distributions artifact and all required acceptance evidence before
assembling a new candidate-bound manifest. A green private CI run may lack signed
GitHub attestations: private repositories require Enterprise Cloud for that feature.
Set `PRIVATE_ATTESTATIONS_ENABLED=true` only when that entitlement is available.
Unsigned provenance is labelled as such and does not count as signed release evidence.
