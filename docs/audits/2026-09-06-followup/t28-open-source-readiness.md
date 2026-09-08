# T28 open-source readiness

Status: **local scans and policies complete; public security channel and final review incomplete**.

The tree is licensed Apache-2.0. Current source, documentation, schemas, SVG assets,
synthetic corpora and benchmark applications are recorded as project-authored; no
vendored third-party source or dataset was identified, so no current NOTICE entry is
required. The installed runtime inventory contains 11 packages with Apache-2.0, MIT,
BSD, PSF-2.0 or compatible compound license expressions. The pipeline generates SPDX
2.3 SBOM and provenance artifacts for every candidate.

Gitleaks 8.30.1 scanned all five Git commits with redaction (about 2.10 MB) and reported
no leaks. `pip-audit` checked the exported locked runtime graph and reported no known
vulnerabilities. Machine outputs are `gitleaks-history.json`, `pip-audit.json`,
`runtime-requirements.txt` and `release-artifacts/dependency-inventory.json` under
`outputs/audit-2026-09-06-followup`.

`SUPPORT.md`, `SECURITY.md` and `CONTRIBUTING.md` now state the supported matrix, owner,
response targets, compatibility/deprecation/rollback rules and contribution rights.
The remote repository is currently private. The authenticated API request for private
vulnerability reporting returned HTTP 404, so `SECURITY.md` records this as a release
blocker. Before publication, the owner must enable the real channel, review the final
tree/rights inventory and repeat both scans on the clean RC SHA.
