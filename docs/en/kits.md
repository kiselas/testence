# Component kits

A screen built from a component library starts every test with the same work: find
how the select opens, why clicking the checkbox does nothing, when the side panel has
finished sliding in. Half of that is the library, not the product. A **kit** carries
the library half once:

```python
from testence.kits import koobiq, react_select

koobiq.select(ex, "Mode").choose("Safe")
react_select.multi(ex, "Targets").pick("alpha.example.test", "delta.example.test")
panel = koobiq.side_panel(ex, "Edit router")
panel.wait_open()
panel.number_field("VLAN", hint="from 1 to 4094").set(42)
```

Each factory takes `ex` and returns a small object. Its `target` (and sub-targets such
as `option()`, `row()`, `chip()`) are ordinary `Target` values you can pass to any `ex`
step; its methods are ordinary `ex` steps with an intent, so they appear in the ledger,
fail with the usual diagnostics and fingerprint like hand-written steps. A kit never
imports the browser library outside `ex.native`, never sleeps, never retries an
interaction and never relaxes a check: a method that must wait waits on a condition
(`expect_*` or a predicate the engine polls per animation frame).

Kits ship with Testence; they add no dependency.

| Module | Covers |
| --- | --- |
| `testence.kits.react_aria` | roles and behaviour shared by react-aria design systems |
| `testence.kits.koobiq` | [Koobiq](https://github.com/koobiq/react-components) (`@koobiq/react-components`) |
| `testence.kits.react_select` | `react-select` 5, single and `isMulti` |
| `testence.kits.xyflow` | `@xyflow/react` (React Flow 12) nodes |
| `testence.kits.codemirror` | CodeMirror 6 editors |

## Koobiq and react-aria

`koobiq.SUPPORTED` is `">=0.37,<0.39"`; `koobiq.VERIFIED` lists the releases the
conformance stand passed with: 0.37.0 is the committed build, 0.38.0 has a receipt in
`bench/sut/koobiq/receipts` (a separate build of the same stand sources, run at the
Playwright floor and on a current browser). A test fails when a claimed version has no
such evidence, or when the receipt predates the stand's current sources. Addresses prefer role and accessible name, then Koobiq's `data-*` attributes
(`data-slot`, `data-transition`, `data-status`, `data-variant`), and only then a CSS
module class **prefix** (`kbq-dialog-header-`): Koobiq hashes its module classes and
the suffix changes between releases.

| Component | Address | Actions | Trap the kit carries |
| --- | --- | --- | --- |
| `koobiq.select(ex, label, required=None)` | trigger through `data-slot="form-field"` with that label; list `role=listbox` named by the label | `open`, `choose(value)`, `expect_value(value)`, `option(label)` | The trigger's name is "label value", and the label also names the open list: the label alone matches two elements while the list is open. The value is checked through the trigger's name. A required field's list is named "label *": left out, `required` is read from the label once, on first use. |
| `koobiq.text_field(ex, label, required=, hint=)` | `role=textbox` with the exact composed name | `fill`, `expect_value` | A required field is named `Name *`; a hint in the label joins the name (`VLAN from 1 to 4094`). The name is composed exactly, never matched as a substring. |
| `koobiq.number_field(...)`, `react_aria.number_field(ex, label)` | `role=textbox` | `set(value, shown=)`, `expect_value` | `onChange` fires on blur, not while typing: `set` fills and presses Tab, then checks what the field shows. |
| `koobiq.checkbox(ex, label)`, `koobiq.switch(ex, label)` | state: `role=checkbox` / `role=switch`; click: the label text | `check`, `uncheck`, `toggle`, `expect_checked` | The `<input>` is clipped to one pixel inside a `<label>`: clicking or `check`-ing it waits on a hit test the label wins. `check` refuses an already checked box instead of toggling it off. |
| `koobiq.table(ex, name)`, `react_aria.table(ex, name)` | `role=grid`; rows `role=row` named by the row header | `row`, `rowheader`, `cell`, `rows`, `select_row`, `unselect_row`, `expect_selected`, `expect_rows`, `row_menu(row, trigger)` | Row checkboxes are named with a translated word ("Select router-one", "Выбрать router-one"): the row's checkbox is its first checkbox label. A mouse click on it toggles twice on Chromium 131 (the row selects on `pointerdown`, the check icon then takes the `pointerup` and the label's click toggles it back), so `select_row` presses Space on the focused row header, react-aria's keyboard selection. Selection is read from the row's `aria-selected`. |
| `koobiq.menu(ex, trigger)`, `react_aria.menu(ex, trigger)` | trigger `role=button`; menu `role=menu` named by the trigger | `open`, `choose(item, closes=True)`, `item(label)` | The menu is portalled to the end of `<body>`: `within=` the trigger finds nothing. |
| `koobiq.tabs(ex, name)` | `role=tablist`, `role=tab`, `role=tabpanel` named by its tab | `select(label)`, `tab`, `panel` | Selection is checked by `aria-selected` and the panel, not by the click alone. |
| `koobiq.tooltip(ex, trigger)` | `role=tooltip` | `open`, `expect_text` | react-aria opens a tooltip on hover only once a `pointermove` has set the "pointer" modality; the first move of a test enters the trigger before that, so a single hover opens nothing. `open` moves the pointer to the page corner first (one `ex.native` step). |
| `koobiq.search(ex, label)` | `role=searchbox` | `submit(text)` | A search field submits on Enter only; typing alone sends nothing. |
| `koobiq.dialog(ex, title, header=, exact=)`, `koobiq.side_panel(...)`, `koobiq.confirm(...)` | `role=dialog` whose `kbq-dialog-header-` element reads the title (XPath); `header="any"` also a heading or paragraph the product draws itself; `exact=False` a header that starts with the title (title and caption in one text) | `wait_open`, `wait_closed`, `close`, `press(name)`, `button`, `field`, `number_field` | Koobiq dialogs have no accessible name (the header is not a heading). Overlays animate for 300 ms and stay mounted while leaving: `wait_open` waits for `data-transition="entered"`, closing waits until the element is gone. The close button's name is translated; it is found by structure. |
| `koobiq.confirm(ex, title)` | the dialog with that title | `accept(action)`, `cancel(name)` | The action button carries the verb ("Delete", "Publish"); a dialog with another title never matches. The dismissing button is the product's word, so `cancel` takes its name. |
| `koobiq.toasts(ex)` | `role=alertdialog` named by the title; caption by `aria-describedby` | `read`, `mark`, `expect_new(mark, title, status=)`, `expect_no_new(mark, within_ms=)`; a `Toast` has `expect_caption`, `dismiss` | Titles repeat: a toast counts only if it appeared after `mark()`, and one already leaving never counts. `ToastProvider` is the region itself and renders no children. A negative (`expect_no_new`) costs its whole budget by construction and fails closed: a page that cannot be read, or that navigated during the window, is not "no toast". |
| `koobiq.badge(ex, text)` | `kbq-badge-` element with `data-variant` and that text | `read`, `expect_variant`, `expect_color` | The colour a product sets inline (`style.color`) is read and waited on as the browser normalizes it, `rgb(r, g, b)`. |
| `koobiq.tag_group(ex, name)` | `role=grid`, tags are `role=row` | `tag`, `remove(label)`, `expect_tags(count)` | The exported `Tag` is the group's item and renders nothing alone; the remove button's name is translated. |
| `react_aria.listbox(ex, name)` | `role=listbox`, `role=option` | `option`, `expect_selected` | A select's list is named after the field's label, not after the trigger. |

## react-select

`react_select.single(ex, label)` and `react_select.multi(ex, label)` find the field by
its combobox input: `aria-label`, `aria-labelledby` or `<label for>` naming it
`label`, or `input_id=` when the product sets `inputId`. A product that put the label
next to the field without associating it: `nearby=True` takes the one combobox of the
nearest container above the element whose own text is `label`. The `<prefix>__…` classes exist
only when the product sets `classNamePrefix`; pass `prefix=` if it is not
`react-select`.

| Part | Address | Actions | Trap the kit carries |
| --- | --- | --- | --- |
| field | `input` (`role=combobox`), `control`, `menu` (the one around the list the input's `aria-controls` names, inline or portalled) | `open`, `close`, `expect_open`, `wait_loaded`, `search(text)` | Escape inside a dialog also dismisses the dialog, Tab picks the focused option (`tabSelectsValue`), a click outside lands on whatever is there: `close` blurs this field's own input (react-select closes on blur). `search` fills, it never sends Backspace, which removes the last chip in an empty input. |
| options | `option(label)` inside the menu | `pick(*labels, keep_open=)` | A multi-select may close after each pick (`closeMenuOnSelect`); `pick` reopens it only when it closed, then checks the chip or the value. |
| chips | `chip(label)`, `chip_remove(label)` (`[role=button]` in the chip) | `remove(label)`, `expect_chips([...])`, `clear()` (then nothing is held) | The remove button is "Remove <label>" by default and often renamed ("Delete"); it is found inside the chip, not by name. |
| state | one evaluation | `state()`: chips, single, placeholder, open, loading, options (label, group, selected, disabled, focused), groups, notice, `unoffered` | A saved value the options no longer offer still renders a chip: `unoffered` lists such chips. |

## React Flow

`xyflow.node(ex, node_id, kind=)` addresses `.react-flow__node-<kind>[data-id=<id>]`.
Nodes are drawn with `visibility: hidden` until measured, so every action waits for
the node to be visible first. `click` selects (`expect_selected`), `open` double-clicks
(`ex.double_click`), `menu()` and `action(label)` use the node's `aria-haspopup` button
or a named one. `xyflow.nodes(kind)` counts nodes.

## CodeMirror

`codemirror.editor(ex, within=, nth=, name=)` addresses `.cm-editor`; `content` is its
`contenteditable` `.cm-content`. `text()` returns the whole document from the editor's
own view, which CodeMirror keeps on the content element (`cmTile`, `cmView` before 6.4x),
and only without it the drawn lines: CodeMirror draws the lines in view, so the drawn
text of a long document is not the document. `set_text(text)` replaces the document in
one input (`fill`, as a paste) and checks it; `type(text)` types key by key at the caret,
so the editor's handlers apply (an opening bracket gets its closing one);
`expect_text(text)` waits frame by frame until the document is exactly `text`.

## Discovery recognizes components

`testence explore` and the MCP tool `testence_snapshot` add a `components` list next
to `elements`. Each entry names the component, its kit line and the import it needs:

```json
{"kind": "koobiq.select", "name": "Mode", "required": false,
 "python": "koobiq.select(ex, \"Mode\")", "import": "from testence.kits import koobiq"}
```

Recognized: react-select fields (with `prefix=` or `input_id=` when needed), Koobiq
selects, number, search and required or hinted text fields, hidden-input checkboxes
and switches, dialogs and side panels (with their `transition`), toasts (with their
titles), tables and tag groups, tab lists, open menus and lists, React Flow nodes.
A react-aria helper is suggested only where react-aria left its markers (`data-rac`,
`data-collection`, `data-react-aria-pressable`, `react-aria…` ids) or Koobiq its
classes: a bare ARIA role, a plain `<table>` or a native checkbox gets no kit line. A
component without an accessible name gets a positional `Target('css', …, nth=N)` and a
`note`, never a kit call that would need the missing name. At most 8 of one kind are
listed, so a page of checkboxes does not crowd out its dialog. Names pass through the
project's redaction policy like the rest of the snapshot.
Recognition is a hint for authoring, read in one evaluation; it proves nothing about
the product.

## Conformance

`bench/sut/koobiq` is a page built with the real `@koobiq/react-components`,
`react-select` and `@xyflow/react` at exact versions, one instance of each component
above, each writing what it did to an event log. The build is committed (`dist/`), so
`uv run pytest -q` runs `tests/test_kits_*.py` against it without Node; a test fails
when the build is older than its sources. Locale-sensitive cases run in English and
Russian. `bench/kits_latency.py` times each kit method on the stand
([snapshot](../../bench/results/kits_latency.json),
[budget](../../bench/budgets/kits_latency.json)); most of a Koobiq method's time is the
component's own 300 ms transition.

To check a new Koobiq release, see the stand's [README](../../bench/sut/koobiq/README.md).

## The project adapter

A kit stops at what the library renders. What remains belongs to the project, in a
thin adapter module that composes kit objects with the product's own knowledge:

- **Routes and screens**: which URL opens the list, which query parameter opens a
  record's panel, what "the screen is ready" means for this product.
- **Names**: the titles of its panels and confirmations, its menu items, its field
  labels and hints, in the languages it ships.
- **The product's own wrappers**: a resizable panel's drag handle, a table's column
  resizer, a search form that is the product's and not the library's. Those are not
  the library's; the adapter addresses them.
- **Data**: the seed that creates what a case needs, the oracle that reads the result
  back from the API, and the clean-up that removes it. A kit never asserts on server
  state.

```python
# project adapter: routers.py
from testence.kits import koobiq

def open_router(ex, router):
    ex.navigate(f"/routers?panel={router['id']}", intent=f"open {router['name']}")
    panel = koobiq.side_panel(ex, "Edit router")
    panel.wait_open()
    return panel
```

The test then reads as product intent, the adapter knows the product, and the kit
knows the components; none of the three re-learns the others' traps.
