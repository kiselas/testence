# Security policy

## Supported versions

Testence is in alpha. Security fixes are applied to the latest `main` only.
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

Evidence is redacted before it is written. Field names are matched by their parts, so
`authToken`, `X-Api-Key` or `dbPassword` are treated as credentials; secret-shaped values
(JWTs, common provider token prefixes, payment card numbers), sensitive URL parameters
and the configured login values are removed wherever they appear. The policy is recorded
in the run and applied again by `testence export` and `testence report`. Network bodies
and screenshots are captured only when a project enables them.

Projects extend the rules in `evidence.redact` and mask elements in screenshots with
`evidence.mask` ([configuration](docs/en/configuration.md#redaction-and-screenshot-masks));
`testence export --attachments minimal|none` limits what leaves the machine. Arbitrary
personal or proprietary text is protected as far as the configured policy reaches, and
pixels where a mask is configured. Review an evidence pack before sharing it outside your
team, and report any credential you find in evidence as a security issue.
