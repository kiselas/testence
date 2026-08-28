# Корпус бенчмарка

Benchmark запускает seeded behaviours на синтетическом приложении из `bench/sut/` и
механически оценивает результаты через собственный evidence ledger Testence.

## Текущий охват

Реализованный набор для экрана коллекции содержит одну исправную baseline, девять
поведенческих дефектов, один случай drift accessible name и шесть безвредных controls.
Авторитетный список и ожидаемые утверждения находятся в `bench/corpus/items.py`,
инъецируемое поведение — в `bench/sut/defects.json`.

Запуск:

```bash
python bench/corpus/run.py
python bench/corpus/run.py --repeats 3
python bench/corpus/run.py --only D-40-first-interaction-swallowed
```

Runner запускает синтетический target, выдаёт каждому item изолированное хранилище и
читает результаты отдельных утверждений из `run.jsonl`, а не сводит запуск к exit code
pytest-процесса.

## Метрики

| Метрика | Значение |
|---|---|
| `outcome_accuracy` | каждый item стал красным или остался зелёным согласно ожиданию |
| `false_green_rate` | seeded defects, избежавшие обнаружения |
| `false_red_rate` | безвредные controls, ошибочно отмеченные как падения |
| `right_reason_rate` | упало целевое утверждение, а не просто другой тест |
| `heal_recall` | drift cases, для которых создано предложение |
| `detection_by_stratum` | обнаружения по уровням обманчивости N/P/O/A |

Collateral failures остаются видимыми, но не засчитываются как обнаружение целевого
дефекта.

## Ограничения дизайна

- Нет повторов interaction: повтор может стереть сигнатуру дефекта.
- API-oracles используют то же seeded store и параметры, что UI.
- Параметр commit происходит одним явным путём, чтобы второй handler случайно не скрыл
  first-interaction defect.
- Controls включают структурные изменения и latency, поэтому suite не может зависеть
  от быстроты target или случайной DOM-разметки.
- Результаты частичного корпуса — smoke-floor evidence, а не доказательство широкого
  продуктового покрытия.

## Оставшиеся пробелы

Корпус пока не реализует multi-page workflows, две параллельные browser sessions,
долгие операции, file uploads/downloads, cross-origin flows, websockets, iframes,
mobile viewports и accessibility assertions. Эти пробелы нужно закрыть до применения
composite score для сравнения релизов или конкурентов.
