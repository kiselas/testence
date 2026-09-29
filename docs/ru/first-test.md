# Первый тест

Десять минут, ваше приложение, без файла плана. PlanSpec нужен, чтобы отслеживать
утверждения в команде ([тестирование фичи](testing-a-feature.md)); чтобы тест
запустился, упал с evidence или что-то доказал, он не нужен.

## 1. Укажите Testence приложение

```bash
pip install testence
python -m playwright install chromium   # или Chrome/Edge: TESTENCE_BROWSER_CHANNEL=chrome|msedge
```

Создайте `testence.json` рядом с тестами (`auth` — `none` для публичного приложения; вход
описан в [аутентификации](auth.md)):

```json
{"base_url": "http://localhost:3000", "auth": "none"}
```

Затем `testence doctor --target` обращается к `base_url`, проверяет учётные данные и один раз
пробует войти: неверный URL или пароль — одна строка, а не таймаут.

## 2. Напишите один тест

`ex` — это браузер, уже вошедший в систему. Элементы называйте по роли и доступному
имени; в `intent` скажите, зачем шаг: именно это показывает отчёт.

```python
from testence.engine import Target


def test_home_page_greets(ex):
    ex.goto("/", intent="open the home page")
    ex.expect_visible(Target("role", "heading", name="Welcome"), intent="see the greeting")
    ex.click(Target("role", "button", name="Go"), intent="press Go")
```

## 3. Запустите и прочитайте результат

```bash
testence run --project . -- test_smoke.py -q
testence inspect runs/<the run id it printed>
```

Каждый запуск пишет `runs/<id>/`. Упавший тест оставляет evidence pack (как выглядела
страница, API-трафик, консоль, предложенное исправление устаревшего селектора).
`testence report runs/<id>` собирает его в один HTML-файл.

Успешный запуск пишет `assurance: 1 unverified`. Это не предупреждение: тест выполнен и
прошёл, но не сказано, какое утверждение он доказывает. Добавьте одну проверку, что API
согласен с экраном, и он станет `verified`; четыре состояния описаны в глоссарии.

## 4. Докажите сохранение, а не только экран

UI может написать «сохранено» поверх записи, которой не было. Спросите у запуска, что
отправляло приложение:

```bash
testence oracle suggest runs/<run id>
```

Для каждой мутации теста команда покажет чтение API, которое её доказывает, и вызов
`save_and_verify_state`, который осталось дописать
([тестирование фичи](testing-a-feature.md)). Для id и имён полей нужен
`"capture_policy": {"network_bodies": true}` в приложении с синтетическими данными.

## Дальше

- Несколько пользователей, права: `testence_actor` ([аутентификация](auth.md)).
- Состояния ошибки и пустые списки: `ex.route` ([тестирование фичи](testing-a-feature.md)).
- Утверждения и планы, когда они нужны команде: [тестирование фичи](testing-a-feature.md).
- Слова из отчётов: [глоссарий](glossary.md).
