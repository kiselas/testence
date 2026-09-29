# Authentication

Decision record: [ADR-0010](adr/0010-modular-authentication.md). Configuration:
[configuration.md](configuration.md).

## The shape of it

Whatever the scheme, the **browser is authenticated first**, and everything else
inherits from the resulting `AuthContext`:

```
credentials (env)  ──►  AuthAdapter  ──►  AuthContext ──┬──► browser (already set up)
                                          cookies       ├──► ApiClient (oracles, seeding)
                                          headers       └──► evidence (names only)
                                          storage
```

That single-session rule is what makes API oracles meaningful: an oracle must read
the API as the same user the UI is logged in as, or its diff proves nothing.

## Choosing a strategy

| scheme | config value | use it when |
|---|---|---|
| Form login | `form` (default) | you want the login screen exercised every run; works whatever the app stores |
| API session | `api-session` | login has its own test; avoid repeating the UI login flow |
| Bearer / JWT | `bearer` (aliases `jwt`, `token`) | token APIs; add `token_storage_key` for SPAs that read it from `localStorage` |
| HTTP Basic | `basic` | APIs accepting Basic (Swagger-style) |
| Attached | `attached` | reuse a Chrome you already logged into; no credentials in play |
| Saved session | `storage-state` | a login you cannot script (SSO, second factor); [below](#a-login-you-cannot-repeat-a-saved-session) |
| Your own | `module:factory` | anything else: [your own login](#your-own-login) |
| None | `none` | public app |

Each test logs in once, in its own fresh browser context; `session_cache_ttl_s`
([configuration](configuration.md)) reuses a session between tests. Measure form and
API-session strategies against your own application; network topology and identity
providers dominate the result.

Bearer and Basic headers go only to `base_url` and the origins in
`api_allowed_origins`: a CDN, analytics or font host the page loads from never
receives the token or the password.

## Using it in tests

The plugin does the work; a test just asks for what it needs. `ex` is already
logged in with the configured scheme:

```python
def test_widget_matches_api(ex, testence_api):
    ex.goto("/widgets/42", intent="open the widget")
    shown = ex.engine.read_text(CIDR_FIELD)
    ex.verify_state(                                    # oracle: the API holds what the UI shows
        "widget",
        lambda: testence_api.get_fresh("/api/v1/widgets/42"),
        ExpectedState.fields("the API holds the CIDR on screen", {"cidr": shown}),
    )
```

Fixtures: `testence_settings` (resolved config), `testence_auth` (the test's
`AuthContext`), `testence_api` (`ApiClient` on that session), `ex` (the DSL, logged
in). A test of the login page itself, or of public pages, opts out:

```python
@pytest.mark.testence(anonymous=True)
def test_login_rejects_a_wrong_password(ex): ...
```

## Several users in one test

Permissions and "another user sees my change" need more than one session. Declare the
extra users by role, with the names of the variables that hold their credentials:

```json
{
  "auth": "form",
  "users": {
    "admin":  {"user_var": "ADMIN_USER",  "password_var": "ADMIN_PASSWORD"},
    "viewer": {"user_var": "VIEWER_USER", "password_var": "VIEWER_PASSWORD"}
  }
}
```

`testence_actor(role)` logs the role in with the configured `auth` scheme and returns
an actor with its own `auth`, `api` (an `ApiClient` on that session) and `ex` (the DSL on
a browser context of its own; steps are recorded in the running test). The main `ex` and
`testence_api` stay the user from `TESTENCE_USER`.

```python
def test_a_viewer_cannot_delete(testence_api, testence_actor):
    viewer = testence_actor("viewer")
    widget = testence_api.post("/api/widgets", {"name": "n"}).raise_for_status().json
    assert viewer.api.delete(f"/api/widgets/{widget['id']}").status == 403


def test_the_viewer_sees_what_the_admin_saved(ex, testence_actor):
    viewer = testence_actor("viewer")
    ex.goto("/widgets")                       # the configured user
    viewer.ex.goto("/widgets")                # the viewer, in a browser context of its own
```

Schemes without a page (`api-session`, `bearer`, `basic`) log an actor in without a
browser, and `.ex` opens one on first use; a `form` login needs the page. Every role's
credentials are redacted from evidence. An undeclared role names the declared ones. The
failure pack describes the main browser only.

## Single-page apps that keep a token in storage

A SPA that logs in through `fetch` and keeps its JWT or OIDC token in `localStorage`
adds it to its own API calls; the browser holds no cookie. The oracle's `ApiClient`
then reads as nobody, and every check is `inconclusive` on HTTP 401. Name where the
token is, and the API client sends it after login:

```json
{
  "auth": "form",
  "login_path": "/login",
  "success_url_contains": "/app",
  "api_auth_from_storage": {"key": "auth", "field": "access_token"}
}
```

`storage` is `local` (default) or `session`; `field` is a dot path into a JSON value;
`header` and `format` default to `Authorization` and `Bearer {token}`. The header goes
to the API client only, never to the browser, and the token is masked in evidence like
a configured secret. A key or field that is missing after login fails the login and
lists what the storage does hold.

`testence doctor --target` reaches `base_url`, checks that the credentials are set and
tries the login once, so a wrong URL, a missing variable or a wrong password is one
line with its fix rather than a timeout in the first test.

## Project-specific forms

Default selectors are conventional (`input[type=email]`, `input[type=password]`,
`button[type=submit]`) and hold up on real SPAs with no test ids. When they do not,
build the adapter explicitly instead of contorting the app:

```python
FormLoginAuth(
    settings.credentials(),
    login_path="/signin",
    username_target=Target("label", "Work email"),
    password_target=Target("testid", "password-input"),
    submit_target=Target("role", "button", name="Continue"),
    success_target=Target("testid", "user-menu"),   # explicit success signal
)
```

Without an explicit success signal the strategy waits for the password field to
disappear — so a wrong password fails *at the login step* with a readable error
rather than as a mysterious timeout three steps later.

## Your own login

A strategy is an object with `scheme: str` and `authenticate(engine) -> AuthContext`
(the `AuthAdapter` protocol); it must be idempotent, authenticating an already
authenticated engine must not fail. Point `auth` at a factory in your project, with no
change to Testence:

```json
{"auth": "tests.login:build"}
```

```python
# tests/login.py
from testence.auth import AuthContext


class CompanySso:
    scheme = "company-sso"

    def __init__(self, settings):
        self.credentials = settings.credentials()

    def authenticate(self, engine) -> AuthContext:
        ...  # drive the SSO, then hand the browser and the API client the session
        return AuthContext(cookies=engine.cookies(), scheme=self.scheme)


def build(settings):
    return CompanySso(settings)
```

`module:factory` names `factory(settings) -> AuthAdapter` (a dotted attribute such as
`pkg.auth:Login.build` works too). The project's root is importable, so nothing needs
packaging. A typo names itself: an unimportable module, a missing attribute, or a factory
that returns something else is a readable error. `testence doctor --target` runs the
login; it does not look for `TESTENCE_USER` and `TESTENCE_PASSWORD`, because a custom
login decides what it needs.

### A login you cannot repeat: a saved session

An SSO with a second factor cannot be scripted. Sign in once by hand, save Playwright's
storage state, and start every test from it:

```json
{"auth": "storage-state", "storage_state": "auth.json"}
```

Cookies and the `localStorage` of `base_url`'s origin are imported. Let Testence make the
file: `testence auth export -o auth.json` logs in with the `auth` you configured (a form,
an API session, your own `module:factory`), and saves the session owner-only; it will not
replace an existing file without `--force`. `context.storage_state("https://app.example")`
produces the same document from Python.
The file holds a live session and expires with it: keep it out of version control.

### One account, many workers

Every test logs in on its own, so `pytest -n 8` with one account is eight simultaneous
sessions. Most apps allow that; one that ends the previous session on a new login makes
tests fail at random. Then share one session (`session_probe_path` reuses it between
tests and workers, see [configuration](configuration.md)), start from a saved state, or
give each worker its own account.

