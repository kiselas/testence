# Киты компонентов

Экран, собранный из библиотеки компонентов, начинает каждый тест с одной и той же
работы: как открывается select, почему клик по флажку ничего не делает, когда боковая
панель закончила выезжать. Половина этого — свойства библиотеки, а не продукта. **Кит**
несёт эту половину один раз:

```python
from testence.kits import koobiq, react_select

koobiq.select(ex, "Mode").choose("Safe")
react_select.multi(ex, "Targets").pick("alpha.example.test", "delta.example.test")
panel = koobiq.side_panel(ex, "Edit router")
panel.wait_open()
panel.number_field("VLAN", hint="from 1 to 4094").set(42)
```

Каждая фабрика принимает `ex` и возвращает небольшой объект. Его `target` (и части —
`option()`, `row()`, `chip()`) — обычные `Target`, их можно передать в любой шаг `ex`;
его методы — обычные шаги `ex` с intent: они попадают в журнал шагов, падают с обычной
диагностикой и снимают отпечаток, как шаги, написанные руками. Кит не обращается к
браузерной библиотеке вне `ex.native`, не спит, не повторяет действие и не ослабляет
проверку: метод, которому надо ждать, ждёт условие (`expect_*` или предикат, который
движок проверяет на каждом кадре анимации).

Киты входят в Testence и не добавляют зависимостей.

| Модуль | Что покрывает |
| --- | --- |
| `testence.kits.react_aria` | роли и поведение, общие для дизайн-систем на react-aria |
| `testence.kits.koobiq` | [Koobiq](https://github.com/koobiq/react-components) (`@koobiq/react-components`) |
| `testence.kits.react_select` | `react-select` 5, одиночный и `isMulti` |
| `testence.kits.xyflow` | узлы `@xyflow/react` (React Flow 12) |

## Koobiq и react-aria

`koobiq.SUPPORTED` — `">=0.37,<1"`; `koobiq.VERIFIED` — версии, на которых прошёл
конформанс-стенд (0.37.0, 0.38.0; сверка с исходниками пакета 2026-11-04). Адрес
выбирается так: сначала роль и доступное имя, затем атрибуты `data-*` Koobiq
(`data-slot`, `data-transition`, `data-status`, `data-variant`), и только потом
**префикс** класса CSS-модуля (`kbq-dialog-header-`): Koobiq хеширует классы модулей,
и хвост меняется от версии к версии.

| Компонент | Адрес | Действия | Зашитая ловушка |
| --- | --- | --- | --- |
| `koobiq.select(ex, label)` | кнопка — через `data-slot="form-field"` с этой подписью; список — `role=listbox` с именем подписи | `open`, `choose(value)`, `expect_value(value)`, `option(label)` | Имя кнопки — «подпись значение», и та же подпись называет открытый список: пока он открыт, одна подпись находит два элемента. Значение проверяется по имени кнопки. |
| `koobiq.text_field(ex, label, required=, hint=)` | `role=textbox` с точным составным именем | `fill`, `expect_value` | Обязательное поле называется `Name *`; подсказка в подписи входит в имя (`VLAN from 1 to 4094`). Имя составляется точно, не ищется подстрокой. |
| `koobiq.number_field(...)`, `react_aria.number_field(ex, label)` | `role=textbox` | `set(value, shown=)`, `expect_value` | `onChange` срабатывает при уходе фокуса, не при вводе: `set` заполняет и жмёт Tab, затем проверяет показанное значение. |
| `koobiq.checkbox(ex, label)`, `koobiq.switch(ex, label)` | состояние — `role=checkbox` / `role=switch`; клик — по тексту подписи | `check`, `uncheck`, `toggle`, `expect_checked` | `<input>` обрезан до пикселя внутри `<label>`: клик или `check` по нему ждут проверку попадания, которую выигрывает label. `check` отказывается от уже отмеченного флажка, а не снимает его. |
| `koobiq.table(ex, name)`, `react_aria.table(ex, name)` | `role=grid`; строки — `role=row` с именем заголовка строки | `row`, `rowheader`, `cell`, `rows`, `select_row`, `unselect_row`, `expect_selected`, `expect_rows`, `row_menu(row, trigger)` | Флажки строк названы переводимым словом («Select router-one», «Выбрать router-one»): флажок строки — её первый label с флажком. Выделение читается по `aria-selected` строки. |
| `koobiq.menu(ex, trigger)`, `react_aria.menu(ex, trigger)` | кнопка `role=button`; меню `role=menu` с именем кнопки | `open`, `choose(item, closes=True)`, `item(label)` | Меню рисуется порталом в конце `<body>`: `within=` кнопки его не находит. |
| `koobiq.tabs(ex, name)` | `role=tablist`, `role=tab`, `role=tabpanel` с именем вкладки | `select(label)`, `tab`, `panel` | Выбор проверяется по `aria-selected` и панели, а не самим кликом. |
| `koobiq.tooltip(ex, trigger)` | `role=tooltip` | `open`, `expect_text` | react-aria открывает подсказку по наведению только после того, как `pointermove` выставил модальность «pointer»; первое движение мыши в тесте входит в кнопку раньше, и одиночный hover ничего не открывает. `open` сначала уводит курсор в угол страницы (один шаг `ex.native`). |
| `koobiq.search(ex, label)` | `role=searchbox` | `submit(text)` | Поиск отправляется только по Enter; ввод сам ничего не отправляет. |
| `koobiq.dialog(ex, title)`, `koobiq.side_panel(ex, title)` | `role=dialog`, у которого элемент `kbq-dialog-header-` читается как заголовок (XPath) | `wait_open`, `wait_closed`, `close`, `press(name)`, `button`, `field`, `number_field` | У диалогов Koobiq нет доступного имени (шапка — не heading). Оверлеи анимируются 300 мс и остаются в DOM, пока уходят: `wait_open` ждёт `data-transition="entered"`, закрытие ждёт исчезновения элемента. Имя крестика переводится — он находится по структуре. |
| `koobiq.confirm(ex, title)` | диалог с этим заголовком | `accept(action)`, `cancel(name="Cancel")` | Кнопка применения несёт глагол («Delete», «Publish»); диалог с другим заголовком не подходит. |
| `koobiq.toasts(ex)` | `role=alertdialog` с именем заголовка; подпись — по `aria-describedby` | `read`, `mark`, `expect_new(mark, title, status=)`, `expect_no_new(mark, within_ms=)`; у `Toast` — `expect_caption`, `dismiss` | Заголовки повторяются: тост засчитывается, только если появился после `mark()`, а уходящий — никогда. `ToastProvider` — сама область тостов, детей не рендерит. Отрицание (`expect_no_new`) по построению тратит весь бюджет. |
| `koobiq.badge(ex, text)` | элемент `kbq-badge-` с `data-variant` и этим текстом | `read`, `expect_variant`, `expect_color` | Цвет, который продукт задал в inline-стиле (`style.color`), читается и ожидается в нормализованном браузером виде `rgb(r, g, b)`. |
| `koobiq.tag_group(ex, name)` | `role=grid`, теги — `role=row` | `tag`, `remove(label)`, `expect_tags(count)` | Экспортируемый `Tag` — элемент группы и в одиночку ничего не рендерит; имя крестика переводится. |
| `react_aria.listbox(ex, name)` | `role=listbox`, `role=option` | `option`, `expect_selected` | Список select называется по подписи поля, а не по кнопке. |

## react-select

`react_select.single(ex, label)` и `react_select.multi(ex, label)` находят поле по его
input-комбобоксу: `aria-label`, `aria-labelledby` или `<label for>` с именем `label`,
либо `input_id=`, если продукт задаёт `inputId`. Классы `<prefix>__…` есть, только если
продукт задал `classNamePrefix`; если префикс не `react-select`, передайте `prefix=`.

| Часть | Адрес | Действия | Зашитая ловушка |
| --- | --- | --- | --- |
| поле | `input` (`role=combobox`), `control`, `menu` | `open`, `close`, `expect_open`, `wait_loaded`, `search(text)` | Escape внутри диалога закрывает и диалог: `close` уводит фокус (react-select закрывает меню на blur). `search` заполняет поле и никогда не жмёт Backspace, который в пустом поле снимает последний чип. |
| варианты | `option(label)` внутри меню | `pick(*labels, keep_open=)` | Мультиселект может закрываться после каждого выбора (`closeMenuOnSelect`); `pick` открывает меню заново, только если оно закрылось, и проверяет чип или значение. |
| чипы | `chip(label)`, `chip_remove(label)` (`[role=button]` в чипе) | `remove(label)`, `expect_chips([...])`, `clear()` | Крестик по умолчанию — «Remove <label>», в дизайн-системах часто переименован («Delete»); он ищется внутри чипа, а не по имени. |
| состояние | один evaluate | `state()`: чипы, значение, плейсхолдер, open, loading, варианты (label, group, selected, disabled, focused), группы, notice, `unoffered` | Сохранённое значение, которого больше нет среди вариантов, всё равно рисует чип: `unoffered` перечисляет такие чипы. |

## React Flow

`xyflow.node(ex, node_id, kind=)` адресует `.react-flow__node-<kind>[data-id=<id>]`.
Узел рисуется с `visibility: hidden`, пока не измерен, поэтому каждое действие сначала
ждёт, что узел виден. `click` выделяет (`expect_selected`), `open` делает двойной клик
через `ex.native` (в DSL двойного клика нет), `menu()` и `action(label)` используют кнопку
узла с `aria-haspopup` или кнопку по имени. `xyflow.nodes(kind)` считает узлы.

## Разведка узнаёт компоненты

`testence explore` и MCP-инструмент `testence_snapshot` добавляют рядом с `elements`
список `components`. Каждая запись называет компонент, строку кита и нужный импорт:

```json
{"kind": "koobiq.select", "name": "Mode", "required": false,
 "python": "koobiq.select(ex, \"Mode\")", "import": "from testence.kits import koobiq"}
```

Узнаются: поля react-select (с `prefix=` или `input_id=`, где нужно), select Koobiq,
числовые, поисковые и обязательные или с подсказкой текстовые поля, флажки и
переключатели со скрытым input, диалоги и боковые панели (с их `transition`), тосты (с
заголовками), таблицы и группы тегов, вкладки, открытые меню и списки, узлы React Flow.
Имена проходят политику редактирования проекта, как и весь снимок. Распознавание —
подсказка для написания теста, одним evaluate; о продукте оно ничего не доказывает.

## Конформанс

`bench/sut/koobiq` — страница на настоящих `@koobiq/react-components`, `react-select` и
`@xyflow/react` точных версий: по экземпляру каждого компонента выше, каждый пишет, что
сделал, в журнал событий. Сборка закоммичена (`dist/`), поэтому `uv run pytest -q` гоняет
`tests/test_kits_*.py` против неё без Node; тест падает, если сборка старше исходников.
Кейсы, зависящие от локали, идут на английском и на русском. `bench/kits_latency.py`
замеряет каждый метод кита на стенде ([снимок](../../bench/results/kits_latency.json),
[бюджет](../../bench/budgets/kits_latency.json)); большая часть времени метода Koobiq —
собственная 300-мс анимация компонента.

Как проверить новую версию Koobiq — в [README стенда](../../bench/sut/koobiq/README.md).

## Проектный адаптер

Кит заканчивается там, где заканчивается то, что рисует библиотека. Остальное — дело
проекта, в тонком модуле-адаптере, который собирает объекты кита со знанием продукта:

- **Роуты и экраны**: какой URL открывает список, какой параметр открывает панель
  записи, что значит «экран готов» для этого продукта.
- **Имена**: заголовки панелей и подтверждений, пункты меню, подписи и подсказки полей
  на языках, которые продукт поддерживает.
- **Собственные обёртки продукта**: ручка изменения ширины панели, изменение ширины
  колонок таблицы, форма поиска продукта, а не библиотеки. Это не библиотека — их
  адресует адаптер.
- **Данные**: сид, который создаёт нужное кейсу, оракул, который читает результат из
  API, и уборка, которая это удаляет. Кит никогда не проверяет состояние сервера.

```python
# проектный адаптер: routers.py
from testence.kits import koobiq

def open_router(ex, router):
    ex.navigate(f"/routers?panel={router['id']}", intent=f"open {router['name']}")
    panel = koobiq.side_panel(ex, "Edit router")
    panel.wait_open()
    return panel
```

Тест читается как намерение продукта, адаптер знает продукт, кит знает компоненты, и
никто из троих не переучивает ловушки других.
