# Support and compatibility

Testence is an alpha candidate. The supported development and CI matrix is Windows and Linux,
Python 3.10 and 3.12, and the Playwright-bundled Chromium browser. macOS, Firefox,
WebKit, mobile, hosted dashboards and production-data handling are outside the current
support promise.

The latest `main` is the only supported development line before the first release.
After `0.1.x`, the latest patch of the current minor receives bug and critical security
fixes until 90 days after the next minor release. `0.x` releases may change Python APIs,
but a breaking change requires a changelog entry and migration instructions. Public
JSON schemas keep explicit versions; readers either preserve a documented legacy
adapter or reject an unsupported version with a typed error.

Use GitHub Issues for reproducible bugs and feature proposals. The maintainer and
support owner is `@kiselas`; CODEOWNERS requires that account for repository review.
Security reports follow [SECURITY.md](SECURITY.md) and must never be posted as public
issues. Response targets are seven days for acknowledgement and 30 days for a triage
decision. Best-effort community support has no guaranteed response time.

Every release candidate must include a rollback instruction. Until a stable package is
published, rollback means installing the previously recorded wheel digest and reverting
repo-owned schema/quality/agent locks to their recorded revisions.
