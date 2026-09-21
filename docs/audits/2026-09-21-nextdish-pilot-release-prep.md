# NextDish pilot retrospective and public-release preparation — 21 September 2026

Status: engineering fixes merged to `main`; version `0.1.0a1` selected for the release
candidate. The repository is public and private vulnerability reporting is enabled.
Tag creation and PyPI publication have not been performed.

## What the pilot changed

The first 12 accepted NextDish browser cases replayed in 63.7 seconds, but the complete
authoring interval was about 40 minutes. Most of that gap came from discovering fixtures,
recovering Vite dependencies, recreating local services for rate limits, mapping runtime
credentials, and learning which oracle adapters were unavailable. Later NextDish work
confirmed that deterministic replay was already the smaller part of the cost.

The framework changes now address the reusable part of that failure:

- `testence plan prepare` checks capabilities, oracle adapters, credentials, files and
  HTTP/JSON fixtures before opening a browser;
- opt-in, project-owned fix recipes bootstrap only declared prerequisites, discard
  command output, and must pass the same readiness check after execution;
- warm authoring and identity-scoped session caches reduce repeated browser and login
  setup while fresh processes remain the acceptance path;
- frame contexts now scope `eval_js` and predicate waits as well as locators, so iframe
  style, overflow and state assertions no longer need Playwright internals;
- the publish gate passes manual inputs through environment variables and verifies the
  embedded `Name` and `Version` metadata in both candidate distributions.

Application fixtures remain application-owned. A framework cannot infer a safe table
token, chat sink, role account, purge operation or accessibility policy. Projects should
declare those capabilities in their readiness manifest and expose an idempotent,
disposable seed. Missing prerequisites remain `blocked` instead of becoming skips,
retries, or weaker assertions.

## Release preparation boundary

Before publishing `0.1.0a1`:

1. merge the framework fixes into a clean candidate and run the complete Windows/Linux
   CI matrix plus installed-wheel browser jobs;
2. build one immutable wheel and sdist, confirm reproducibility, and preserve their
   hashes, dependency inventory, SPDX SBOM and provenance;
3. scan the exact clean tree, history and resolved dependencies, then complete the
   independent security and publication-rights reviews;
4. change repository visibility, then immediately enable and verify GitHub private
   vulnerability reporting before announcing the repository;
5. configure the protected `pypi` environment and the PyPI trusted publisher for
   `kiselas/testence`, `.github/workflows/publish.yml`, environment `pypi`;
6. assemble a candidate-bound `go` manifest, create an immutable matching version tag,
   and obtain the owner's decision for those exact artifact hashes;
7. dispatch `publish.yml`. It downloads the candidate produced by the selected CI run,
   verifies the tag, manifest, build receipt and distribution bytes, and publishes the
   sealed artifacts without rebuilding.

Opening the repository and uploading to PyPI are separate actions. Neither should happen
while `SECURITY.md` still says that outside vulnerability reports are unavailable or the
release manifest remains `no-go`.

Current operational status:

| Step | Status | Closure condition |
|---|---|---|
| Pilot framework fixes | complete | PR #9 merged to `main` with all hosted checks green |
| Package version | in progress | `0.1.0a1` metadata, lock, wheel and docs agree; release PR green |
| Public source inventory | prepared | independent rights review binds the clean candidate SHA |
| Security review | pending | exact candidate scan/review has no unexplained blocking finding |
| Repository visibility | complete | `kiselas/testence` is public |
| Vulnerability reporting | complete | GitHub API reports `enabled: true`; public report route is documented |
| GitHub `pypi` environment | pending | environment exists with required owner approval |
| PyPI trusted publisher | pending | project `testence` trusts `publish.yml` / environment `pypi` |
| Release manifest | pending | all required receipts resolve and owner decision is `go` |
| Tag and upload | pending | immutable `v0.1.0a1` tag matches candidate; verified workflow publishes existing artifacts |

## Validation and handoff

The focused checks for this change are `tests/test_capabilities.py`,
`tests/test_publish_inputs.py`, and `tests/test_documentation.py`. The complete release
candidate must also run the commands in `CONTRIBUTING.md` from a clean checkout and the
installed-wheel jobs in `.github/workflows/ci.yml`.

Local Windows validation of the merged pilot fixes:

```text
uv run ruff format --check src tests bench scripts
164 files already formatted

uv run ruff check src tests bench scripts
All checks passed!

uv run mypy src scripts
Success: no issues found in 68 source files

uv run pytest -q --basetemp=<new repository-local directory>
441 passed, 2 skipped in 106.20s
```

The two skips are the existing Windows symlink-privilege cases. This local result is an
engineering check and does not replace the clean hosted candidate matrix.

The subsequent `0.1.0a1` version-consistency change passed Ruff, mypy, 21 focused
distribution/documentation tests, and the complete local suite: **443 passed, 2 known
Windows symlink skips in 161.93 seconds**. Clean distribution and hosted results must be
bound to the final alpha candidate commit after this document is committed.

The NextDish repository retains its full canonical suites and a generated backlog of all
browser cases without accepted Testence evidence. Product-specific open findings remain
in `docs/testcases/testence-release-fixes.md`; they are not Testence release claims.
