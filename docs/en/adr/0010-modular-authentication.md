# ADR-0010: Modular authentication, with form login as the default

Status: accepted (2026-08-25)

## Context

Applications use session cookies, bearer tokens, HTTP Basic, browser storage and
external identity providers. API oracles must observe the same authenticated identity
as the UI, while credentials and target URLs must remain outside test code.

## Decision

An `AuthAdapter` produces a scheme-neutral `AuthContext` containing cookies, headers,
storage and non-secret identity metadata. The browser, API client, oracles and seed
adapters consume that context without depending on the authentication mechanism.

| strategy | use |
|---|---|
| `FormLoginAuth` | default; exercises the login UI |
| `ApiSessionAuth` | obtains a browser session through an API login |
| `BearerTokenAuth` | token APIs with an optional storage mirror |
| `BasicAuth` | HTTP Basic targets |
| `AttachedSessionAuth` | reuses a browser session the user established |
| `NoAuth` | public targets |

Configuration resolves from a settings file, ignored environment files, process
environment and explicit flags. Credentials never belong in a tracked settings file.

`Credentials.__repr__`, `AuthContext.describe()` and `Settings.describe()` redact
secret values by construction. TLS configuration is shared by browser and API paths;
a named private CA is preferred to disabling verification.

## Consequences

Project-specific login screens override semantic targets or add a new adapter instead
of leaking selectors into core. The current mock server verifies cookie, bearer and
Basic flows without any external account.

OIDC/SAML redirects, MFA, passkeys and device authorization are not bundled yet.

## Tripwire

When an application cannot be authenticated by a bundled strategy, add a reusable
adapter and confirm that `AuthContext` still represents everything downstream needs.
