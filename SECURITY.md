# Security policy

## Supported versions

Testence is currently pre-alpha. Security fixes are applied to the latest `main` only.
There is no supported stable release line. After the first `0.1.x` release, its latest
patch receives critical security fixes until 90 days after the next minor release.

## Reporting a vulnerability

Do not open a public issue for a vulnerability or attach a sensitive evidence pack.
The repository is private during release preparation, so outside reports are not yet
accepted. Before the repository becomes public, the release owner must enable GitHub
private vulnerability reporting and replace this paragraph with the visible **Report a
vulnerability** link. The 2026-09-06 readiness check returned HTTP 404 for that endpoint;
this is an explicit release blocker rather than a claimed reporting channel.

Repository collaborators should open a private draft security advisory and notify
`@kiselas`, the current security owner. Include only the minimum synthetic reproduction
needed to establish the issue.

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
