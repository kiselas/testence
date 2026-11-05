# Authoring generators

The commands below do the typing that every new suite repeats, so an author spends the
time on addresses and oracles instead. None of them runs a browser, and none of them
invents an expected value.

| Command | Reads | Writes |
|---|---|---|
| `testence plan skeleton` | a Markdown case file | a PlanSpec and pytest stubs |
| `testence seed scaffold` | an OpenAPI 3.x document | fixtures for temporary objects with ordered cleanup |
| `testence inventory` | a finished run's ledger | a Markdown reference per screen |

## `testence plan skeleton`: cases to a plan and test stubs

```bash
testence plan skeleton cases/login.md --plan specs/login.json --tests tests_e2e
testence plan skeleton cases/login.md --plan specs/login.md --tests tests_e2e --module test_login
testence plan validate specs/login.json
```

The case file is Markdown in one of two shapes. A table with a steps column and an
expected-result column (`#`, `Title`/`Название`, `Steps`/`Шаги`,
`Expected result`/`Ожидаемый результат`; an optional `Precondition` column):

```markdown
| # | Title | Steps | Expected result |
|---|-------|-------|-----------------|
| 1 | Sign in | 1. Open `/login`<br>2. Type "demo@example.test" into Email<br>3. Click "Sign in" | The greeting "signed in as demo@example.test" is shown |
```

Or one section per case, headed `## Case N — title`, `### Кейс N — …` or `### N. title`,
with numbered or `- bulleted` steps and expected results as `Expected:`/`Ожидается:`
lines, a list under a bare `Expected:` label, or `→` items under a step. A heading with a
number but no case word (`## 3. Overview`) is a case only when its section states an
expected result, so numbered chapters and dated notes are not mistaken for cases. Short
`- Key: value` bullets above the first step are metadata; an indented bullet under a step
details that step.

```markdown
## Case 2 — Validation of an empty name

- Precondition: the catalogue is empty.

1. Click "New widget".
   - → The form "New widget" opens
2. Click "Save".

Expected: the message "Name is required" is shown
```

What it builds:

- **Plan.** One scenario per case (`case-N`), one claim and one required `ui` assertion
  per expected result. `statement` and `expected` are the source text, verbatim. In a
  table, each `<br>` line or `1. … 2. …` item of the expected cell is its own result.
  A case with no expected result gets no scenario; it is listed under `open_questions`
  (and, for a `.md` plan, in its `## Open questions` section). Upgrade an assertion's
  oracle to `api` where the result is about stored data: the generator cannot know.
- **Tests.** A file `test_NN_<slug>.py` per case, or every case in `--module <name>`.
  Each function carries `@pytest.mark.testence(plan=…, claims=[…], case_id="case-N")`, a
  comment and a stub per step with `intent="case N step M: …"` (`кейс N ш.M: …` for a
  Russian source), and a bound `ex.expect_visible(…, assertion_id=…, claim_id=…)` per
  expected result. A step mentioning a path becomes `ex.goto`, a pressed key (`Press
  Enter`, `Ctrl+S`) becomes `ex.press`, and a quoted value becomes the `fill` value.
  Addresses never are: every stub calls `TODO("…")`, and an unquoted value
  `TODO_VALUE("…")`; both fail the step at once until you replace them with a `Target`
  from `testence explore` or a failure snapshot and the value the case means. A case
  without steps is listed under `warnings`: its test has checks only.

`--root` (default `.`) is the pytest root: the marker's `plan=` path is relative to it.
`--id` and `--project-id` override the plan and project IDs (defaults: the case file's
name and the root directory's name).

Rerunning is safe. Each generated file records a digest of its own content in its first
line (`# testence:skeleton sha256=…`; a `.json` plan in an `x-testence-skeleton` field).
A file whose content still matches is refreshed from the case file; a file you edited, or
one without the marker, is reported as `kept` and left alone. So after editing a case in
the source, rerun the command: untouched stubs follow, written tests do not move. A file
name carries the case title, so a retitled case gets a new file; the old skeleton of the
same plan is `removed` when untouched, and reported as `stale` (kept) when you edited it,
because both would bind the same claims.

The case file must be UTF-8 (a BOM is fine); anything else is exit 2 with how to convert
it, never a traceback.

With `--json` the command prints a `testence/plan-skeleton/1` document: `format`,
`plan` (`path`, `id`, `valid`), `cases` (number, `case_id`, title, claims, test file),
`files` (path, `kind`, `status` of `created`, `updated`, `unchanged`, `kept`, `removed`
or `stale`), `open_questions` and `warnings`. Exit codes: 0 written and the plan validates, 2 the case file cannot
be turned into a plan without guessing (no cases, duplicate numbers, no expected result
anywhere, an expected text over 1000 characters), 3 the plan on disk is an edited one
that no longer validates.

## `testence seed scaffold`: temporary objects and their cleanup

```bash
testence seed scaffold --openapi openapi.json --out conftest_seed.py --marker "(temp)"
testence seed scaffold --openapi https://app.example/openapi.json --collections projects,posts
```

The command reads an OpenAPI 3.x document (a file or an http(s) URL; JSON, or YAML when
PyYAML is installed) and writes a fixture module for its collections. A collection is a
path with a list `GET` and an item path below it with `DELETE`, whose schema has a
`name`, `title`, `label` or `display_name` field to carry the marker; other paths are
listed under `skipped` with the reason. `--collections` limits the module to the named
ones (a nested collection needs its parent selected too).

The module, built only on `testence_api` (`ApiClient`), never on the browser, holds:

- `temp_name(ticket, label)`, which returns `"<ticket> <label> <marker>"`;
- `Sweeper`, which finds marked objects by name (with the list's search parameter when
  the document declares one, always filtered by the marker) on every page of the list,
  deletes them in `DELETE_ORDER`, repeats a `DELETE` answered with 409 for up to five
  seconds, and then gives `GET` on the object five more seconds to answer 404;
  `assert_clean()` fails while anything marked is left;
- `temp_sweeper`, a fixture whose teardown sweeps and asserts clean, and a
  `make_temp_<name>(ticket, label, *parent_ids, **fields)` factory per collection; the
  parent ids fill a nested list path's parameters in order
  (`make_temp_member("T-12", "viewer", org["id"], team["id"])`).

Paging comes from the list's query parameters, `$ref` ones included: `page` (with
`per_page`, `page_size`, `size` or `limit`) or `offset`/`skip` (with `limit`). The sweeper
reads until a short or empty page, and fails if the API repeats a page. A list without
paging parameters is read once; if its envelope declares a total (`total`, `count`, …)
larger than what came back, `find` fails rather than miss marked objects. A list with
neither cannot show it was cut short; give it a search parameter.

Nesting may go several levels deep (`/orgs/{org}/teams/{team}/members`): a nested
collection is found under every marked object of its parent, and its parent must be a
collection too.

`DELETE_ORDER` puts dependents first. A collection depends on another when its create
or item schema has a `$ref` to the other's schema (also inside `allOf` or `items`), a
field named after it (`project_id`, `projectId`, `post_ids`), or when its path is nested
under the other's item path. A cycle is an error: no order is safe, so choose
collections without it.

Load the module from a `conftest.py` with `pytest_plugins = ["conftest_seed"]`, then:

```python
def test_rename_project(ex, make_temp_project):
    project = make_temp_project("T-12", "rename", description="seeded")
    ...
```

Under parallel workers, give each worker its own marker: sweepers that share one delete
each other's objects. Collection names come from the path, transliterated when not ASCII
and numbered when two paths would share one. Regeneration follows the same rule as the
skeleton: an edited module is `kept`.

With `--json` the command prints a `testence/seed-scaffold/1` document: `out`, `status`
(`created`, `updated`, `unchanged`, `kept`), `marker`, `collections` (paths, name field,
search parameter, `items_key`, `total_key`, `paging`, `parent`, `depends_on`),
`delete_order` and `skipped`. Exit code 2 means the document cannot be read (including
one that is not UTF-8) or yields no safe cleanup.

## `testence inventory`: a screen reference from a run

```bash
testence inventory runs/r-local
testence inventory runs/r-local --out docs/inventory --json
```

The command reads one run's ledger (`run.jsonl`, and `pack.json` of failed tests) and
writes one Markdown file per page under `--out` (default `docs/inventory`), named after
the page path with identifiers templated: `/projects/42/settings` becomes
`projects_id_settings.md`. A name that would lose anything (case, punctuation, another
script, a literal `id` segment, length) gets a short digest of the page, so two pages never
share a file: `/a/b` is `a_b.md`, `/a-b` is `a-b.md`, `/привет` is `privet-<digest>.md`.
A file another page already owns is never merged into. Each file has four generated sections:

- **Targets**: every Target a step addressed on the page, with its role or kind, name,
  actions (`click` and `fill` from the recorded operation; another step on a Target is
  `check` unless its intent starts with an action verb) and the text the element showed;
- **API calls**: the browser's requests from the run's `net` record (method, path with
  `{id}`, statuses) in tests that visited the page, and the test's own `testence_api`
  calls, marked `test`;
- **Texts**: what green `expect_*` steps saw, such as toasts and headings;
- **Traps**: steps that failed at least once, with the error and whether the test then
  went green (a rerun, a soft check, or a later run).

The page of a step is the last navigation its test made. The ledger names it when the
`goto`/`navigate` intent contains the URL (the default `open <url>` does), or when a
failure pack recorded `page_url`; steps before such a navigation are filed in
`unknown-page.md`. A custom intent such as `"open the project list"` hides the URL, so
write `"open /projects"` where the page matters.

Rerunning on another run merges into the existing file: earlier targets, calls, texts
and traps stay, trap counts add up, and a run already merged is not counted twice. A
section whose heading carries `<!-- manual -->` is yours and is kept verbatim:

```markdown
## Notes <!-- manual -->

The Save button stays disabled until the name changes.
```

The merge state lives in a `<!-- testence:inventory … -->` comment at the end of each
file; leave it in place. With `--json` the command prints a `testence/inventory/1`
document: `run_dir`, `out` and `pages` (page, path, status, counts of targets, API calls,
texts, traps and manual sections). Exit code 2 means the run directory cannot be read.
