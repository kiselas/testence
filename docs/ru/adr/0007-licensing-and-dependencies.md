# ADR-0007: Apache-2.0 и permissive policy runtime dependencies

Статус: accepted (2026-08-25)

## Контекст

Testence предназначен для публичного применения и расширения. Правила лицензии и
dependencies должны быть явными до появления первой истории репозитория.

## Решение

- Лицензия проекта: Apache-2.0.
- Runtime dependencies обязаны использовать permissive licenses: MIT, Apache, BSD или
  PSF.
- Runner не должен требовать hosted service, SDK model provider или telemetry.
- Development tools по возможности остаются permissive.
- CI до релиза проверяет лицензии dependencies и запрещённые imports.

## Последствия

Core работает offline и нейтрален к model provider. Интеграции со своими SDK должны
поставляться отдельными packages и регистрироваться через версионированную точку
расширения.

## Tripwire

Если необходимая возможность доступна только по несовместимой лицензии или как
обязательный hosted service, до её добавления нужно записать новое решение с конкретной
возможностью и влиянием на distribution.
