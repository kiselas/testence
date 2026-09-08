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

Keys the framework knows: `project_id`, `base_url`, `api_prefix`, `auth`, `login_path`,
`api_login_path`, `cdp_url`, `execution_mode`, `browser_channel`, `debug_port`, `headed`,
`timeout_ms`, `verify_tls`, `ca_bundle`,
`runs_root`, `user_var`, `password_var`. Anything else lands in `settings.extra`
and is available to strategies and project adapters (e.g. `session_cookie`,
`token_storage_key`, `success_url_contains`).

`project_id` is the repository-owned namespace used by ledger, packs, verdicts and
report history. Set it explicitly in `testence.json`; the package name from
`pyproject.toml` is only a compatibility fallback for projects not yet migrated.

`execution_mode` is `isolated` by default. Each test receives a new owned browser
context, auth session and API client; owned processes and ports close after pass,
failure or interruption. `warm` retains the runner-owned browser process while
replacing its context before every test. `attached` is selected automatically by
`cdp_url`; it borrows the launcher's context and never closes that browser. Warm and
attached are explicit authoring modes and are not CI isolation.

Use `testence_namespace` or its `testence_seed_marker` string in project seed fixtures.
The marker includes project, run, worker, case, role and attempt. Pair it with
`SeedLifecycle(owner=...)` so cleanup failures stay visible and reverse-order or xdist
runs cannot share a data namespace.

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

`ApiClient` sends the inherited Authorization header only to the normalized origin
of `base_url` and the optional `api_allowed_origins` list. An absolute URL on another
host or port, an HTTPS-to-HTTP downgrade, and a redirect to another origin fail before
credentials reach the destination. Cross-origin API access therefore requires an
explicit profile entry. Browser cookies additionally keep their domain, path, secure
and expiry scope.

## Optional session cache

Session reuse is disabled until a profile declares an identity probe. A safe cache
profile names the expected role and a finite TTL:

```json
{
  "session_probe_path": "/api/v1/auth/me",
  "session_cache_ttl_s": 900,
  "session_identity_field": "email",
  "session_role_field": "role",
  "session_expected_role": "qa-admin"
}
```

The probe must return a JSON object containing the configured identity and role.
Before every reuse Testence requires HTTP 2xx, the configured account and role, and
an unexpired cache record. A logout, corrupt or legacy cache, changed project,
origin, account, profile, role or auth strategy causes a real login. Cache filenames
are scope-derived, account values are hashed, and files use owner-only mode where
the operating system supports it. Keep the cache under the ignored `runs_root`.

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
| `ALLURE_TESTPLAN_PATH` | standard Allure `version: 1.0` selective plan; invalid/unresolved/empty scope fails closed |
| `TESTENCE_EMPTY_TESTPLAN` | `fail` (default) or explicit `noop`; the CLI equivalent is `--testence-empty-testplan=noop` |

For a repeated agent-authoring loop, launch and authenticate the browser once, then
run any number of short pytest processes through an attached profile:

```bash
python -m testence.dev_browser --profile staging
pytest tests_e2e/ -k current_case --testence-profile staging-attached
```

The launcher owns the persistent context. Attached pytest runs reuse its cookies,
storage and current page, reset Testence's capture buffers per test, and detach without
closing that context. This is a repeated-run optimization: a one-off command still has
to pay the launcher cost.

Add `--warm` to `testence watch` only during authoring. Every `-w` directory becomes a
module-reload boundary: project modules imported from those roots are evicted before
the next pytest session, while Testence remains loaded. Keep normal subprocess
isolation for CI and release evidence.

Warm mode also retains its Playwright/CDP engine between sessions. The engine key
contains every browser-connection setting; changing one closes the old client and
creates a new one. Stopping the warm runner releases the retained client.

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

## Evidence capture policy

Network bodies and screenshots are disabled unless the project opts in. Text evidence
such as ARIA, bounded console records and sanitized URLs remains available. A project
that uses synthetic data may enable specific capture channels in `testence.json`:

```json
{
  "extra": {
    "capture_policy": {
      "network_bodies": true,
      "screenshots": true,
      "body_content_types": ["application/json"],
      "body_cap_bytes": 65536
    }
  }
}
```

The hard body ceiling is 64 KiB. A body with an untrusted content type, missing size,
or declared size above the limit is omitted before Testence asks Playwright to
materialize it. The pack records disabled/error/omission state. Screenshot capture is
separate because text redaction cannot sanitize pixels.

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
