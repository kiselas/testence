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
| None | `none` | публичное приложение |

Аутентификация имеет scope сессии. Измеряйте form и API-session на собственном
приложении: основную стоимость определяют сеть и identity provider.

## Использование в тестах

Работу выполняет plugin; тест только запрашивает нужные fixtures:

```python
def test_widget_matches_api(ex, testence_api):
    ex.goto("/widgets/42", intent="open the widget")
    ui = {"cidr": ex.engine.read_text(CIDR_FIELD)}
    api = testence_api.get("/api/v1/widgets/42").raise_for_status().json
    verify(ex.writer, "widget", ui, api)      # oracle: UI vs API
```

Fixtures: `testence_settings` — итоговая конфигурация, `testence_auth` —
`AuthContext` со scope сессии, `testence_api` — `ApiClient` в этой сессии, `ex` —
DSL.

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

## Создание новой стратегии

Реализуйте `scheme: str` и `authenticate(engine) -> AuthContext`; операция должна
быть идемпотентной — повторная аутентификация уже вошедшего engine не должна падать.
Затем добавьте стратегию в `from_settings` и `_KNOWN_SCHEMES`, чтобы валидация
конфигурации оставалась честной: неизвестный механизм должен сообщить об опечатке, а
не о «недостающих credentials».

Проверьте стратегию на `tests/mock_app.py`, поддерживающем session cookies, bearer
tokens и Basic. Так встроенные стратегии проверяются при каждом commit без внешнего
приложения и реальных credentials.
