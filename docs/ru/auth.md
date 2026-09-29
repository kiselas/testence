# Аутентификация

Архитектурное решение: [ADR-0010](adr/0010-modular-authentication.md). Настройка:
[configuration.md](configuration.md).

## Общая схема

Независимо от механизма сначала **аутентифицируется браузер**, после чего все остальные
компоненты наследуют полученный `AuthContext`:

```
credentials (env)  ──►  AuthAdapter  ──►  AuthContext ──┬──► browser (уже настроен)
                                          cookies       ├──► ApiClient (oracles, seeding)
                                          headers       └──► evidence (только имена)
                                          storage
```

Правило единой сессии делает API-oracles осмысленными: oracle должен читать API от
имени того же пользователя, под которым UI вошёл в систему, иначе diff ничего не
доказывает.

## Выбор стратегии

| Механизм | Значение config | Когда использовать |
|---|---|---|
| Form login | `form` (по умолчанию) | экран входа должен проверяться в каждом запуске; работает независимо от способа хранения сессии |
| API session | `api-session` | login уже имеет отдельный тест; не нужно повторять UI-flow входа |
| Bearer / JWT | `bearer` (aliases `jwt`, `token`) | token APIs; добавьте `token_storage_key` для SPA, читающего token из `localStorage` |
| HTTP Basic | `basic` | API с Basic-аутентификацией, например Swagger |
| Attached | `attached` | переиспользование Chrome, в который уже вошёл пользователь; credentials не нужны |
| Сохранённая сессия | `storage-state` | вход, который нельзя автоматизировать (SSO, второй фактор) |
| Свой | `module:factory` | всё остальное: [собственный вход](#собственный-вход) |
| None | `none` | публичное приложение |

Каждый тест входит один раз, в собственном свежем контексте браузера;
`session_cache_ttl_s` ([конфигурация](configuration.md)) переиспользует сессию между
тестами. Измеряйте form и API-session на собственном приложении: основную стоимость
определяют сеть и identity provider.

Заголовки Bearer и Basic уходят только на `base_url` и origin из
`api_allowed_origins`: CDN, аналитика или хостинг шрифтов, с которых грузится
страница, не получают ни токен, ни пароль.

## Использование в тестах

Работу выполняет plugin; тест только запрашивает нужные fixtures. `ex` уже вошёл
по настроенной схеме:

```python
def test_widget_matches_api(ex, testence_api):
    ex.goto("/widgets/42", intent="open the widget")
    shown = ex.engine.read_text(CIDR_FIELD)
    ex.verify_state(                                    # oracle: API хранит то, что в UI
        "widget",
        lambda: testence_api.get_fresh("/api/v1/widgets/42"),
        ExpectedState.fields("the API holds the CIDR on screen", {"cidr": shown}),
    )
```

Fixtures: `testence_settings` — итоговая конфигурация, `testence_auth` —
`AuthContext` теста, `testence_api` — `ApiClient` в этой сессии, `ex` — DSL, уже
вошедший. Тест самой страницы входа или публичных страниц от входа отказывается:

```python
@pytest.mark.testence(anonymous=True)
def test_login_rejects_a_wrong_password(ex): ...
```

## Несколько пользователей в одном тесте

Права доступа и «другой пользователь видит мою правку» требуют больше одной сессии.
Объявите дополнительных пользователей по ролям, указав имена переменных с их данными:

```json
{
  "auth": "form",
  "users": {
    "admin":  {"user_var": "ADMIN_USER",  "password_var": "ADMIN_PASSWORD"},
    "viewer": {"user_var": "VIEWER_USER", "password_var": "VIEWER_PASSWORD"}
  }
}
```

`testence_actor(role)` входит под ролью схемой `auth` из настроек и возвращает актора со
своими `auth`, `api` (`ApiClient` на этой сессии) и `ex` (DSL в собственном контексте
браузера; шаги записываются в выполняющийся тест). Основные `ex` и `testence_api` остаются
пользователем из `TESTENCE_USER`.

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

Схемы без страницы (`api-session`, `bearer`, `basic`) входят без браузера, а `.ex`
открывает его при первом обращении; вход через `form` требует страницу. Данные каждой
роли маскируются в evidence. Необъявленная роль называет объявленные. Failure pack
описывает только основной браузер.

## SPA с токеном в хранилище браузера

SPA, который входит через `fetch` и хранит JWT или OIDC-токен в `localStorage`, сам
добавляет его к своим API-запросам; cookie у браузера нет. Тогда `ApiClient` oracle
читает как аноним, и каждая проверка даёт `inconclusive` на HTTP 401. Укажите, где лежит
токен, и после входа API-клиент будет его отправлять:

```json
{
  "auth": "form",
  "login_path": "/login",
  "success_url_contains": "/app",
  "api_auth_from_storage": {"key": "auth", "field": "access_token"}
}
```

`storage` — `local` (по умолчанию) или `session`; `field` — путь через точку внутри
JSON-значения; `header` и `format` по умолчанию `Authorization` и `Bearer {token}`.
Заголовок получает только API-клиент, не браузер, а токен маскируется в evidence как
заданный секрет. Если после входа нет ключа или поля, вход падает и перечисляет, что в
хранилище есть.

`testence doctor --target` обращается к `base_url`, проверяет, что учётные данные заданы,
и один раз пробует войти: неверный URL, отсутствующая переменная или неверный пароль —
одна строка с исправлением, а не таймаут в первом тесте.

## Специфичные формы проекта

Селекторы по умолчанию используют общепринятые адреса: `input[type=email]`,
`input[type=password]`, `button[type=submit]`. Они работают во многих SPA без test
ids. Если этого недостаточно, явно создайте адаптер вместо усложнения приложения:

```python
FormLoginAuth(
    settings.credentials(),
    login_path="/signin",
    username_target=Target("label", "Work email"),
    password_target=Target("testid", "password-input"),
    submit_target=Target("role", "button", name="Continue"),
    success_target=Target("testid", "user-menu"),   # явный сигнал успеха
)
```

Без явного сигнала успеха стратегия ждёт исчезновения поля пароля. Поэтому неверный
пароль приводит к понятной ошибке *на шаге login*, а не к загадочному timeout через
три шага.

## Собственный вход

Стратегия — объект с `scheme: str` и `authenticate(engine) -> AuthContext` (протокол
`AuthAdapter`); операция должна быть идемпотентной: повторная аутентификация уже
вошедшего engine не должна падать. Укажите в `auth` фабрику из вашего проекта, ничего
не меняя в Testence:

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

`module:factory` называет `factory(settings) -> AuthAdapter` (точечный атрибут вроде
`pkg.auth:Login.build` тоже работает). Корень проекта импортируется, упаковка не нужна.
Опечатка называет себя сама: модуль, который не импортируется, отсутствующий атрибут или
фабрика, вернувшая что-то другое, дают читаемую ошибку. `testence doctor --target`
выполняет вход, но не ищет `TESTENCE_USER` и `TESTENCE_PASSWORD`: собственный вход сам
решает, что ему нужно.

### Вход, который нельзя повторить: сохранённая сессия

SSO со вторым фактором нельзя автоматизировать. Войдите один раз вручную, сохраните
storage state Playwright и начинайте каждый тест с него:

```json
{"auth": "storage-state", "storage_state": "auth.json"}
```

Импортируются cookies и `localStorage` origin из `base_url`. Файл может сделать сам
Testence: `testence auth export -o auth.json` входит настроенной схемой `auth` (форма,
API-сессия, ваш `module:factory`) и сохраняет сессию с доступом только владельцу;
существующий файл без `--force` не заменяется. Тот же документ по Python даёт
`context.storage_state("https://app.example")`. Файл
содержит живую сессию и истекает вместе с ней: не храните его в системе контроля версий.

### Один аккаунт, много workers

Каждый тест входит сам, поэтому `pytest -n 8` с одним аккаунтом — восемь одновременных
сессий. Большинство приложений это допускает; то, что завершает прежнюю сессию при новом
входе, роняет тесты случайным образом. Тогда разделите одну сессию (`session_probe_path`
переиспользует её между тестами и workers, см. [конфигурацию](configuration.md)),
начинайте с сохранённого состояния или дайте каждому worker свой аккаунт.

