# Stage 3 implementation progress

Updated: 7 September 2026. This is the engineering handoff for the current materialized
working tree. It is not an R1 acceptance receipt and it does not authorize publication.

Baseline: commit `7be8d025f81d9116ab267c59d440e14b377cfce7` with the existing large
uncommitted R1 implementation preserved. The final local regression on that materialized
tree is 389 passed and two Windows symbolic-link privilege skips in 158.29 seconds.

| Task | Engineering status | Evidence and remaining acceptance |
|---|---|---|
| S3-00 | locally_verified | Baseline, audit A01-A09 and R/T/S3 mapping are preserved in this stage directory and the dated audit. A clean candidate SHA is still absent. |
| S3-01 | locally_verified (core) | Strict bounded UTF-8 JSON rejects duplicate keys and non-finite numbers; packaged Draft 2020-12 schemas include corpus, release and acceptance receipt contracts. Legacy adapters cannot authorize RC. |
| S3-02 | locally_verified on Windows | Portable path grammar, reparse/junction checks and atomic replacement cover application, agent, quality and readers. Two symlink cases need hosted Linux execution. |
| S3-03 | locally_verified (core) | Init, agent install and quality-pack changes use one writer lock, preflight and durable staged journal/recovery. Quality dry-run returns add/replace/delete/keep/preserve/conflict plan without mutation. Hosted fault matrix remains an RC receipt. |
| S3-04 | locally_verified (core) | Effective/upstream digests, removed files, immutable verified history, corrupt rollback refusal, concurrent writer refusal, kill recovery and preservation of newer human edits are covered. |
| S3-05 | implemented_partial | Body capture is default-deny, content-type/declared-byte bounded at 64 KiB, screenshot capture is separate opt-in, tap rings expose caps/omissions. Existing auth isolation and redaction tests pass. The complete real login/refresh/logout/role-switch, archive import and retention SEC matrix is not yet an RC receipt. |
| S3-06 | locally_verified (structure/freeze) | Corpus `/2` has 40 cases, exact strata, eight holdouts, selector/source hashes and a separate content freeze; fake target/reviewer metadata cannot pass acceptance. |
| S3-07 | implemented_partial | Registry/evaluator guards and synthetic corpus cases exist. Forty isolated consumer executions with hidden custodian truth and raw repeated outcomes remain pending. |
| S3-08 | external_pending | Two distinct licensed OSS targets, independent truth reviewers and deterministic external reruns require real repositories/people. No identities, signatures or runs were synthesized. |
| S3-09 | locally_verified Windows | Exact wheel `80e7f683…0473` was installed in a fresh Python 3.13 environment; 101 package files, 27 schemas, Codex/Claude packs, three-mode demo and Chromium 151 were verified. Hosted Windows/Linux receipts remain. |
| S3-10 | locally_verified development snapshot | Two builds produced identical wheel/sdist bytes; rebuilding from the exact sdist matched 106 normative files. Resolved 16-package Windows inventory is wheel/smoke-bound; SPDX 2.3 validates with spdx-tools 0.8.5. Clean-source Linux SBOM/scans remain. |
| S3-11 | locally_verified validator | Manifest `/2` validates exactly R01-R24/G1-G8, file hashes, profiles, candidate SHA and owner payload binding. General acceptance receipts are validated internally. Current candidate is correctly no-go. |
| S3-12 | locally_verified Windows | Installed-wheel demo proves healthy persisted state, catches optimistic false green with a real pack/screenshot, and accepts a harmless layout change. Hosted Linux portability remains. |
| S3-13 | implemented_partial | Whole normative skill-pack digest, transactional two-client install/verify, bound verdict/repair checks and filtered multi-project quality summary exist. Two actual client workflows and three-repository consumer receipt remain external/RC work. |
| S3-14 | locally_verified smoke | Five warm/cold 10k-result repetitions passed budgets with deterministic output; failure storm covers 1000 bounded failures. Thirty-repeat reference-host, 100 MiB streaming, 100k console and 50 warm browser runs remain. |
| S3-15 | implemented | CI defines locked quality, Windows/Linux × Python 3.10/3.12, dependency floor, browser tests, one immutable distribution artifact, installed-wheel smoke, sdist rebuild, resolved SBOM and provenance. Hosted run on a clean candidate remains required. |
| S3-16 | implemented_partial | EN/RU docs, support manifest, community/security files and publication inventory exist. Clean tree/history scans, independent rights review, verified private reporting settings and final video remain. |
| S3-17 | publishing_prepared | Manual protected workflow verifies tag→SHA→manifest→artifact bytes and publishes the sealed bundle through PyPI OIDC without rebuilding. GitHub environment/trusted publisher are not configured or exercised here. |
| S3-18 | external_pending | Live TestOps round trip, five users/three teams, week-return, independent security/rights/truth reviews require external tenants and people. Prepared protocols exist; no evidence was fabricated. |
| S3-19 | engineering_handoff | Local code, tests, artifacts and no-go decision are assembled. R1 acceptance needs a clean commit, hosted receipts and every external gate before owner `go`. |

Final local checks:

- `pytest`: 389 passed, 2 skipped;
- Ruff format/lint: passed for `src tests bench scripts`;
- mypy: passed for 66 source/script modules;
- wheel: `sha256:80e7f683981a6185e10d21bf87062999cd27f208cb45c9945dfd1eb0968a0473`;
- sdist: `sha256:94603be0e71af3d798418db1b42e388ef2a2eec67dab3f537d4956c685970808`;
- installed-wheel smoke, sdist rebuild, SPDX validation and five-repeat scale budget: passed.

The release manifest remains `no-go` because development evidence from a dirty tree is
not a clean candidate-bound RC profile and cannot substitute for hosted or external
acceptance.
