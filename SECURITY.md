# Security policy

## Supported versions

Testence is currently pre-alpha. Security fixes are applied to the latest `main` only;
there is no supported stable release line yet.

## Reporting a vulnerability

Do not open a public issue for a vulnerability or attach a sensitive evidence pack.
Use GitHub's private vulnerability reporting for this repository when it is available.
If that channel is unavailable, contact the repository owner privately through their
GitHub profile and include only the minimum synthetic reproduction needed to establish
the issue.

Please report credential disclosure, unsafe evidence capture, cross-run data leakage,
browser-profile exposure, arbitrary code execution and dependency-chain concerns as
security issues. You can expect an acknowledgement within seven days and a remediation
decision after the impact is reproduced.

## Evidence safety

Until the redaction and session-cache release gates are complete, do not run Testence
against sensitive production data. Before sharing an artifact, remove credentials,
tokens, cookies, private URLs, personal data and proprietary page content.
