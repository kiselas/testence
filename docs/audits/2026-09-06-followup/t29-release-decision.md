# T29 release decision

Status: **manifest assembled; decision no-go**.

`release/rc-manifest.json` is a validated `testence/release-manifest/1` document mapping
G1–G8 to concrete receipts and missing evidence. It identifies the target version
0.1.0a1, local distribution artifacts and rollback instructions. It intentionally has
no RC SHA or tag and marks the working tree dirty.

Final local verification on the assembled working tree: 339 tests passed and two
platform link cases skipped in 122.01 seconds; the separate minimum-dependency run also
passed 339 with two skips. Ruff format/check, mypy over 61 source files, actionlint
1.7.12, sdist/wheel build, installed-wheel Chromium smoke, schema/docs links, corpus
freeze and both performance budgets passed. Distribution checksums were recomputed and
verified after the final build. All authorized `.tmp-pytest-*` directories were removed.

G1 and G5 have local passing evidence. G2, G3, G4, G6, G7 and G8 remain incomplete or
blocked by independent security/Linux validation, live TestOps, two licensed OSS SUTs
and truth reviewers, external pilots/reproductions, the real security channel, the video
and hosted checks on one clean RC SHA. The recorded decision is `no-go`; no package,
tag, repository visibility or external message was published by this work.
