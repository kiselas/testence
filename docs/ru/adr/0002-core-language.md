# ADR-0002: Python для ядра фреймворка

Статус: accepted (2026-08-25)

## Контекст

Python и TypeScript имеют зрелые Playwright clients. У TypeScript есть first-party
Playwright test runner и agent tooling; у Python — экосистема pytest fixtures,
parametrization и plugins. Python client общается с процессом Playwright driver,
поэтому решение должно учитывать измеримый IPC overhead.

## Эксперимент E1

`bench/e1_python.py` и `bench/node/e1_node.mjs` выполняют одинаковые семь действий
на одной синтетической странице в 30 итерациях. Сохранённый snapshot:

| Метрика | Node | Python | Разница |
|---|---:|---:|---:|
| instant-step p50 | 9,43 мс | 10,28 мс | +9,0% |
| async assertion p50 | 310,32 мс | 311,70 мс | +0,4% |
| browser launch | 1664 мс | 1753 мс | +5,3% |

Критерий принятия: p50 overhead Python ниже 15%. Snapshot удовлетворяет условию, но
зависит от hardware и versions и должен оставаться воспроизводимым, а не считаться
универсальным утверждением.

## Решение

Использовать Python 3.10+, pytest и synchronous Playwright API. Тела тестов остаются
линейными; parallelism обеспечивают изолированные процессы согласно ADR-0012.
Контракты evidence и configuration остаются нейтральными к языку.

## Последствия

Node-only инструменты Playwright являются integrations, а не in-process APIs. Проекты
на других языках могут читать CLI и JSONL artifacts; будущий port runner переиспользует
контракты.

## Tripwire

Повторять E1 для значимых обновлений Playwright. Пересмотреть решение, если p50 overhead
Python достигнет 15% на поддерживаемом benchmark либо execution-critical возможность
останется только в TypeScript API.
