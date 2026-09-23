# macOS support — 23 September 2026

Status: engineering candidate on branch `macos-support`. macOS (Apple Silicon) is in the
CI matrix and its first hosted run is recorded below. No macOS machine was available to
the author; every macOS observation here comes from the hosted `macos-latest` runner.
`0.1.0a1` on PyPI was published without macOS receipts and is not retroactively
verified by this work.

## Scope

In scope: the Python package, the pytest plugin, the CLI, the bundled Playwright
Chromium, the installed-wheel smoke and the visual client simulation on macOS arm64.

Out of scope until separately proven: Intel macOS (GitHub no longer offers a free
x86_64 runner for this matrix), the `chrome`/`msedge` channels on macOS, the headed
long-lived dev browser, and a real agent client session on a Mac.

## Starting point

The code was already close to portable. Two OS branches exist: the quality lock uses
`fcntl.flock` off Windows, and link detection adds reparse points on Windows. Both
POSIX branches were already exercised on Linux, and `mypy --platform darwin src scripts`
is clean. Playwright 1.62 in `uv.lock` has macOS x86_64, arm64 and universal2 wheels.
Every subprocess uses `sys.executable`, servers bind `127.0.0.1`, and the tracked tree
has no case-colliding or non-ASCII file names.

## Changes

1. **Finder metadata no longer breaks managed walkers.** A `.DS_Store` or AppleDouble
   `._name` file blocked quality transaction recovery, changed the CI delivery identity
   of an Allure results folder, and entered the skill pack from an editable checkout.
   `managed_paths.is_shell_metadata` now matches only regular files with those names
   plus Explorer's `Thumbs.db`/`desktop.ini`; unknown entries still fail closed. Each
   regression test fails without the fix (checked by reverting the source change).
2. **CI.** `macos-latest` joined the test matrix (Python 3.10 and 3.12) and the visual
   client simulation, and a macOS installed-wheel job uploads
   `installed-wheel-smoke-macos.json`. The documentation contract now derives the
   platform set from every OS matrix in `ci.yml` and requires an installed-wheel job
   per non-Linux runner.
3. **Declarations.** `support.json`, SUPPORT, CONTRIBUTING, the `Operating System ::
   MacOS` classifier, the CLI docstring and both changelogs name macOS on Apple Silicon.
   The release manifest `release/rc-manifest-v2.json` is frozen for `0.1.0a1` and was
   not edited; the next candidate's manifest must list `macos-latest`.
4. **Honest caveats in the docs** (English and Russian):
   - evidence schema: macOS `fsync` does not flush the drive cache (`F_FULLFSYNC`
     does); Testence keeps plain `fsync`, so a power loss can drop the last events;
   - configuration: `chrome`/`msedge` need the applications in `/Applications`, and a
     low default `ulimit -n` can starve parallel workers.

Visual baselines already record the OS in their profile (ADR-0023), so a Linux or
Windows baseline is refused on macOS by design rather than compared across font
rasterizers.

## Validation without a Mac

Ranked by the assurance each gives:

1. **Hosted `macos-latest` runs** — the only source this project accepts for a
   release-verified platform. The repository is public, so these minutes are free.
2. **Local pre-checks on Windows** — `mypy --platform darwin`, file-name collision
   scan, the full suite with the regression tests. They cover Darwin-specific typing and
   the metadata defect, not runtime behaviour.
3. **Rented Mac** (for example a cloud Mac mini with a 24-hour minimum) — only if a
   headed or interactive check is needed that a hosted runner cannot give.
4. **A contributor's receipt** — run the commands below on a Mac and send the JSON.

macOS virtual machines on non-Apple hardware violate the macOS licence and are not an
acceptable validation path for this project.

## Hosted runs

**Run 1** — [35887593956](https://github.com/kiselas/testence/actions/runs/35887593956),
revision `8e4ce53`, dispatched manually on `macos-support`.

| Job | Result |
|---|---|
| Quality, minimum dependencies, Linux 3.10/3.12, Windows 3.12 | passed |
| Visual client simulation on Linux, Windows and macOS | passed |
| macOS 3.10 and 3.12 | 1 failed, 465 passed, 1 skipped; about 9 minutes each |
| Windows 3.10 | 1 failed, 466 passed |
| Installed-wheel jobs | skipped, because a test job failed |

Both macOS failures were `test_state_must_remain_true_through_the_observation_window`:
the verdict was correctly `failed`, but a 5 ms sleep lasted over 20 ms, so the oracle
made two reads where the test demanded three. The Windows failure was
`test_deadline_shorter_than_stability_window_is_inconclusive`, which returned `passed`:
a delayed read past the 5 ms deadline completed a 30 ms stability window. That is a
false green, fixed in the oracle by `4c2d43e`; the window tests now use a virtual clock
with explicit sleep overshoot. The first run also confirmed the local fixes: nothing
else in the suite failed on macOS.

The macOS test jobs take about four times longer than Linux; the review below found
the cause.

**Run 2** — [35889355676](https://github.com/kiselas/testence/actions/runs/35889355676),
revision `99b73a8`, dispatched manually on `macos-support`. All 14 jobs passed.

| macOS job | Result |
|---|---|
| Python 3.10 suite | 469 passed, 1 skipped, 9 min 16 s |
| Python 3.12 suite | 469 passed, 1 skipped, 9 min 8 s |
| Documented examples, both Pythons | 5 passed, 1 skipped |
| Visual client simulation | passed |
| Installed-wheel smoke | passed; receipt in artifact `testence-99b73a8…-macos-wheel-smoke` |

The skipped suite test is the Windows-only junction case. This is an engineering
receipt for a branch revision, not release verification: the next clean candidate must
repeat the matrix on its exact commit.

**Run 3** — [35898328733](https://github.com/kiselas/testence/actions/runs/35898328733),
revision `e9cee5f`, after the loopback server fix and the rebase onto `main`. All 14
jobs passed.

| Suite, Python 3.12 | Before the fix | After the fix |
|---|---|---|
| macOS | 567 s | 163 s |
| Windows | not measured | 164 s |
| Linux | 67 s | 95 s |

macOS now runs as fast as Windows. The remaining gap to Linux is the slower Chromium
launch on the hosted Windows and macOS runners, about 1 s per browser test.

## Review findings

**Slow macOS suite: a 35-second reverse DNS lookup.** Timing run
[35892194670](https://github.com/kiselas/testence/actions/runs/35892194670) (revision
`73a398d`) uploads per-test JUnit timings. The suite took 567 s on macOS against 67 s on
Linux, and six tests produced 450 s of the gap in multiples of about 37 s: three demo
runs at three multiples each, `init`, the scaffold run and the first test-auth setup at
one each. Every other browser test was about 1 s slower, which matches a slower
Chromium launch.

`http.server.HTTPServer.server_bind` calls `socket.getfqdn(host)`. A temporary probe on
the hosted runner (macOS 26.6.2, branch deleted after the run) measured:

| Operation | Time |
|---|---|
| `getfqdn("127.0.0.1")`, first call in a process | 35.0 s |
| the same call again in that process | 0.002 s |
| `ThreadingHTTPServer(("127.0.0.1", 0))`, first in a process | 35.0 s |
| the same server with `server_bind` skipping `getfqdn` | 0.000 s |
| `getfqdn()` of the host name | 70.0 s |
| warm Chromium launch | 1.6-1.8 s |

The cost is paid once per process, so every subprocess that starts a server pays it
again. It is not only a test problem: the demo target server in
`src/testence/application.py` runs inside user projects, so `testence demo run` on a
Mac with this resolver behaviour loses 35 s per scenario. `tests/mock_app.py`,
`tests/test_auth.py`, `bench/client_simulation`, `bench/oss` and the `python -m
http.server` benchmarks inherit it too, which also skews macOS benchmark numbers.
Fixed: `testence.loopback.LoopbackHTTPServer` records the bound address without a
reverse lookup (`server_name` is read only by CGI), and `python -m testence.loopback`
replaces `python -m http.server` in the benchmarks. The standalone SUT in `bench/sut`
carries its own copy so it stays independent of the framework under test. Two
benchmarks were broken on macOS rather than slow: `bench/competitive` waits 5 s and
`bench/i3_baseline` 1.5 s for a port that opens only after the 35 s lookup. A
repository test fails if a plain stdlib server construction returns.

**Case-insensitive file systems accept colliding quality-pack paths.** Reproduced on
NTFS, which behaves like default APFS: a pack listing `quality/A.json` and
`quality/a.json` loads and applies, one file lands on disk, and the lock records two
managed files. A Linux-authored pack with distinct contents would instead fail to load
on macOS and Windows with a misleading integrity mismatch. Proposed fix: reject paths
that are equal after `casefold()` (and Unicode normalization) at load time on every
platform. The defect predates this branch.

**Smaller review notes.**

- A positive `stability_ms` equal to `deadline_ms` can now never pass. It rarely
  could before; a configuration check that rejects `stability_ms >= deadline_ms` early
  would be clearer than an inconclusive result after the full deadline.
- Inside the deadline, a window can still be completed by two reads far apart when
  the scheduler oversleeps. Sampling density is not enforced.
- `fcntl.flock` may be unsupported on SMB or NFS mounts; the quality lock would then
  report "another operation is in progress" instead of the real cause.
- The dependency floors in `support.json` are exercised only on Linux.
- `macos-latest` will move to a newer macOS without notice; receipts record
  `platform.platform()`, so the tested version stays traceable.

## Remaining uncertainty and next steps

- Timing-sensitive tests (`tests/test_speed.py` waits of 250–500 ms) are the most likely
  macOS flakes. A failure there is investigated, not absorbed by raising the budget.
- `pytest -n` with many browser workers on a 256-descriptor shell is untested.
- The headed dev browser (`python -m testence.dev_browser`) and the `chrome` channel
  have not been launched on macOS.
- Release: the next clean candidate must pass the full matrix including all macOS jobs,
  and its manifest must reference the macOS wheel smoke receipt.

Contributor receipt on a Mac:

```bash
uv sync --locked --extra dev --extra parallel --extra visual
uv run playwright install chromium
uv run pytest -q
uv run pytest examples -q --testence-headless
uv build --wheel --out-dir dist
uv venv .wheel-venv
uv pip install --python .wheel-venv/bin/python dist/testence-*.whl
.wheel-venv/bin/python -m playwright install chromium
.wheel-venv/bin/python -I scripts/installed_wheel_smoke.py --distribution dist/testence-*.whl --output installed-wheel-smoke-macos.json
```

The smoke compares installed files with the wheel bytes, so it must run from that
separate environment, never from the editable development one.
