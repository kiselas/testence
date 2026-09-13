# External panel smoke corpus

Four UI claims against two real, pinned upstream dashboard projects. Each repeat
starts fresh pytest/browser processes. The runner starts loopback HTTP servers on
free ports and checks exact expected failed tests and assertion messages. It exits
nonzero for an unexpected pass, failure, skip, setup error or missing test.
It also requires verified assurance for every healthy/restored/restyled case and
exactly two violated plus two verified cases in the defect phase, with no integrity
errors. Every UI state predicate carries its declared assertion and claim IDs.

This is an engineering smoke corpus. It is not the frozen R1 40-case corpus,
holdout evaluation, independent agent-client trial or backend persistence proof.

## Prepare

From the Testence repository root, install its locked development dependencies and
Chromium as described in CONTRIBUTING. Clone only if the directories do not exist:

```sh
git clone https://github.com/ColorlibHQ/AdminLTE.git .tmp/oss-adminlte
git -C .tmp/oss-adminlte checkout --detach 12b4b06ffe8fb1e5337a1022d7d4967c4d942a30
git clone https://github.com/tabler/tabler.git .tmp/oss-tabler
git -C .tmp/oss-tabler checkout --detach 68c844c7d16697a2dbab903de156b6d8f137b7e3
```

AdminLTE includes the built demo in `dist`. Tabler needs Node >=22.12 and its
pinned pnpm version. In `.tmp/oss-tabler` run:

```sh
npx --yes pnpm@11.17.0 install --frozen-lockfile
npx --yes pnpm@11.17.0 exec turbo run build --filter=@tabler/preview...
```

Then from the Testence root:

```sh
uv run testence plan validate bench/oss/plan.md --json
uv run python bench/oss/run.py --repeats 3 --output outputs/oss-panels
```

Use a new output directory for each invocation to preserve earlier evidence.
The runner refuses wrong revisions or modified tracked upstream files. Upstream
pages can load CDN assets; internet/cache state therefore affects measurements.
These results are not an offline reproducibility or cross-machine speed claim.
Isolated browsers use an ephemeral CDP port. A 120-second process deadline is
recorded as a failed attempt (exit 124); logs and checkpoint.json preserve partial
evidence. The runner continues the declared phases without retrying a failed attempt.

## Cases and controls

| Case | Healthy observation | Defect control |
|---|---|---|
| AdminLTE checkbox | selected then deselected | onchange immediately clears selection |
| AdminLTE radio | option two selected, option one cleared | unaffected control |
| Tabler password | show then hide changes masking | password-toggle hook removed |
| Tabler recovery | recovery heading after link click | unaffected control |

Phases are healthy → defect → restored → harmless border restyle. Defects change
only the served response; upstream files and accepted test code remain unchanged.
Each defect phase expects exactly two failed assertions, not a generic exit 1.
No retries or force clicks. The plan explicitly declares UI-only oracles.

`result.json` retains raw wall times, phase medians/maxima, framework revision and
dirty flag, target/license hashes, test/plan hashes, exit codes and assertions.
JUnit, logs and Testence run/pack artifacts are next to it. Build/discovery time is
excluded from replay timing. Three repeats are a smoke sample, not a p95 estimate.

Inspect screenshots and accessible states during authoring using the packaged
[visual discovery reference](../../src/testence/agent/skills/testence-author/references/visual-discovery.md).
The September audit includes an actual visual inspection; the deterministic suite
does not itself judge full-page appearance or accessibility.

## Rights and scope

[AdminLTE](https://github.com/ColorlibHQ/AdminLTE) and
[Tabler](https://github.com/tabler/tabler) declare MIT for their core. See exact
revisions and license paths in `targets.json`. License text and its hash are copied
to each local result bundle. Third-party images, charts and vendored libraries can
have separate terms. No upstream source, demo screenshots or bundled assets are
redistributed in Testence; clones/builds stay under ignored `.tmp/`. This manifest
does not replace the independent release rights review.
