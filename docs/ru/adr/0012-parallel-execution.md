# ADR-0012: Параллельное исполнение process shards

Статус: accepted (2026-08-26)

## Контекст

Browser tests выигрывают от process parallelism, но общие evidence files, debug ports
и seed data делают наивный sharding небезопасным.

## Варианты

- Threads с Playwright sync API отклонены, потому что API не thread-safe.
- Один async browser с несколькими contexts отложен, потому что изменил бы публичную
  форму engine и DSL.
- Process shards pytest-xdist выбраны ради изоляции и совместимости.

## Решение

Parallelism является необязательным process sharding с четырьмя инвариантами:

1. Тест владеет своим предусловием и не зависит от output другого теста.
2. Каждый worker пишет свой ledger shard; readers объединяют shards по timestamp.
3. Seed markers включают worker id, cleanup не может удалить данные другого worker.
4. Machine-wide resources, включая CDP ports, получают worker-specific offsets.

`TESTENCE_RUN_ID` задаётся до запуска workers, поэтому все shards принадлежат одному
логическому run. Heal-memory files следуют тому же правилу sharding.

## Последствия

Каждый worker оплачивает browser и auth setup, получая изоляцию crash и state.
Последовательное исполнение поддерживается и остаётся default, потому что fixtures
приложения могут быть shard-unsafe. Reports и exporters читают объединённый ledger,
а не отдельные файлы.

## Tripwire

Async multi-context пересматривается, когда setup каждого worker начинает доминировать
во времени run. Потеря ledger event, удаление данных другого worker или рост
parallel false-red rate являются correctness defect и блокируют parallel execution.
