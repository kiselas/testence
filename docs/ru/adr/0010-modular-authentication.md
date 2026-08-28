# ADR-0010: Модульная аутентификация с form login по умолчанию

Статус: accepted (2026-08-25)

## Контекст

Приложения используют session cookies, bearer tokens, HTTP Basic, browser storage и
external identity providers. API-oracles должны наблюдать ту же authenticated identity,
что UI, а credentials и target URLs должны оставаться вне тестового кода.

## Решение

`AuthAdapter` создаёт scheme-neutral `AuthContext`, содержащий cookies, headers,
storage и несекретные identity metadata. Browser, API client, oracles и seed adapters
читают этот context без зависимости от механизма аутентификации.

| Стратегия | Применение |
|---|---|
| `FormLoginAuth` | default; проверяет UI входа |
| `ApiSessionAuth` | получает browser session через API login |
| `BearerTokenAuth` | token APIs с необязательным mirror в storage |
| `BasicAuth` | targets с HTTP Basic |
| `AttachedSessionAuth` | переиспользует browser session пользователя |
| `NoAuth` | публичные targets |

Configuration разрешается из settings file, ignored environment files, process
environment и explicit flags. Credentials никогда не находятся в tracked settings.

`Credentials.__repr__`, `AuthContext.describe()` и `Settings.describe()`
редактируют secrets по конструкции. TLS configuration общая для browser и API;
предпочтителен named private CA, а не отключение verification.

## Последствия

Project-specific login screens переопределяют semantic targets или добавляют новый
adapter, но не протаскивают selectors в core. Текущий mock server проверяет cookie,
bearer и Basic flows без внешнего account.

OIDC/SAML redirects, MFA, passkeys и device authorization пока не поставляются.

## Tripwire

Если приложение нельзя аутентифицировать встроенной стратегией, нужно добавить
переиспользуемый adapter и подтвердить, что `AuthContext` по-прежнему представляет
всё необходимое downstream.
