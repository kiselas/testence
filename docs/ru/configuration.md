# Конфигурация

Данные окружения не должны находиться в тестовом коде. Адрес запуска, способ входа и
credentials берутся из конфигурации.

## Слои в порядке убывания приоритета

1. Явные flags: `pytest --testence-profile staging --testence-base-url ...`
2. Переменные процесса: `TESTENCE_*`
3. `.env.local`, затем `.env` в корне проекта; оба исключены из Git,
   `.env.local` имеет приоритет
   Все переменные перечислены в [`.env.example`](../../.env.example). Сохраняйте их в UTF-8; метка порядка байтов (BOM) допустима.
4. Settings file: `testence.toml` для Python 3.11+ или `testence.json`
5. Встроенные значения по умолчанию

## Settings file и профили

Settings file хранится в репозитории проекта: он описывает **окружения**, но никогда
не секреты. Profiles превращают смену окружения в одно слово:

```bash
TESTENCE_PROFILE=staging pytest tests_e2e/
pytest tests_e2e/ --testence-profile local
```

Полный пример с профилями `local`, `staging`, `staging-attached` и `ci` находится
в [`testence.example.json`](../../testence.example.json). Неизвестное имя профиля сразу
приводит к ошибке со списком доступных профилей.

Известные фреймворку keys: `project_id`, `base_url`, `api_prefix`, `auth`, `login_path`,
`api_login_path`, `cdp_url`, `execution_mode`, `browser_channel`, `debug_port`, `headed`,
`timeout_ms`, `verify_tls`, `ca_bundle`,
`runs_root`, `user_var`, `password_var`. Остальные попадают в `settings.extra`
и доступны стратегиям и адаптерам проекта, например `session_cookie`,
`token_storage_key`, `success_url_contains`.

`project_id` — принадлежащий репозиторию namespace для ledger, packs, verdicts и
истории отчётов. Укажите его явно в `testence.json`; package name из `pyproject.toml`
служит только compatibility fallback для ещё не мигрировавших проектов.

По умолчанию `execution_mode` равен `isolated`. Каждый тест получает новый собственный
browser context, auth session и API client; принадлежащие runner процессы и порты
закрываются после pass, failure и interrupt. Режим `warm` сохраняет принадлежащий
runner процесс browser, но заменяет context перед каждым тестом. При `cdp_url`
автоматически выбирается `attached`: Testence заимствует context и никогда не закрывает
чужой browser. Warm и attached являются явными authoring-режимами, а не CI isolation.

В project seed fixtures используйте `testence_namespace` или строку
`testence_seed_marker`. Marker включает project, run, worker, case, role и attempt.
Свяжите его с `SeedLifecycle(owner=...)`: ошибка cleanup остаётся видимой, а reverse-order
и xdist runs не используют общий data namespace.

Два значения `extra`, которые читает сам engine:

| Key | Значение |
|---|---|
| `test_id_attribute` | DOM-атрибут, по которому разрешается `Target("testid", ...)` |
| `keep_animations` | `true` возвращает CSS entry animations, отключённые по умолчанию |

`test_id_attribute` — свойство **приложения**, а не фреймворка. Немногие приложения
поставляют `data-testid`, но многие имеют другой стабильный атрибут идентичности.
Настройка test-id selector на него не связывает публичный DSL со специфичными CSS или
XPath. Playwright также дёшево переоценивает плоское совпадение атрибута при
actionability checks.

`keep_animations` нужен для единственного случая, когда тест действительно проверяет
анимацию. Включённые анимации добавляют около 1 секунды на 14 UI-действий.

## Credentials

Credentials поступают только из окружения или `.env.local`:

```bash
TESTENCE_USER=user@example.com
TESTENCE_PASSWORD=...
```

Для multi-tenant поддерживаются имена переменных на уровне профиля: задайте `user_var`
и `password_var`, например `TESTENCE_STAGING_USER`, затем экспортируйте их.

Фреймворк относится к credentials как к радиоактивным данным: `Credentials` печатает
`***` в любом repr или traceback, `AuthContext.describe()` сообщает только имена
headers и cookies, а `Settings.describe()`, записываемый в `run.jsonl`, никогда не
содержит секрет. Найденное значение credential в evidence artifact — это баг.

`ApiClient` передаёт унаследованный Authorization header только на нормализованный
origin из `base_url` и из необязательного списка `api_allowed_origins`. Абсолютный URL
с другим host или port, переход с HTTPS на HTTP и redirect на другой origin завершаются
ошибкой до передачи credentials. Поэтому cross-origin API требует явной записи в
profile. Для browser cookies дополнительно соблюдаются domain, path, secure и expiry.

## Необязательный session cache

Переиспользование session выключено, пока profile не задаёт identity probe. Безопасная
конфигурация cache указывает ожидаемую role и конечный TTL:

```json
{
  "session_probe_path": "/api/v1/auth/me",
  "session_cache_ttl_s": 900,
  "session_identity_field": "email",
  "session_role_field": "role",
  "session_expected_role": "qa-admin"
}
```

Probe должен вернуть JSON object с настроенными identity и role. Перед каждым reuse
Testence требует HTTP 2xx, совпадение account и role и непросроченную запись cache.
Logout, повреждённый или старый формат cache, смена project, origin, account, profile,
role или auth strategy приводят к настоящему login. Имя cache file зависит от scope,
account хранится как hash, а файл получает доступ только владельцу там, где ОС
поддерживает этот режим. Cache следует держать в исключённом из Git `runs_root`.

## TLS с частным центром сертификации

Self-hosted тестовое окружение может использовать private CA, доверенный браузером
через system store, но отсутствующий в Python bundle. Тогда API-вызовы получают
`CERTIFICATE_VERIFY_FAILED`, хотя UI работает. В порядке предпочтения:

```bash
TESTENCE_CA_BUNDLE=/path/to/testing-root.pem    # лучше: проверка остаётся включённой
TESTENCE_VERIFY_TLS=false                        # только изолированные test environments
```

`verify_tls=false` также ослабляет browser context через `ignore_https_errors`,
поэтому UI и API видят одинаковое окружение.

## Runtime-настройки, не связанные с окружением

| Переменная | Значение |
|---|---|
| `TESTENCE_RUNS_ROOT` | каталог запусков, по умолчанию `runs/` |
| `TESTENCE_KERNELS` | `auto` \| `reference` \| `native` — compute backend ([kernels.md](kernels.md)) |
| `TESTENCE_BROWSER_CHANNEL` | `chromium` по умолчанию — свежий браузер, поставляемый установленной версией Playwright; `chrome` и `msedge` — системные браузеры, `chromium-headless-shell` — bundled сборка только для headless. Действует и для `Settings` и движков, созданных напрямую, без `Settings.load` |
| `TESTENCE_CDP_URL` | подключение к запущенному Chrome вместо нового |
| `TESTENCE_RUN_ID` | имя каталога запуска; plugin задаёт его общим для всех xdist workers ([ADR-0012](adr/0012-parallel-execution.md)) |
| `ALLURE_TESTPLAN_PATH` | стандартный selective plan Allure версии `1.0`; неверный план отклоняется, несовпавшие записи попадают в отчёт ([отчётность](reporting.md#выбор-тестов-по-плану-testops)) |
| `TESTENCE_TESTPLAN_UNRESOLVED` | `warn` (по умолчанию) или `fail` для записей плана без совпавшего теста |
| `TESTENCE_ALLURE_RESULTS` | потоковая запись результатов Allure в этот каталог по мере окончания тестов (`--testence-allure-results`) |
| `TESTENCE_EMPTY_TESTPLAN` | `fail` по умолчанию или явный `noop`; CLI-эквивалент — `--testence-empty-testplan=noop` |

Для повторяющегося agent-authoring loop один раз запустите и аутентифицируйте browser,
после чего подключайте к нему короткие pytest processes через attached profile:

```bash
python -m testence.dev_browser --profile staging
pytest tests_e2e/ -k current_case --testence-profile staging-attached
```

Persistent context принадлежит launcher'у. Attached pytest runs переиспользуют cookies,
storage и текущую page, сбрасывают capture buffers Testence на каждом test и отключаются,
не закрывая этот context. Это оптимизация повторных runs: одиночная команда всё равно
оплачивает старт launcher'а.

Добавляйте `--warm` к `testence watch` только во время authoring. Каждый каталог `-w`
становится границей module reload: импортированные из этих roots проектные модули
выгружаются перед следующей pytest session, а Testence остаётся загруженным. Для CI и
release evidence сохраняйте обычную subprocess isolation.

Warm mode также сохраняет Playwright/CDP engine между sessions. Engine key содержит все
settings browser connection: изменение любой из них закрывает старый client и создаёт
новый. Остановка warm runner освобождает сохранённый client.

`TESTENCE_RUN_ID` задаётся через `setdefault` в `pytest_configure` до запуска xdist
и наследуется workers. Устанавливайте его вручную только если внешнему инструменту
нужно писать в известный каталог. Два независимых параллельных запуска с одним
значением перемешают свои журналы.

После установки Python-пакета один раз установите соответствующий ему браузер:

```bash
python -m playwright install chromium
pytest examples/ -q --testence-headless
```

Флаг `--testence-browser-channel chrome` оставляет возможность регрессионного запуска
на системном Google Chrome. Обычный локальный и CI-путь использует bundled Chromium,
поэтому версия браузера согласована с версией Playwright и не зависит от состояния ПК.

Если на машине bundled `chrome.exe` не стартует вовсе (например, политика контроля
приложений Windows отвергает его приватную side-by-side сборку, тогда как
`chromium-headless-shell` той же ревизии и системный Edge запускаются), задайте для
этой машины `TESTENCE_BROWSER_CHANNEL=msedge` или `chromium-headless-shell`.
Переменная действует и на `Settings(...)` и движки, созданные напрямую, а не через
`Settings.load`, — в том числе на браузерные тесты самого репозитория; явный аргумент
`browser_channel=`
по-прежнему сильнее, а CI остаётся на bundled Chromium, потому что переменную не задаёт.

На macOS bundled Chromium не требует ничего, кроме `python -m playwright install
chromium`. Каналы `chrome` и `msedge` запускают приложения из `/Applications`, поэтому
доступны только там, где установлены Google Chrome или Microsoft Edge. Параллельный
прогон открывает сразу несколько браузеров, а оболочка macOS может стартовать с мягким
лимитом файловых дескрипторов всего в 256; если воркеры падают с «Too many open files»,
проверьте `ulimit -n` и поднимите лимит для этой оболочки.

## Эмуляция устройства, локали и часового пояса

`emulation` в settings file или профиле (попадает в `settings.extra`) делает каждый контекст браузера, который
создаёт Testence, похожим на заданное устройство и место:

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

`device` — один из дескрипторов устройств Playwright (viewport, user agent, масштаб,
touch, mobile); остальные ключи, в том числе `user_agent`, его переопределяют. Геолокация выдаётся вместе с
разрешением на неё. Неизвестные ключи, неизвестное устройство (ошибка перечисляет
похожие имена) и неверные значения отклоняются до запуска браузера. Эмуляция действует
для запускаемого и persistent-браузера, но не для attached: там решает его владелец.
Fingerprint прогона её записывает, поэтому результаты сравниваются только с прогонами
с той же эмуляцией. `viewport` по-прежнему задаёт размер страницы и сильнее
viewport устройства.

## Политика сбора evidence

Network bodies и screenshots отключены, пока проект явно их не разрешит. Текстовые
ARIA-данные, ограниченный console buffer и очищенные URL остаются доступны. Для среды
только с синтетическими данными каналы можно включить в `testence.json`:

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

Жёсткий предел body — 64 KiB. При недопущенном content type, неизвестном размере или
размере выше лимита Testence фиксирует omission и не просит Playwright материализовать
body. Screenshot управляется отдельно: text redaction не очищает пиксели.

### Маскировка секретов и маски скриншотов

Evidence маскируется до записи. Имена полей сопоставляются по частям, поэтому
`authToken`, `session_token`, `X-Api-Key`, `csrfToken`, `pwd` и `dbPassword` считаются
учётными данными, а `passage`, `author` или `pinned` — нет. Значения, которые выдают
себя формой, — JWT, распространённые префиксы токенов провайдеров, номера платёжных
карт — удаляются везде, где встречаются, как и чувствительные параметры URL: OAuth
`code`, `session`, `sig`. Если запись называет поле в данных, как oracle diff
`{"field": "authToken", "ui": …}` или заголовок `{"name": "Authorization", "value": …}`,
её значение тоже маскируется.

Проект расширяет эти правила в `testence.json`:

```json
{
  "evidence": {
    "redact": {
      "keys": ["tenant_ref"],
      "allow_keys": ["session_status"],
      "url_params": ["ticket"],
      "env": ["SHOP_API_TOKEN"],
      "pii": ["email", "phone"]
    },
    "mask": [
      {"kind": "testid", "value": "card-number"},
      {"kind": "role", "value": "textbox", "name": "Passport"}
    ]
  }
}
```

- `keys` добавляет имена полей или их части; `allow_keys` освобождает поле, которое
  правила иначе скрыли бы.
- `url_params` добавляет имена параметров запроса.
- `env` перечисляет переменные окружения, значения которых заменяются везде, где
  встречаются, — в дополнение к переменным логина и пароля. Сами значения не пишутся.
- `pii` включает маскировку email и телефонов. По умолчанию она выключена: тесты часто
  проверяют email вошедшего пользователя.
- `screenshots`: `on-failure` (по умолчанию) оставляет скриншот в pack падения;
  `always` снимает и страницу прошедшего теста для отчётов (нужен
  `capture_policy.screenshots`).
- `mask` закрашивает перечисленные элементы чёрным на каждом скриншоте, включая
  визуальные эталоны. Эталон записывает свои маски, поэтому их смена делает эталон
  несовместимым профилем, а не пиксельным вердиктом.

Ledger записывает политику (только имена) в `run.start`. `testence export` и
`testence report` применяют её повторно, поэтому прогон, записанный до появления
правила, не уходит наружу в открытом виде. Неверные настройки останавливают сессию до
запуска тестов.

## Параллельный запуск

```bash
pip install testence[parallel]
pytest tests_e2e/ -q -n 4
```

Параллелизм намеренно необязателен: suite с shard-unsafe fixtures не должен случайно
получать workers. До добавления `-n` проверьте четыре инварианта из
[ADR-0012](adr/0012-parallel-execution.md): одно утверждение на сценарий, один ledger
на процесс, seed namespace на worker и worker-specific offsets для machine-wide
ресурсов, включая debug port `9222 + N`. Измерьте serial и parallel на своём target
до выбора количества workers по умолчанию.
