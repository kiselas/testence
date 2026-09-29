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

## Writing a new strategy

Implement `scheme: str` and `authenticate(engine) -> AuthContext`; be idempotent
(authenticating an already-authenticated engine must not fail). Then add it to
`from_settings` and to `_KNOWN_SCHEMES` so config validation stays honest — an
unknown scheme must report the typo, not "missing credentials".

Verify it against `tests/mock_app.py`, which speaks session cookies, bearer tokens
and Basic; that is how the bundled strategies are tested on every commit, with no
external application and no real credentials.
