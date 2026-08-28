# ADR-0004: ARIA snapshot как DOM-формат доказательств

Статус: proposed — default до решения эксперимента E2 ablation

## Контекст

«Записать состояние страницы» требует конкретного формата. Он должен помещаться в
evidence pack до 8K tokens, поддерживать diff между шагами и нести достаточно структуры
для вердикта без скриншотов. Урок ручных запусков: «читать текст, а не смотреть
картинки» — текст лучше pixels для triage агентом.

## Варианты для E2 на failure corpus

| | ARIA snapshot | CDP DOMSnapshot | dump `innerText` | screenshot |
|---|---|---|---|---|
| Размер | small–medium, только semantic tree | большой: layout boxes и styles | минимальный, только text | максимальный |
| Структура | roles, names, states — что может пользователь | полная, но шумная | нет roles/states | только visual |
| Diff | YAML, line diff | JSON с шумными diffs | line diff | нет |
| Стабильность | высокая, semantic | низкая из-за layout jitter | средняя | низкая |
| Стоимость | один Python API call | один CDP call | один eval | 0,1–30 с |

## Решение до E2

Использовать ARIA snapshot как `aria.txt` в pack и источник per-step snapshots.
Screenshots создавать только при падении и для людей; агенты начинают с текста.
Заранее зарегистрированный критерий E2: ARIA остаётся, если `verdict_accuracy` не
ниже альтернатив при стоимости tokens не более 50% от них. E3 сравнит between-step
diffs с полными snapshots: принять при сокращении tokens не менее 60% и потере accuracy
не более 2 percentage points.

## Последствия

- Rich-canvas areas недостаточно представлены в ARIA; ActionMap должен читать canvas
  state через app-level API oracle или DOM queries, что и является правильным слоем.
- Опция `box` с bounding boxes доступна, если verdict требует geometry, но её
  стоимость измеряется и она не включена по умолчанию.

## Tripwire

Не менее трёх ошибок verdict в корпусе, вызванных отсутствием visual/geometry
информации, требуют повторить E2 со screenshot и вариантами `box`.
