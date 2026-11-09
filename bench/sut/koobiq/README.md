# Koobiq conformance stand

One page built with the **real** packages the kits address, at exact versions
(`package.json`): `@koobiq/react-components`, `react-select`, `@xyflow/react` and `codemirror` on
React 19. Nothing on it is a hand-made copy of their DOM. Each control writes what it
did to the event log (`#log`), so a conformance test checks what the component reported,
not only what it drew.

| Instance | Kit | State it lets a test drive |
| --- | --- | --- |
| Checkbox, Toggle | `koobiq.checkbox`, `koobiq.switch` | hidden input inside a label |
| Select "Mode" | `koobiq.select` | trigger named "label value", portalled list |
| SearchInput | `koobiq.search` | submit on Enter only |
| Tooltip on "Help" | `koobiq.tooltip` | hover after the pointer modality is known |
| Tabs | `koobiq.tabs` | selection and panels |
| Badge, TagGroup | `koobiq.badge`, `koobiq.tag_group` | inline colour, removable tags |
| react-select "Targets" (`isMulti`), "Zone" | `react_select` | groups, a disabled option, a saved value the options no longer offer, a "no options" notice, clearing |
| Table "Routers" | `koobiq.table` | row selection checkboxes, a row menu |
| SidePanel "Edit router" | `koobiq.side_panel` | 300 ms slide in and out, a required field, a NumberField with a hint |
| Modal "Delete «router-two»" | `koobiq.confirm` | accept and cancel |
| Toasts | `koobiq.toasts` | success and error, repeated titles, dismissal |
| React Flow nodes | `xyflow` | selection, double-click, node menu |
| Select "Color" (required) | `koobiq.select` | a list named "Color *" |
| Modals "Agent token created", "Publish «tpl-one»?" | `koobiq.dialog(header="any")`, `koobiq.confirm(exact=False)` | a title the product draws itself, a header with a caption |
| react-select "Owner" | `react_select.single(nearby=True)` | a label not associated with its input |
| CodeMirror 6 editor (`#schema`) | `codemirror` | the document, a replacement, typing at the caret |

`?locale=ru-RU` renders Koobiq's own labels in Russian; the locale-sensitive tests run
in both languages.

## Build

```bash
npm ci --prefix bench/sut/koobiq
npm run build --prefix bench/sut/koobiq
```

The build in `dist/` is committed, so `uv run pytest -q` exercises the kits without
Node. `npm run build` also writes `dist/stand.json`: the SHA-256 of every source and the
installed versions. `tests/test_kits_stand.py` fails when a source changed after the
build, and when the Koobiq version built is not one `testence.kits.koobiq.VERIFIED`
lists. `.npmrc` sets `legacy-peer-deps`: Koobiq declares `react-markdown`, `remark-gfm`
and `highlight.js` as peers of entry points the stand does not import.

`dist/.vite/license.md` lists the licenses of everything bundled (MIT and Apache-2.0).

```bash
.venv/Scripts/python bench/sut/koobiq/server.py --port 8810   # http://127.0.0.1:8810
```

## Checking a new release

Build a copy of the stand against the release outside the repository and point the
tests at it:

```bash
cp -r bench/sut/koobiq/{.npmrc,index.html,package.json,stamp.mjs,vite.config.ts,src} /tmp/stand-next/
# set the new "@koobiq/react-components" version in /tmp/stand-next/package.json
npm install --prefix /tmp/stand-next && npm run build --prefix /tmp/stand-next
TESTENCE_KOOBIQ_STAND=/tmp/stand-next/dist uv run pytest -q tests/test_kits_koobiq.py \
  tests/test_kits_react_select.py tests/test_kits_xyflow.py tests/test_kits_discovery.py
```

When it passes, add the version to `VERIFIED` in `src/testence/kits/koobiq.py` and raise
`SUPPORTED` to the next minor, with its evidence: either move the stand to it and rebuild
`dist/`, or commit a receipt `receipts/koobiq-<version>.json` holding that build's
`stand.json`, the test command and each run's environment and result
(`receipts/koobiq-0.38.0.json` is one). `tests/test_kits_stand.py` refuses a claimed
version without evidence, and a receipt made from other page sources than the stand's.

## Latency

```bash
.venv/Scripts/python bench/kits_latency.py
.venv/Scripts/python bench/kits_latency.py --repeats 5 --check
```

Each kit method is timed on the stand, one page load per repeat;
`bench/budgets/kits_latency.json` holds broad ceilings that catch a method waiting out a
step budget. The checked-in snapshot is `bench/results/kits_latency.json`.
