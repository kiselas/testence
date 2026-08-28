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

Authentication is session-scoped. Measure form and API-session strategies against
your own application; network topology and identity providers dominate the result.

## Using it in tests

The plugin does the work; a test just asks for what it needs:

```python
def test_widget_matches_api(ex, testence_api):
    ex.goto("/widgets/42", intent="open the widget")
    ui = {"cidr": ex.engine.read_text(CIDR_FIELD)}
    api = testence_api.get("/api/v1/widgets/42").raise_for_status().json
    verify(ex.writer, "widget", ui, api)      # oracle: UI vs API
```

Fixtures: `testence_settings` (resolved config), `testence_auth` (the `AuthContext`,
session-scoped), `testence_api` (`ApiClient` on that session), `ex` (the DSL).

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
