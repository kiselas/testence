# Локальный Allure TestOps sandbox

Это подготовка настоящего Allure TestOps для интеграционного прогона.
Нужны trial-лицензия и registry credentials Qameta. Обычный Allure Report
не предоставляет tenant, selective launch или историю TestOps.

Официальный источник: [инструкция Qameta](https://docs.qameta.io/server/install/docker-compose/).
Запрос trial: [форма Qameta](https://qameta.io/server-trial-request).
Владелец запрашивает trial сам: форма требует контактные данные и согласие с условиями.
Лицензию вводить в локальном TestOps UI, credentials — через `docker login`;
не отправлять их в чат и не добавлять в Git.

## Подготовка

Из корня Testence в PowerShell:

```powershell
./infra/testops-sandbox/prepare.ps1
```

Скрипт использует официальный `qameta/testops-deploy-compose`, commit
`bc3f0c5c57773392112a4d46306f404dad7bd401` (Apache-2.0), и версию из его
demo-шаблона `25.3.2`. Если выданная лицензия требует другую версию,
перед первой подготовкой передать `-Version <выданная-версия>` и проверить
её compatibility с шаблоном. Образы фиксируются тегами; перед live acceptance
сохранить фактические image digests. Это ещё не receipt проверенного TestOps.

Все полученные файлы и случайно сгенерированные пароли остаются в
`.tmp/testops-sandbox/`, исключённом из Git. Повторная подготовка отказывается
перезаписывать `.env`. Официальный compose не меняется; отдельный overlay
изолирует имена контейнеров, снимает фиксированную подсеть и публикует только
loopback-порты. Mailpit принимает приглашение администратора локально,
без реального SMTP и внешней рассылки.

## Запуск после получения доступа

```powershell
# Ввести выданные Qameta credentials в интерактивном prompt.
docker login --username <registry-user>
Set-Location .tmp/testops-sandbox
docker compose -f docker-compose.yml -f compose.override.yaml pull
# Продолжать, только если pull завершился с exit 0.
docker compose -f docker-compose.yml -f compose.override.yaml up -d
docker compose -f docker-compose.yml -f compose.override.yaml ps
```

- TestOps: `http://localhost:18080`.
- Локальные приглашения: `http://localhost:18025`.
- Первый администратор: `admin@testence.local`. В Mailpit открыть приглашение,
  создать учётную запись, активировать trial-лицензию.
- Создать пустой проект `Testence sandbox` и отдельный automation token.
  Сохранить endpoint/project ID/token в локальном хранилище или environment;
  сообщить исполнителю только расположение/имена переменных.

Не выполнять `docker compose config` без `--quiet`: полный вывод содержит
подставленные пароли. Параметры `down -v` удаляют данные sandbox;
для обычной остановки использовать:

```powershell
docker compose -f docker-compose.yml -f compose.override.yaml stop
```

## Проверка интеграции

Проверяется код кандидата, а не опубликованный `0.1.0a1`: ставьте Testence из ветки
или из собранного wheel. Набор `check/` покрывает каждое поведение интеграции:
passed/failed/broken/skipped, параметризацию с секретом, метаданные `@allure.*`,
дерево сьютов, UI-падение с pack и скриншотом и имитацию убитого job.

### 0. Подготовка клиента

```powershell
# Отдельное окружение с кандидатом (путь к клону Testence — свой).
uv venv .tmp/testops-check-venv --python 3.12
uv pip install --python .tmp/testops-check-venv/Scripts/python.exe -e .
.tmp/testops-check-venv/Scripts/python.exe -m playwright install chromium
# allurectl: скачать бинарник под свою ОС со страницы релизов
# https://github.com/allure-framework/allurectl/releases и положить в PATH.
allurectl --version
```

В TestOps: создать проект, выпустить API-токен (профиль → API tokens) и запомнить
id проекта. Токен хранить в переменной окружения, не в файлах:

```powershell
$env:ALLURE_ENDPOINT = "http://localhost:18080"
$env:ALLURE_PROJECT_ID = "<id проекта>"
$env:ALLURE_TOKEN = "<токен>"          # ввести вручную, не сохранять в истории
$env:TESTENCE_BROWSER_CHANNEL = "msedge"   # если bundled Chromium не стартует
$py = (Resolve-Path .tmp/testops-check-venv/Scripts/python.exe).Path
Set-Location infra/testops-sandbox/check
```

### 1. Потоковая загрузка и карточка

```powershell
$env:TESTENCE_RUN_ID = "r-sandbox-1"
allurectl watch --results runs/r-sandbox-1/allure-results --launch-name "testence stream 1" -- `
  $py -m pytest -q --testence-allure-results runs/r-sandbox-1/allure-results
```

Ожидание (13 результатов, 3 failed/broken, 1 skipped — это задумано):

- результаты появляются в запуске по ходу прогона, а не в конце;
- `test_assertion_fails` и `test_ui_failure_has_a_pack` — **failed**,
  `test_code_error_is_broken` — **broken**, `test_skipped` — **skipped**;
- у упавших — полный трейс; у `test_ui_failure_has_a_pack` — вложения pack и
  скриншот, скриншот есть и на упавшем шаге;
- дерево: `test_sandbox` → `TestCart` для методов класса;
- тег только `smoke`, без `parametrize`/`slow`;
- `test_login`: два результата одного кейса, параметр `role` читаемый, `password`
  замаскирован;
- `test_decorated`: feature `Cart`, story `Pay by card`, severity `critical`, ссылка
  `PAY-7`, описание «Explicit description wins over the docstring.»;
- `test_documented`: описание из docstring.

### 2. История и отсутствие дублей

Повторить шаг 1 с `TESTENCE_RUN_ID = "r-sandbox-2"`. Ожидание: число тест-кейсов в
проекте не выросло, у каждого кейса история из двух результатов.

### 3. Миграция с allure-pytest

В отдельном проекте TestOps (или после очистки кейсов): сначала загрузить результаты
настоящего allure-pytest, затем Testence.

```powershell
uv pip install --python $py allure-pytest
$py -m pytest -q -p no:testence --alluredir ap-results
allurectl upload ap-results --launch-name "allure-pytest before"
$env:TESTENCE_RUN_ID = "r-sandbox-3"
$py -m pytest -q -p no:allure_pytest --testence-allure-results runs/r-sandbox-3/allure-results
allurectl upload runs/r-sandbox-3/allure-results --launch-name "testence after"
```

Ожидание: второй запуск лёг на те же тест-кейсы (новые не появились), история
непрерывна, метки из шага 1 на месте. Если allure-pytest не устанавливается без
изменения окружения — пропустить шаг и отметить это в квитанции.

### 4. Выбор тестов по плану

Из UI TestOps взять id кейса `test_login` и составить план с устаревшей записью:

```powershell
@'
{"version": "1.0", "tests": [
  {"id": "<id кейса test_login>"},
  {"selector": "test_sandbox#test_plain"},
  {"selector": "test_sandbox.py::test_renamed_last_week"}
]}
'@ | Set-Content -Encoding utf8 testplan.json
$env:ALLURE_TESTPLAN_PATH = (Resolve-Path testplan.json).Path
$env:TESTENCE_RUN_ID = "r-sandbox-4"
$py -m pytest -q --testence-allure-results runs/r-sandbox-4/allure-results
allurectl upload runs/r-sandbox-4/allure-results --launch-name "testence plan"
$py -m pytest -q --testence-testplan-unresolved=fail   # должно упасть до выполнения
Remove-Item Env:ALLURE_TESTPLAN_PATH
```

Ожидание: выполнены оба варианта `test_login` и `test_plain`; в выводе pytest —
предупреждение про `test_renamed_last_week`; в `environment.properties` запуска —
`testence.testplan_unresolved=1`; строгий режим завершился кодом 4.

Если в песочнице настроена CI-интеграция (GitLab/Jenkins), дополнительно запустить
job из TestOps по рецепту из [reporting](../../docs/ru/reporting.md) с
`allurectl job-run plan` и проверить то же на плане, собранном в UI.

### 5. Убитый job

```powershell
$env:TESTENCE_RUN_ID = "r-sandbox-5"
$env:SANDBOX_KILL = "1"
allurectl watch --results runs/r-sandbox-5/allure-results --launch-name "testence killed" -- `
  $py -m pytest -q --testence-allure-results runs/r-sandbox-5/allure-results
Remove-Item Env:SANDBOX_KILL
```

Ожидание: pytest завершился аварийно, в запуске 12 результатов — все, кроме
`test_killed_job`.

### 6. Квитанция

Сохранить в `release/evidence/` обезличенную квитанцию: SHA кандидата, версия
TestOps и `allurectl`, `docker compose images` (digest образов), номера запусков,
итог по каждому шагу 1–5 (совпало / нет, с кратким описанием расхождения). Токены,
адреса пользователей и содержимое результатов в квитанцию не попадают.

Готовые CLI-рецепты: [reporting](../../docs/ru/reporting.md).
