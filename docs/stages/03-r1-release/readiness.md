# Stage 3 execution readiness

Checked: 8 September 2026. Sensitive values are intentionally absent.

| Dependency | Status | Evidence and next action |
|---|---|---|
| Local Windows implementation environment | verified for engineering | Windows 11, Python 3.13.11, Playwright 1.62.0 and Chromium 151.0.7922.34 are recorded in current receipts |
| Python 3.10 minimum environment | workflow_ready | Minimum declared dependencies are isolated in CI; obtain the hosted candidate receipt |
| Linux/Python hosted matrix | workflow_ready, not run | CI covers Linux/Windows × Python 3.10/3.12; run it after creating the clean candidate |
| Reference host (4 vCPU/8 GiB/SSD) | deferred by owner, 8 September | Run locally for this iteration; keep actual host characteristics and local profile. This is not evidence from the originally specified reference host |
| Git remote and hosted CI | access verified; push/branch authorized | `gh repo view`: PRIVATE, ADMIN. Owner authorizes release branch/push, repository must stay private |
| TestOps test tenant | prepared, registry access unavailable | Docker Linux engine 29.7.2 and Compose v5.5.0 work. Official pinned demo template plus loopback overlay validates; image manifest request returns unauthorized. Trial/registry credentials required: [sandbox guide](../../../infra/testops-sandbox/README.md) |
| Codex and Claude client access | Codex session available; Claude user-run planned | [Exact workflow and Claude instructions](agent-client-check.md); client presence alone is not a consumer receipt |
| Two OSS target revisions | unavailable | Select two licensed, distinct public web apps and freeze full commit SHAs before the corpus run |
| Truth/holdout/security/rights reviewers | unavailable | Give each reviewer a digest-bound acceptance bundle; their identities and decisions must be real |
| Five users / three pilot teams | unavailable | Use the pilot protocol and retain setup/QA/return-week measurements |
| Private vulnerability channel | not verified | Enable and test GitHub private vulnerability reporting with a maintainer receipt |
| Protected `pypi` environment / trusted publisher | workflow prepared, setting absent | Configure exact repository/workflow/environment identity and require owner approval |
| Owner decision for exact candidate | unavailable | Sign only the final manifest payload after every required gate is passed |

The autonomous engineering path is complete up to facts that can only be produced by a
clean hosted candidate, external systems or independent people. Those conditions remain
explicit no-go gates; elapsed time, mock identities and local metadata do not satisfy them.
