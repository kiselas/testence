# Configuration

Nothing about an environment belongs in test code. Where to run, how to log in, and
with what credentials all come from configuration.

## Layers (highest precedence first)

1. Explicit flags — `pytest --testence-profile staging --testence-base-url ...`
2. Process environment — `TESTENCE_*`
3. `.env.local`, then `.env` in the project root (both git-ignored; `.env.local` wins).
   [`.env.example`](../../.env.example) lists every variable Testence reads.
   Save these files as UTF-8; a byte-order mark is tolerated.
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
`token_storage_key`, `success_url_contains`, `api_auth_from_storage` —
[auth](auth.md#single-page-apps-that-keep-a-token-in-storage)).

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

A profile is merged into the base file table by table: it restates only what differs,
and a table it names keeps the base's other keys. An empty table (`{}`) changes nothing;
set a key to another value to replace it.

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
explicit profile entry. The browser follows the same rule: Bearer and Basic headers
are added only to requests for those origins, never to a CDN, analytics or font host
the page loads from. Browser cookies additionally keep their domain, path, secure and
expiry scope.

`ApiClient` keeps its connections alive: one per origin, so the calls of a test share
one TCP and TLS connection, closed when the test ends. Before an idle connection is
used, it is checked: one the server closed while it sat idle is discarded and the
request goes on a new connection. A connection that breaks while a request is in flight
is retried once on a new connection only for an idempotent method (GET, HEAD, OPTIONS,
PUT, DELETE); a POST or PATCH is never sent twice behind the test's back, the call
fails instead, because the application may have applied it. A connection that fails or
breaks raises `urllib.error.URLError`, as before; a call without an answer in time
raises `TimeoutError`. Redirects follow urllib's rules (GET and HEAD follow, a POST
answered 301-303 continues as a GET without its body, anything else is returned) and
stay on the origin. Proxies come from the environment or the system settings, read for
every request, as with urllib.

## Optional session cache

Session reuse is disabled until a profile declares an identity probe. The smallest
cache profile names the probe and a finite TTL:

```json
{
  "session_probe_path": "/api/v1/auth/me",
  "session_cache_ttl_s": 900,
  "session_identity_field": "user.email",
  "session_id_field": "user.id"
}
```

The probe must return a JSON object containing the configured identity
(`session_identity_field`, default `email`; a dot path reads a nested field). The
identity is that value plus, when named, `session_id_field` and `session_role_field`:
a different id or role behind the same account is another identity. A role is not
required. Add `"session_expected_role": "qa-admin"` to pin one; it is enforced only
when set, reads `role` unless `session_role_field` names another field, and a probe
without that field is then never reused. A named id field that is missing from the
probe is a miss too. Before every reuse Testence requires HTTP 2xx, the configured
account (and role, when expected), the same identity as when the session was cached,
and an unexpired cache record. A logout, corrupt or legacy cache, changed project,
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
| `TESTENCE_BROWSER_CHANNEL` | defaults to `chromium`, the fresh browser bundled with the installed Playwright release; `chrome` or `msedge` select a system browser, `chromium-headless-shell` the bundled headless-only build. Also the default for `Settings` and engines constructed directly, without `Settings.load` |
| `TESTENCE_CDP_URL` | attach to a running Chrome instead of launching one |
| `TESTENCE_RUN_ID` | names the run directory; set by the plugin so every xdist worker shares one ([ADR-0012](adr/0012-parallel-execution.md)) |
| `ALLURE_TESTPLAN_PATH` | standard Allure `version: 1.0` selective plan; invalid plans fail, unresolved entries are reported ([reporting](reporting.md#selecting-tests-from-a-testops-plan)) |
| `TESTENCE_TESTPLAN_UNRESOLVED` | `warn` (default) or `fail` for plan entries that match no collected test |
| `TESTENCE_SCHEDULE` | `default` or `longest-first`: order tests under pytest-xdist by earlier durations (`--testence-schedule`, [running in parallel](#slowest-tests-first)) |
| `TESTENCE_RERUNS` | repeat a failed test up to N times, 0–5 (`--testence-reruns`); every attempt is recorded ([reporting](reporting.md#reruns-and-flaky-tests)) |
| `TESTENCE_ALLURE_RESULTS` | stream Allure results into this directory as tests end (`--testence-allure-results`) |
| `TESTENCE_FULL_TRACE` | `1` keeps the frames of Testence and Playwright below the test in failure tracebacks (`--testence-full-trace`; pytest's `--full-trace` does the same) |
| `TESTENCE_EMPTY_TESTPLAN` | `fail` (default) or explicit `noop`; the CLI equivalent is `--testence-empty-testplan=noop` |

### When a pytest session records a run

The plugin loads into every pytest session of an environment that has the package, but
a session writes a run directory only when it is a Testence session:

- it was started by the `testence` CLI (`run`, `watch`, `ci`), which names the run;
- a `--testence-*` option is on the command line — the way to record a whole suite,
  Testence tests or not, for an Allure or TestOps upload; or
- a collected test uses a Testence fixture (`ex`, `testence_*`) or the
  `@pytest.mark.testence` marker. The whole session is then recorded, including its
  other tests.

A session with none of these writes nothing, and an invalid `testence.json` does not stop
it. When a Testence session meets invalid settings, pytest exits with a usage error (code
4) that names the setting. A Testence fixture requested only through
`request.getfixturevalue()` in a session that is otherwise not recording raises an error
that says so: declare it in the test signature instead.

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

If a host cannot start the bundled `chrome.exe` at all (for example a Windows
application-control policy rejects its private side-by-side assembly while the
same-revision `chromium-headless-shell` and system Edge start fine), set
`TESTENCE_BROWSER_CHANNEL=msedge` or `chromium-headless-shell` for that machine. The
variable also reaches `Settings(...)` and engines constructed directly rather than
through `Settings.load`, such as the repository's own browser tests; an explicit
`browser_channel=` argument still
wins, and CI keeps the bundled Chromium because it does not set the variable.

On macOS the bundled Chromium needs nothing beyond `python -m playwright install
chromium`. The `chrome` and `msedge` channels launch the applications installed in
`/Applications`, so they are available only where Google Chrome or Microsoft Edge is
installed. Parallel runs open several browsers at once, and a macOS shell may start
with a soft file descriptor limit as low as 256; if workers fail with "Too many open
files", check `ulimit -n` and raise it for that shell.

## Device, locale and time-zone emulation

`emulation` in a settings file or profile (it lands in `settings.extra`) makes every browser context Testence
creates look like the given device and place:

```json
{
  "profiles": {
    "mobile-berlin": {
      "emulation": {
        "device": "iPhone 13",
        "locale": "de-DE",
        "timezone_id": "Europe/Berlin",
        "geolocation": {"latitude": 52.52, "longitude": 13.405},
        "permissions": ["clipboard-read"],
        "color_scheme": "dark"
      }
    }
  }
}
```

`device` is one of Playwright's device descriptors (viewport, user agent, scale factor,
touch, mobile); the other keys, `user_agent` among them, override it. A geolocation is granted along with its
position. Unknown keys, an unknown device (the error lists close names) and malformed
values fail before a browser starts. Emulation applies to launched and persistent
browsers, not to an attached one, whose owner decides. The run fingerprint records it,
so results are compared only with runs that emulated the same. `viewport` still
sets the page size and wins over the device's.

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

### Redaction and screenshot masks

Evidence is redacted before it is written. Field names are matched by their parts, so
`authToken`, `session_token`, `X-Api-Key`, `csrfToken`, `pwd` and `dbPassword` are all
treated as credentials, while `passage`, `author` or `pinned` are not. Values that are
secrets by their shape — JWTs, common provider token prefixes, payment card numbers —
are removed wherever they appear, and so are sensitive URL parameters such as an OAuth
`code`, `session` or `sig`. A record that names its field in data, such as an oracle diff
`{"field": "authToken", "ui": …}` or a header `{"name": "Authorization", "value": …}`,
has its value redacted as well.

Projects extend these rules in `testence.json`:

```json
{
  "evidence": {
    "redact": {
      "keys": ["tenant_ref"],
      "allow_keys": ["session_status"],
      "url_params": ["ticket"],
      "env": ["SHOP_API_TOKEN"],
      "auto_env": true,
      "pii": ["email", "phone"]
    },
    "screenshots": "on-failure",
    "mask": [
      {"kind": "testid", "value": "card-number"},
      {"kind": "role", "value": "textbox", "name": "Passport"}
    ]
  }
}
```

- `keys` adds field names or name parts; `allow_keys` exempts a field that the rules
  would otherwise hide.
- `url_params` adds query parameter names.
- `env` names environment variables whose values are replaced wherever they appear, in
  addition to the login and password variables. The values are never written.
- `auto_env` (default `true`) also masks, without listing them, the values of
  environment variables (the process environment and `.env` files) whose names contain
  `TOKEN`, `SECRET`, `PASSWORD`, `PASSWD`, `API_KEY`, `PRIVATE_KEY` or `CREDENTIAL`, in any
  case. A value shorter than 8 characters, a boolean word (`true`, `off`, `none`…) and a
  number are skipped, so `TOKENIZERS_PARALLELISM=false` stays readable. The rule only adds
  values: a variable named in `env` is masked whatever it holds. `testence doctor` lists the
  names it matched (never the values). `"auto_env": false` switches the rule off.
- `pii` opts into email and phone redaction. They are off by default because tests often
  assert the signed-in user's email.
- `screenshots`: `on-failure` (default) keeps a screenshot in the failure pack;
  `always` also captures the passing page for reports (needs
  `capture_policy.screenshots`).
- `mask` paints the listed elements black in every screenshot, including visual
  baselines. A baseline records its masks, so changing them makes the baseline an
  incompatible profile rather than a pixel verdict.

A secret that Testence knows is masked in every spelling a test id or a traceback can
carry it in: as is, URL-encoded, JSON- and `repr`-escaped, and as pytest escapes a
parameter id (`é`, `к`). A parameter id such as `test_login[<redacted>]` is only
what is shown. The case, the variant, the Allure `historyId` and the last-green
fingerprints are computed from the original value, so history does not split when a
value is masked. Give credentials `ids=` anyway: Testence cannot mask a secret it does
not know.

Attachments of a test (`ex.attach`, `allure.attach`) in three formats are also masked by
structure, before the text rules run on the result. In **HTML**, the `value` of
`password` and `hidden` inputs, of one-time-code and password-autocomplete inputs and of
inputs and textareas named like a secret, and the `content` of a `csrf-token` meta tag. In
**XML**, the text and attributes of an element whose name is a secret name (and of
everything inside it), an attribute with a secret name, and the `value` of an element
that names a secret in `name`/`key`. In **CSV** and **TSV**, the cells of a column whose
header is a secret name. Everything else in the file is kept, so it still parses and
diffs; a document that is not well-formed, or declares entities, gets the text rules only.

The ledger records the policy (names only) in `run.start`. `testence export` and
`testence report` apply it again, so a run written before a rule existed does not leave
in clear text. Invalid settings stop the session before any test runs.

### Playwright trace and video

```json
{"evidence": {"trace": "retain-on-failure", "video": "retain-on-failure"}}
```

`off` (default), `on` or `retain-on-failure` for each. A kept trace is the test's
`trace.zip`, opened with `npx playwright show-trace`; a kept video is `video-1.webm`
per page. Both are listed on `test.end` as `recordings`.

**They are not redacted.** A trace holds DOM snapshots, network traffic and
screenshots exactly as the page showed them, a video holds the pixels; redaction and
`evidence.mask` do not reach inside either. Enable them where the data a test touches
may be kept, and note each file is marked `redaction: none`. Only
`testence export --attachments raw` ships them; the default export and the live Allure
stream do not. They need a context Testence owns, so
an attached browser or a persistent profile refuses them.

### Element fingerprints

```json
{"evidence": {"fingerprints": "once"}}
```

`every-green` (default): after every green step with a target the element's
fingerprint is taken and stored in `.testence/fingerprints.json`, so a heal proposal
and the repair skill compare a failure with the last green run. `once`: a step whose
store already holds the fingerprint for the same target skips that browser call; a
changed target is taken again. That saves one round trip per step on every green
replay, and the baseline becomes the first green run of the step and target.

### Ledger durability

```json
{"evidence": {"durability": "test"}}
```

Every event is flushed when it is written, so a killed process keeps the ledger.
`durability` decides when it is also synced to disk (`fsync`), which only a machine
crash needs: `test` (default) at the end of each test, on any failure or error event,
when a failure pack binds the ledger and at close; `step` after every event, the
earlier behaviour, at a few milliseconds per event on Windows. See
[evidence schema](evidence-schema.md).

## Negative controls

A control names one way to break the target and the claims it makes false. A test
that stays green with the control active cannot detect the defect its claim is about
([ADR-0033](adr/0033-negative-proof.md)).

```json
{
  "controls": {
    "drop-save": {
      "description": "The API answers the save but stores nothing",
      "claims": ["widgets.create.persisted"]
    }
  }
}
```

`testence run --control drop-save` (pytest `--testence-control drop-save`) activates
one control for the whole run and records it in `run.start`. Testence does not break
anything itself: the test reads the `testence_control` fixture and applies the
control, for example with `ex.rewrite_response`, a seed variant or a flag on a
synthetic target. An undeclared name and `--testence-reruns` with a control are
usage errors. A run made with a control never proves product behaviour, and
`ci evaluate` refuses it as the run under evaluation.

## Sharing a page within a module

```json
{"page_reuse": "module"}
```

`test` (default): every test gets a fresh context and logs in. `module`: a test hands its
tab and context to the next test pytest runs when that test is in the same module,
logs in the same way (the configured scheme, or anonymous) and is not marked
`@pytest.mark.testence(fresh_page=True)`. The next test takes the page over with its
other tabs closed and its network, console and wait buffers cleared; its `auth` phase
reuses the login (`reused: true`). Each test's evidence and `test.waits` stay its own.

A page is not handed on after a failure, after `ex.route`, a fake clock, a WebSocket
gate, a response rewrite or `ex.native`, with trace or video on, in warm or attached
mode, or when the next test does not share module and login; a `page not kept` note
says why. Cookies, storage and the current document are shared: a test that reads
state another test may leave clears it with `ex.reset_storage(["key", ...])`, or opts
out with `fresh_page=True`. See [ADR-0038](adr/0038-page-reuse-within-a-module.md).

## Running in parallel

```bash
pip install testence[parallel]
pytest tests_e2e/ -q -n 4
```

Optional on purpose — a suite whose fixtures are not shard-safe must not acquire
workers by accident. Before adding `-n`, check the four invariants in
[ADR-0012](adr/0012-parallel-execution.md): one claim per case, one ledger per
process, per-worker seed namespaces, and per-worker offsets for anything
machine-wide (the debug port is ephemeral by default; an explicit `debug_port` becomes
`debug_port + N`). Measure serial and parallel runs on
your own target before selecting a default worker count.

Those invariants make workers safe for each other's files and ports, not for each
other's data on a shared server. Which tests may share one target is decided per
test from what its serial run read and wrote, and proven with repeated parallel runs
and an adversarial neighbour ([ADR-0034](adr/0034-parallel-safety-on-a-shared-target.md)).
Agents follow the procedure in the author skill's `references/parallel-safety.md`.

### Slowest tests first

```bash
pytest tests_e2e/ -q -n 4 --testence-schedule longest-first
```

xdist hands tests out in collection order, so a slow test collected last becomes the
tail of the run. `longest-first` (or `TESTENCE_SCHEDULE=longest-first`) has the
controller read the `test.end` durations of the 20 most recent runs under `runs_root`
(the median of each test's last five, repeated attempts excluded) and every worker
order its collection by them. The unit is a module: modules go longest first by their
total, and the tests of a module keep their order and stay together, so module
fixtures and `page_reuse: module` keep working. The tests of one `xdist_group` are a
unit of their own (under `--dist loadgroup` xdist keeps that order). A test without
history counts as the median test. Without history nothing changes; other `--dist`
modes are refused. Under `--dist load` xdist still hands a module's tests out in
chunks, so a long module can be split between workers as before.
