# ADR-0011: Self-healing как проверяемое предложение, но не runtime rebind

Статус: accepted (2026-08-25) — измерено на failure corpus

## Контекст

Locators меняются: кнопку переименовывают, label поля обновляют, component переписывают.
Кто-то должен заметить и обновить тест. Индустрия называет ответ self-healing, но под
этим именем скрываются две очень разные формы:

1. **Runtime rebinding**: при падении найти похожий элемент и использовать его, чтобы
   run стал зелёным.
2. **Proposal**: записать прежний вид элемента, назвать лучшего кандидата и передать
   человеку или агенту diff для принятия.

Первая форма выглядит магически и именно поэтому опасна: framework, который «исцелился»
вокруг **удалённой** кнопки, показывает green при сломанной функции. Серьёзные tools,
включая Healenium, mabl и testRigor, показывают healed locators для подтверждения, а не
поглощают их скрыто.

## Решение

Heal является **motion**: framework предлагает, reviewer принимает, принятое изменение
живёт в Git как обычная правка test code. Runtime rebinding отсутствует, как и flag для
его включения.

Механика:

- Каждый green step записывает multi-attribute fingerprint затронутого элемента по
  ключу `(test id, step intent)`. Ключом служит intent, а не locator, потому что
  именно locator меняется. Хранилище — JSON в репозитории
  `.testence/fingerprints.json`, пригодный для review и diff.
- При падении шага с target страница сканируется на addressable elements, каждый
  оценивается относительно fingerprint через `kernels.score_candidates`, а результат
  записывается в evidence pack как `heal.json`: score, runner-up, rationale и готовый
  `suggested_edit`.
- **Порог — главный смысл.** Ниже `MIN_SCORE = 0.6` verdict hint равен `real_bug`,
  адрес не предлагается: элемент исчез, а не переместился.
- Сохранившийся test id немедленно даёт perfect score. Это не один из signals: человек
  поставил его как указание на точный смысл теста, поэтому он сильнее изменившихся tag,
  role и text.
- Два кандидата внутри `AMBIGUOUS_MARGIN` помечаются `ambiguous`: proposer выбирает
  winner, но reviewer видит близость результата.

## Измерения на корпусе

9 items, `corpus/run.py`:

| Метрика | Значение |
|---|---:|
| `heal_recall` — drift с proposal | 1.0 |
| `heal_precision` — proposal с приемлемым address | 1.0 |
| `disappearance_discrimination` — отказ healing удалённых элементов | 1.0 |
| `false_green_rate` / `false_red_rate` | 0.0 / 0.0 |

Для этого пришлось исправить три дефекта, найденных корпусом, но не unit tests:
несогласованное вычисление fingerprints в двух местах, scoring weights в пользу
атрибутов, которые как раз меняются, и loose substring matching, скрывший реальный
drift. Подробности в `corpus/README.md`.

## Последствия

- Качество healing измеряется и защищено regression tests, а не демонстрацией.
- Proposal является evidence, но не authority: `TRIAGE.md` требует проверить
  `heal.json`, потому что уверенное неверное предложение хуже его отсутствия.
- Первый запуск не имеет baseline и proposal. Это корректно: догадка без baseline —
  шум. Поэтому corpus сначала выполняет green baseline; cold start измерял бы не тот
  эффект.

## Tripwire

`disappearance_discrimination` ниже 1.0 в любом corpus run блокирует release:
healing вокруг удалённого элемента дискредитирует возможность целиком. Если
`heal_precision` падает ниже 0.8, weights пересматриваются **на данных корпуса**, а
item, обнаруживший падение, добавляется в него.
