# T13 expected-state implementation receipt

Date: 2026-09-06. Status: locally implemented and verified; review/commit SHA pending.

## Delivered behavior

`ExpectedState` describes the product state that must be observed through an
authoritative JSON read. It can bind entity, actor role, correlation id and minimum
revision before evaluating the business predicate. `ApiClient.get_fresh` forces cache
bypass headers, so a stale value that merely agrees with the UI cannot satisfy proof.

`observe_expected_state` repeats only the safe read until a deadline. A positive result
may have to remain true for `stability_ms`; the same window supports negative claims and
catches a delayed rollback. Empty, non-JSON, HTML and rejected/error HTTP responses are
classified `inconclusive`. A usable response with the wrong entity, role, correlation,
revision or business state is `failed`.

`RequestExpectation` binds one UI mutation by exact path, HTTP method and optional
origin, correlation id, GraphQL operation or record predicate. The Playwright engine
can skip unrelated completed traffic on the same endpoint. `save_and_verify_state`
takes the network mark before clicking, executes the mutation once, rejects duplicate
matching requests, requires a completed successful JSON response, and only then polls
the authoritative read. The emitted oracle and assertion evidence carries the operation
binding, observation classification, reason, attempt count and elapsed time.

`Actions.verify_state` exposes the read-only expected-state path to project ActionMaps.
The older `verify` and `save_and_verify` calls remain compatible.

## Executable corpus

`corpus/expected-state-v1.json` contains 13 deterministic cases: healthy, optimistic
stale read followed by commit, stale-but-equal state, empty/HTML responses, wrong
entity, wrong role, delayed commit, rollback during the observation window and
401/403/404/500 oracle responses. The corpus is run by pytest and is included in the
source distribution through `MANIFEST.in`. Separate tests cover an aborted mutation,
duplicate mutation, GraphQL/correlation matching and a broken predicate.

## Verification

| Check | Observed |
|---|---|
| Full pytest, `dev,parallel` environment | `269 passed, 2 skipped in 83.40s` |
| Expected-state/corpus/speed/auth subset | `82 passed in 35.21s` |
| Ruff check and format | all checks passed; 83 files formatted |
| mypy | success, 45 source files |
| wheel + sdist | `uv build` succeeded; expected-state corpus present in sdist |
| installed wheel, isolated cwd, Python `-I` | expected state evaluated `passed`; request expectation imported |

Build artifacts are under `outputs/audit-2026-09-06-followup/t13-dist/`.

## Boundary

This closes the local T13 foundation. T14 still owns verdict pointer/digest binding and
repair proof. T19–T20 own runtime isolation, strict action semantics and the complete
engine capability matrix. T23 owns the frozen independent corpus and external truth
review. This receipt is not immutable until review and commit.
