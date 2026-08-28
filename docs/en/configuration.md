# Configuration

Nothing about an environment belongs in test code. Where to run, how to log in, and
with what credentials all come from configuration.

## Layers (highest precedence first)

1. Explicit flags — `pytest --testence-profile staging --testence-base-url ...`
2. Process environment — `TESTENCE_*`
3. `.env.local`, then `.env` in the project root (both git-ignored; `.env.local` wins)
4. Settings file — `testence.toml` (Python 3.11+) or `testence.json`
5. Built-in defaults

## Settings file and profiles

The settings file is tracked in the project's repo — it describes *environments*,
never secrets. Profiles make switching environments a one-word change:

```bash
TESTENCE_PROFILE=staging pytest tests_e2e/
pytest tests_e2e/ --testence-profile local
```

See [`testence.example.json`](../../testence.example.json) for a full example with
`local`, `staging`, `staging-attached` and `ci` profiles. An unknown profile name fails
immediately and lists the profiles that do exist.

Keys the framework knows: `base_url`, `api_prefix`, `auth`, `login_path`,
`api_login_path`, `cdp_url`, `browser_channel`, `headed`, `timeout_ms`, `verify_tls`, `ca_bundle`,
`runs_root`, `user_var`, `password_var`. Anything else lands in `settings.extra`
and is available to strategies and project adapters (e.g. `session_cookie`,
`token_storage_key`, `success_url_contains`).

Two `extra` keys the engine itself reads:

| key | meaning |
|---|---|
| `test_id_attribute` | DOM attribute `Target("testid", ...)` resolves against |
| `keep_animations` | `true` restores CSS entry animations (killed by default) |

`test_id_attribute` is a property of the *application*, not of the framework: few
apps ship `data-testid`, but many expose another stable identity attribute. Pointing
the test-id selector at that attribute avoids coupling the public DSL to application-
specific CSS or XPath. A flat attribute match is also inexpensive for Playwright to
re-evaluate during actionability checks.

`keep_animations` exists for the one case that legitimately asserts on an
animation. Leaving animations on costs ~1 s per 14 UI actions.

## Credentials

Only ever from the environment or `.env.local`:

```bash
TESTENCE_USER=user@example.com
TESTENCE_PASSWORD=...
```

Per-profile variable names are supported for multi-tenant setups — set `user_var`
and `password_var` in the profile (e.g. `TESTENCE_STAGING_USER`), then export those.

The framework treats credentials as radioactive: `Credentials` prints `***` in any
repr or traceback, `AuthContext.describe()` reports header and cookie *names* only,
and `Settings.describe()` — the thing written into `run.jsonl` — never contains a
secret. If you find a credential value in an evidence artifact, that is a bug worth
filing.

## TLS with a private certificate authority

A self-hosted test environment may use a private CA trusted by the browser through
the system store but absent from Python's bundle. That appears as
`CERTIFICATE_VERIFY_FAILED` on API calls while the UI works. In order of preference:

```bash
TESTENCE_CA_BUNDLE=/path/to/testing-root.pem    # best: verification stays on
TESTENCE_VERIFY_TLS=false                        # isolated test environments only
```

`verify_tls=false` also relaxes the browser context (`ignore_https_errors`), so the
UI and the API see the same thing.

## Runtime knobs unrelated to environments

| variable | meaning |
|---|---|
| `TESTENCE_RUNS_ROOT` | where run directories are written (default `runs/`) |
| `TESTENCE_KERNELS` | `auto` \| `reference` \| `native` — compute backend ([kernels.md](kernels.md)) |
| `TESTENCE_BROWSER_CHANNEL` | defaults to `chromium`, the fresh browser bundled with the installed Playwright release; `chrome` selects system Google Chrome |
| `TESTENCE_CDP_URL` | attach to a running Chrome instead of launching one |
| `TESTENCE_RUN_ID` | names the run directory; set by the plugin so every xdist worker shares one ([ADR-0012](adr/0012-parallel-execution.md)) |

`TESTENCE_RUN_ID` is set (with `setdefault`) in `pytest_configure`, before xdist
spawns anything, and inherited by the workers. Set it yourself only to make an
external tool write into a known directory; two concurrent, unrelated runs sharing
one value would interleave their ledgers.

Install the browser revision paired with the Python package once after setup:

```bash
python -m playwright install chromium
pytest examples/ -q --testence-headless
```

`--testence-browser-channel chrome` remains available for regression runs against the
system Google Chrome. Normal local and CI runs use bundled Chromium, so the browser
revision matches Playwright and does not depend on machine-wide browser state.

## Running in parallel

```bash
pip install testence[parallel]
pytest tests_e2e/ -q -n 4
```

Optional on purpose — a suite whose fixtures are not shard-safe must not acquire
workers by accident. Before adding `-n`, check the four invariants in
[ADR-0012](adr/0012-parallel-execution.md): one claim per case, one ledger per
process, per-worker seed namespaces, and per-worker offsets for anything
machine-wide (the debug port is `9222 + N`). Measure serial and parallel runs on
your own target before selecting a default worker count.
