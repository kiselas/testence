# OSS publication inventory

Updated: 7 September 2026. Scope: the files intended for the first public source
release. This is an engineering inventory; the independent rights decision remains
pending and is represented as incomplete in `release/rc-manifest-v2.json`.

| Scope | Recorded origin | Intended license/distribution | Modifications | Review state |
|---|---|---|---|---|
| `src/testence/`, `scripts/`, `tests/` | Testence repository history | Apache-2.0; source and package | Active R1 development | maintainer inventory complete; independent rights review pending |
| `docs/`, root Markdown, `.github/` | Testence repository history | Apache-2.0; public source/docs | Active R1 development | maintainer inventory complete; independent rights review pending |
| `examples/`, generated demo fixture text | Testence repository history; synthetic loopback SUT | Apache-2.0; public examples | Deterministic R1 demo | independent rights review pending |
| `bench/`, `corpus/` | Testence repository history; synthetic cases and local fixtures | Apache-2.0; public benchmark protocol/fixtures | Corpus `/2` freeze added | two future OSS target repositories are references, never vendored copies; target selection/review pending |
| `docs/assets/testence-mark.svg` | Testence repository history | Apache-2.0; public documentation asset | Repository mark | independent rights review pending |
| Python dependencies | PyPI distributions resolved by the candidate consumer | Their upstream licenses; dependencies are referenced, not vendored | None | exact Windows inventory and SPDX SBOM generated; Linux inventory and rights review pending |
| Playwright Chromium/driver | Installed by Playwright tooling | Upstream component terms; not committed to Git | None | exact local browser/Playwright versions recorded; review pending |

Local `.venv*`, `.tmp*`, `build/`, `dist/`, `runs/`, `.testence/`, `.mcp.json`,
`.env*` values, `outputs/` transcripts and browser caches are excluded from the public
source inventory. Only explicitly selected, sanitized, digest-bound receipts may move
from `outputs/` into a public release evidence bundle.

Before the rights gate can pass, the reviewer must inspect the exact clean candidate
tree and history, resolve any secret/license scan findings, decide whether `NOTICE` is
required, and produce an external acceptance receipt bound to the candidate SHA and
this inventory's digest.
