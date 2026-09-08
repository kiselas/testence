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

После активации исполнитель:

1. Фиксирует candidate SHA, wheel hash, версию TestOps/allurectl и image digests.
2. Загружает synthetic pass/fail/broken/skip и проверяет статусы/attachments в UI.
3. Создаёт планы для выборок 1/8 и 3/20; запускает через настоящий
   `ALLURE_TESTPLAN_PATH`, сверяет collected/executed/доставленные test IDs.
4. Повторяет run, проверяет history/retries и отсутствие лишних test cases.
5. Проверяет повторную delivery по тому же receipt; не выполняет blind retry
   после неоднозначного сетевого исхода.
6. Сохраняет обезличенные receipts. До этого TestOps live gate остаётся pending.

Готовые CLI-рецепты: [reporting](../../docs/ru/reporting.md).
