# ADR-0020: Явный application CLI с manifests

Статус: accepted (2026-09-06)

## Контекст

Библиотека предоставляла низкоуровневые pytest и contract helpers, но onboarding и
agent clients были вынуждены угадывать paths, выбирать latest run или напрямую
копировать файлы. Такие shortcuts делают identity запуска неоднозначной, а update или
submit verdict — непроверяемой filesystem mutation.

## Рассмотренные варианты

Сравнивались shell recipes, интерактивный wizard и небольшие application services за
стабильными CLI-командами. Shell recipes различаются на Windows/Linux и не создают
единый contract. Wizard трудно воспроизвести и проверить агентом.

## Решение

Стабильная application surface:

- `testence doctor --root <project> --json` проверяет Python, settings, packaged schemas,
  Chromium и workspace без вывода credentials;
- `testence init <project> --json` создаёт только отсутствующие scaffold-файлы и
  связывает точные bytes в `testence/scaffold-manifest/1`; conflict даёт ошибку;
- `testence run --project <project> --run-id <id> -- [pytest args]` выполняет явный
  scope, а без pytest arguments запускает только hidden synthetic proof;
- `testence inspect <run-dir> --json` требует явный каталог запуска и показывает
  reconciled execution, assurance и integrity;
- `testence verdict submit <candidate> --plan <plan> --pack <pack> --json` проверяет
  bindings, атомарно записывает `verdict.json` и создаёт
  `testence/verdict-submission/1`. Другой существующий verdict не перезаписывается.

Machine JSON пишется в stdout, пользовательские ошибки возвращают exit 2 без traceback.
`init` не меняет pytest configuration и не добавляет hidden example в test paths.

## Последствия

Команды одинаковы для wheel на Windows и Linux, а agent clients могут проверять
manifests до изменения файлов. Каждая операция явно называет project, run, plan или
pack; latest lookup отсутствует. Установка и обновление Agent Skills остаются отдельным
manifest-backed слоем.

## Tripwire

Решение пересматривается, если два независимых agent clients не способны пройти один
wheel-only workflow или scaffold update нельзя выразить как reviewable manifest diff
без перезаписи пользовательских изменений.
