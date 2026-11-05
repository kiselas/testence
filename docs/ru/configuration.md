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
`token_storage_key`, `success_url_contains`, `api_auth_from_storage` —
[аутентификация](auth.md#spa-с-токеном-в-хранилище-браузера).

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

Профиль сливается с базовым файлом по таблицам: в нём указывают только отличия, а
названная в нём таблица сохраняет остальные ключи базы. Пустая таблица (`{}`) ничего не
меняет; чтобы заменить ключ, задайте ему другое значение.

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
profile. Браузер следует тому же правилу: заголовки Bearer и Basic добавляются только к
запросам на эти origin и никогда — к CDN, аналитике или хостингу шрифтов, с которых
грузится страница. Для browser cookies дополнительно соблюдаются domain, path, secure и
expiry.

`ApiClient` держит соединения открытыми: одно на origin, поэтому вызовы теста идут по
одному TCP- и TLS-соединению, которое закрывается в конце теста. Перед использованием
простаивавшее соединение проверяется: закрытое сервером в простое отбрасывается, и
запрос идёт по новому соединению. Соединение, оборвавшееся во время запроса,
повторяется один раз на новом соединении только для идемпотентного метода (GET, HEAD,
OPTIONS, PUT, DELETE); POST и PATCH никогда не отправляются дважды за спиной теста —
вызов падает, потому что приложение могло их применить. Соединение, которое не
открылось или оборвалось, даёт `urllib.error.URLError`, как раньше; вызов без ответа за
отведённое время — `TimeoutError`. Redirect следуют правилам urllib (GET и HEAD
следуют, POST с ответом 301–303 продолжается как GET без тела, остальное возвращается)
и не покидают origin. Proxy берутся из окружения или системных настроек при каждом
запросе, как у urllib.

## Необязательный session cache

Переиспользование session выключено, пока profile не задаёт identity probe.
Минимальная конфигурация cache называет probe и конечный TTL:

```json
{
  "session_probe_path": "/api/v1/auth/me",
  "session_cache_ttl_s": 900,
  "session_identity_field": "user.email",
  "session_id_field": "user.id"
}
```

Probe должен вернуть JSON object с настроенной identity (`session_identity_field`,
по умолчанию `email`; путь через точку читает вложенное поле). Identity — это значение
плюс, если названы, `session_id_field` и `session_role_field`: другой id или role за тем
же account — другая identity. Role не обязательна. Чтобы закрепить её, добавьте
`"session_expected_role": "qa-admin"`: проверка действует, только если задана, читает
`role`, если `session_role_field` не называет другое поле, и probe без этого поля тогда
никогда не переиспользуется. Названный id field, которого нет в ответе probe, — тоже
промах. Перед каждым reuse Testence требует HTTP 2xx, совпадение account (и role, если
она ожидается), ту же identity, что при записи в cache, и непросроченную запись cache.
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
| `TESTENCE_SCHEDULE` | `default` или `longest-first`: порядок тестов под pytest-xdist по прошлым длительностям (`--testence-schedule`, [параллельный запуск](#сначала-самые-долгие-тесты)) |
| `TESTENCE_RERUNS` | повторить упавший тест до N раз, 0–5 (`--testence-reruns`); записывается каждая попытка ([отчётность](reporting.md#повторы-и-нестабильные-тесты)) |
| `TESTENCE_ALLURE_RESULTS` | потоковая запись результатов Allure в этот каталог по мере окончания тестов (`--testence-allure-results`) |
| `TESTENCE_FULL_TRACE` | `1` оставляет в трассировке падения кадры Testence и Playwright ниже теста (`--testence-full-trace`; то же делает `--full-trace` pytest) |
| `TESTENCE_EMPTY_TESTPLAN` | `fail` по умолчанию или явный `noop`; CLI-эквивалент — `--testence-empty-testplan=noop` |

### Когда сессия pytest записывает запуск

Plugin загружается в каждую сессию pytest окружения, где установлен пакет, но каталог
запуска пишет только сессия Testence:

- её запустил CLI `testence` (`run`, `watch`, `ci`), который задаёт имя запуска;
- в командной строке есть опция `--testence-*` — так записывают весь набор, с тестами
  Testence и без, для загрузки в Allure или TestOps;
- собранный тест использует фикстуру Testence (`ex`, `testence_*`) или маркер
  `@pytest.mark.testence`. Тогда записывается вся сессия, включая остальные тесты.

Сессия без этих признаков ничего не пишет, и неверный `testence.json` её не
останавливает. Если неверные настройки встречает сессия Testence, pytest завершается
ошибкой использования (код 4) с именем настройки. Фикстура Testence, запрошенная только
через `request.getfixturevalue()` в сессии, которая иначе ничего не записывает, даёт
ошибку с объяснением: объявите фикстуру в сигнатуре теста.

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

- `keys` добавляет имена полей или их части; `allow_keys` освобождает поле, которое
  правила иначе скрыли бы.
- `url_params` добавляет имена параметров запроса.
- `env` перечисляет переменные окружения, значения которых заменяются везде, где
  встречаются, — в дополнение к переменным логина и пароля. Сами значения не пишутся.
- `auto_env` (по умолчанию `true`) без перечисления маскирует ещё и значения переменных
  окружения (из процесса и из файлов `.env`), в чьих именах есть `TOKEN`, `SECRET`,
  `PASSWORD`, `PASSWD`, `API_KEY`, `PRIVATE_KEY` или `CREDENTIAL`, в любом регистре.
  Значения короче 8 символов, булевы слова (`true`, `off`, `none`…) и числа пропускаются,
  поэтому `TOKENIZERS_PARALLELISM=false` остаётся читаемым. Правило только добавляет
  значения: переменная из `env` маскируется при любом значении. `testence doctor`
  перечисляет подошедшие имена (значения не выводит). `"auto_env": false` отключает правило.
- `pii` включает маскировку email и телефонов. По умолчанию она выключена: тесты часто
  проверяют email вошедшего пользователя.
- `screenshots`: `on-failure` (по умолчанию) оставляет скриншот в pack падения;
  `always` снимает и страницу прошедшего теста для отчётов (нужен
  `capture_policy.screenshots`).
- `mask` закрашивает перечисленные элементы чёрным на каждом скриншоте, включая
  визуальные эталоны. Эталон записывает свои маски, поэтому их смена делает эталон
  несовместимым профилем, а не пиксельным вердиктом.

Известный Testence секрет маскируется во всех написаниях, в которых его может нести id
теста или трассировка: как есть, в URL-кодировке, в экранировании JSON и `repr`, и так, как
pytest экранирует id параметра (`é`, `к`). Id вида `test_login[<redacted>]` — только
то, что показывается. Кейс, вариант, `historyId` Allure и отпечатки последнего зелёного
прогона считаются по исходному значению, поэтому история не расходится из-за маскирования.
Для учётных данных всё равно задавайте `ids=`: секрет, которого Testence не знает, он
замаскировать не может.

Вложения теста (`ex.attach`, `allure.attach`) трёх форматов маскируются ещё и по структуре,
до текстовых правил, которые затем идут по результату. В **HTML** — `value` полей
`password` и `hidden`, полей с автозаполнением одноразового кода и пароля и полей и
textarea с секретным именем, а также `content` мета-тега `csrf-token`. В **XML** — текст и
атрибуты элемента с секретным именем (и всего внутри него), атрибут с секретным именем и
`value` элемента, который называет секрет в `name`/`key`. В **CSV** и **TSV** — ячейки
столбца с секретным заголовком. Остальное в файле сохраняется, поэтому он по-прежнему
разбирается и сравнивается построчно; документ, не являющийся well-formed, или с объявлением
сущностей получает только текстовые правила.

Ledger записывает политику (только имена) в `run.start`. `testence export` и
`testence report` применяют её повторно, поэтому прогон, записанный до появления
правила, не уходит наружу в открытом виде. Неверные настройки останавливают сессию до
запуска тестов.

### Trace и видео Playwright

```json
{"evidence": {"trace": "retain-on-failure", "video": "retain-on-failure"}}
```

Для каждого: `off` (по умолчанию), `on` или `retain-on-failure`. Сохранённый trace —
`trace.zip` теста, открывается командой `npx playwright show-trace`; сохранённое видео
— `video-1.webm` на каждую страницу. Оба перечислены в `test.end` в поле `recordings`.

**Они не проходят маскировку.** В trace — снимки DOM, сетевой трафик и скриншоты
ровно такими, какими их показала страница, в видео — пиксели; редактирование и
`evidence.mask` внутрь не достают. Включайте их там, где данные, которых касается тест,
можно хранить; каждый файл помечен `redaction: none`. Отдаёт их только
`testence export --attachments raw`; экспорт по умолчанию и потоковая выгрузка в Allure —
нет. Им нужен контекст, которым владеет Testence,
поэтому attached-браузер и persistent-профиль от них отказываются.

### Отпечатки элементов

```json
{"evidence": {"fingerprints": "once"}}
```

`every-green` (по умолчанию): после каждого зелёного шага с target отпечаток элемента
снимается и сохраняется в `.testence/fingerprints.json`, поэтому heal proposal и скилл
repair сравнивают падение с последним зелёным прогоном. `once`: шаг, для которого store
уже хранит отпечаток того же target, не обращается к браузеру; изменённый target
снимается заново. Это экономит один round trip на шаг в каждом зелёном повторе, а
основой становится первый зелёный прогон шага и target.

### Долговечность журнала

```json
{"evidence": {"durability": "test"}}
```

Каждое событие сбрасывается при записи (flush), поэтому убитый процесс сохраняет
журнал. `durability` решает, когда журнал ещё и синхронизируется с диском (`fsync`),
что нужно только при падении машины: `test` (по умолчанию) — в конце каждого теста, на
любом событии с падением или ошибкой, когда failure pack привязывает журнал, и при
закрытии; `step` — после каждого события, как раньше, ценой нескольких миллисекунд на
событие на Windows. См. [схему доказательств](evidence-schema.md).

## Негативные контроли

Контроль описывает один способ сломать target и claim, которые от этого становятся
ложными. Тест, который остаётся зелёным при активном контроле, не способен заметить
дефект, о котором его claim ([ADR-0033](../en/adr/0033-negative-proof.md)).

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

`testence run --control drop-save` (в pytest `--testence-control drop-save`) включает
один контроль на весь прогон и записывает его в `run.start`. Сам Testence ничего не
ломает: тест читает фикстуру `testence_control` и применяет контроль, например через
`ex.rewrite_response`, вариант засева или флаг синтетического target. Необъявленное
имя и `--testence-reruns` вместе с контролем — ошибки использования. Прогон с
контролем никогда не доказывает поведение продукта, и `ci evaluate` не принимает его
как оцениваемый прогон.

## Одна вкладка на модуль

```json
{"page_reuse": "module"}
```

`test` (по умолчанию): каждый тест получает свежий context и входит заново. `module`:
тест передаёт свою вкладку и context следующему тесту, который запускает pytest, если
тот в том же модуле, входит так же (настроенная схема или anonymous) и не помечен
`@pytest.mark.testence(fresh_page=True)`. Следующий тест принимает страницу с закрытыми
остальными вкладками и очищенными буферами сети, консоли и ожиданий; его фаза `auth`
переиспользует вход (`reused: true`). Улики и `test.waits` каждого теста остаются его
собственными.

Страница не передаётся после падения, после `ex.route`, поддельных часов, шлюза
WebSocket, подмены ответа или `ex.native`, при включённых trace или видео, в warm- и
attached-режимах, а также если следующий тест не разделяет модуль и вход; заметка
`page not kept` объясняет причину. Cookies, storage и текущий документ общие: тест,
который читает состояние, оставленное другим тестом, очищает его через
`ex.reset_storage(["key", ...])` или отказывается от общей вкладки через
`fresh_page=True`. См. [ADR-0038](../en/adr/0038-page-reuse-within-a-module.md).

## Параллельный запуск

```bash
pip install testence[parallel]
pytest tests_e2e/ -q -n 4
```

Параллелизм намеренно необязателен: suite с shard-unsafe fixtures не должен случайно
получать workers. До добавления `-n` проверьте четыре инварианта из
[ADR-0012](adr/0012-parallel-execution.md): одно утверждение на сценарий, один ledger
на процесс, seed namespace на worker и worker-specific offsets для machine-wide
ресурсов (debug port по умолчанию эфемерный; явный `debug_port` превращается в
`debug_port + N`). Измерьте serial и parallel на своём target
до выбора количества workers по умолчанию.

Эти инварианты защищают workers друг от друга на уровне файлов и портов, но не данных
на общем сервере. Какие тесты могут идти на одном target одновременно, решается по
каждому тесту из того, что его serial-прогон прочитал и записал, и доказывается
повторными parallel-прогонами и враждебным соседом
([ADR-0034](../en/adr/0034-parallel-safety-on-a-shared-target.md)). Агент следует
процедуре из `references/parallel-safety.md` скилла author.

### Сначала самые долгие тесты

```bash
pytest tests_e2e/ -q -n 4 --testence-schedule longest-first
```

xdist раздаёт тесты в порядке сбора, поэтому долгий тест, собранный последним,
становится хвостом прогона. `longest-first` (или `TESTENCE_SCHEDULE=longest-first`)
заставляет controller прочитать длительности `test.end` из 20 последних прогонов в
`runs_root` (медиана последних пяти наблюдений каждого теста, повторные попытки не
учитываются), а каждый worker — упорядочить по ним свой сбор. Единица порядка —
модуль: модули идут от долгих к коротким по суммарной длительности, а тесты модуля
сохраняют свой порядок и остаются вместе, поэтому фикстуры уровня модуля и
`page_reuse: module` продолжают работать. Тесты одного `xdist_group` — отдельная
единица (при `--dist loadgroup` xdist сохраняет этот порядок). Тест без истории
считается медианным. Без истории ничего не меняется; другие режимы `--dist`
отклоняются. При `--dist load` xdist по-прежнему раздаёт тесты модуля порциями, поэтому
длинный модуль, как и раньше, может разойтись по разным workers.
