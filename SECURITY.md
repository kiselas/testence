# Security policy

## Supported versions

Testence is currently an alpha candidate. Security fixes are applied to the latest `main` only.
There is no supported stable release line. After the first `0.1.x` release, its latest
patch receives critical security fixes until 90 days after the next minor release.

## Reporting a vulnerability

Do not open a public issue for a vulnerability or attach a sensitive evidence pack.
Use GitHub's private **[Report a vulnerability](https://github.com/kiselas/testence/security/advisories/new)**
form. Private vulnerability reporting was enabled and verified through the GitHub API
on 21 September 2026. Repository collaborators may also open a private draft security
advisory and notify `@kiselas`, the current security owner. Include only the minimum
synthetic reproduction needed to establish the issue.

Please report credential disclosure, unsafe evidence capture, cross-run data leakage,
browser-profile exposure, arbitrary code execution and dependency-chain concerns as
security issues. You can expect an acknowledgement within seven days and a remediation
decision after the impact is reproduced. Critical confirmed issues target an initial
containment decision within 72 hours; these are response targets, not a service-level
guarantee.

## Evidence safety

The current development tree sanitizes common structured credentials and configured
Testence credentials before writing text evidence, bounds captured text, validates
session-cache identity and keeps API authentication on explicit origins. These controls
do not yet cover arbitrary personal/proprietary text or visual secrets in screenshots.
Until the full T12 review and cross-platform safety matrix are complete, do not run
Testence against sensitive production data. Review every artifact before sharing it.
