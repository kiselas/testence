# M1 security implementation receipt: auth and read containment

Date: 6 September 2026. Baseline: `7be8d025f81d9116ab267c59d440e14b377cfce7`.
State: implemented and verified in the local working tree; no commit, publication,
remote configuration or real credential was used.

## Delivered slice

- `ApiClient` resolves relative and absolute targets against one normalized HTTP(S)
  origin. Another host or effective port, URL userinfo, scheme-relative targets and
  HTTPS-to-HTTP downgrade fail before the network call.
- The stdlib HTTP transport follows only same-origin redirects. A live two-server
  regression proves that Authorization and Cookie canaries never reach the redirect
  destination on another origin.
- Browser cookies passed to the API keep host/domain, path, secure and expiry scope.
- Session reuse remains opt-in through `session_probe_path`. Versioned cache records
  expire, bind project/origin/account/profile/role/strategy, hash the account value,
  validate identity and role before every reuse, and use atomic replacement plus mode
  `0600` where supported. Logout, expiry, old/corrupt records and identity changes are
  misses; a freshly authenticated wrong account or role fails explicitly.
- Exporter evidence files and run ledger shards are resolved before reading. Parent
  traversal, absolute filenames and links outside the selected run are ignored.
- One sanitizer now runs before ledger, pack and fingerprint-store persistence. It
  removes configured credentials, structured auth/cookie/password/token/key values,
  Bearer/Basic credentials and secret query parameters. Ledger strings and extended
  pack sections are bounded. Every pack has a relative size/SHA-256 manifest.
- A synthetic canary test scans ledger, pack, HTML report, Allure, CTRF and fingerprint
  outputs and proves the canary is absent from every text artifact.

## Regression evidence

The focused suite covers direct foreign origins, default-port normalization, downgrade,
cookie scoping, cross-origin redirects, cache hit/expiry/logout/role/corruption, unsafe
probe URLs, evidence traversal and absolute paths. Link tests are present for both pack
directories and ledger files; this Windows host could not create the required links, so
pytest reported those two cases as platform skips rather than passes.

Validation after the final implementation changes:

| Check | Result |
|---|---|
| Full pytest suite with `dev,parallel` environment | 196 passed, 2 platform skips in 77.23 seconds |
| Ruff format/check | 97 files formatted; all checks passed |
| mypy | 41 source files passed |
| Frozen local corpus | 51 item-runs; accuracy 1.0, false green 0.0, false red 0.0, right reason 1.0, heal recall 1.0 |
| Build | sdist and wheel built; wheel contains the new sanitizer module |

The first full-suite attempt used the base `.venv`, which lacks the optional xdist
extra, and therefore failed only the two xdist launcher tests before test execution.
The recorded result above is the rerun in the audit environment with xdist 3.8.0.

## Remaining acceptance boundary

This receipt is implementation evidence for the T10 core, the read side of T11 and the
text-artifact core of T12. It does not close M1 or G2. Still required: Windows
junction/UNC and Linux symlink execution, browser/API refresh and logout integration,
import/retention boundaries, visual masking or an explicit screenshot policy, arbitrary
PII policy, adversarial review and a repeat on one committed SHA. No claim is made for
protection of sensitive production data before those gaps and the independent security
review are complete.
