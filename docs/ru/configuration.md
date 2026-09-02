# Конфигурация

Данные окружения не должны находиться в тестовом коде. Адрес запуска, способ входа и
credentials берутся из конфигурации.

## Слои в порядке убывания приоритета

1. Явные flags: `pytest --testence-profile staging --testence-base-url ...`
2. Переменные процесса: `TESTENCE_*`
3. `.env.local`, затем `.env` в корне проекта; оба исключены из Git,
   `.env.local` имеет приоритет
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

Известные фреймворку keys: `base_url`, `api_prefix`, `auth`, `login_path`,
`api_login_path`, `cdp_url`, `browser_channel`, `headed`, `timeout_ms`, `verify_tls`, `ca_bundle`,
`runs_root`, `user_var`, `password_var`. Остальные попадают в `settings.extra`
и доступны стратегиям и адаптерам проекта, например `session_cookie`,
`token_storage_key`, `success_url_contains`.

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
| `TESTENCE_BROWSER_CHANNEL` | `chromium` по умолчанию — свежий браузер, поставляемый установленной версией Playwright; `chrome` включает системный Google Chrome |
| `TESTENCE_CDP_URL` | подключение к запущенному Chrome вместо нового |
| `TESTENCE_RUN_ID` | имя каталога запуска; plugin задаёт его общим для всех xdist workers ([ADR-0012](adr/0012-parallel-execution.md)) |

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
