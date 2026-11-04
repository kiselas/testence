# Authoring generators

The commands below do the typing that every new suite repeats, so an author spends the
time on addresses and oracles instead. None of them runs a browser, and none of them
invents an expected value.

| Command | Reads | Writes |
|---|---|---|
| `testence plan skeleton` | a Markdown case file | a PlanSpec and pytest stubs |
| `testence seed scaffold` | an OpenAPI 3.x document | fixtures for temporary objects with ordered cleanup |

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
with numbered steps and expected results as `Expected:`/`Ожидается:` lines, a list under a
bare `Expected:` label, or `→` items under a step:

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
  expected result. A step mentioning a path becomes `ex.goto`, a key chord becomes
  `ex.press`, and a quoted value becomes the `fill` value. Addresses never are: every stub
  calls `TODO("…")`, which fails the step at once until you replace it with a `Target`
  from `testence explore` or a failure snapshot.

`--root` (default `.`) is the pytest root: the marker's `plan=` path is relative to it.
`--id` and `--project-id` override the plan and project IDs (defaults: the case file's
name and the root directory's name).

Rerunning is safe. Each generated file records a digest of its own content in its first
line (`# testence:skeleton sha256=…`; a `.json` plan in an `x-testence-skeleton` field).
A file whose content still matches is refreshed from the case file; a file you edited, or
one without the marker, is reported as `kept` and left alone. So after editing a case in
the source, rerun the command: untouched stubs follow, written tests do not move.

With `--json` the command prints a `testence/plan-skeleton/1` document: `format`,
`plan` (`path`, `id`, `valid`), `cases` (number, `case_id`, title, claims, test file),
`files` (path, `kind`, `status` of `created`, `updated`, `unchanged` or `kept`) and
`open_questions`. Exit codes: 0 written and the plan validates, 2 the case file cannot
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
  the document declares one, always filtered by the marker), deletes them in
  `DELETE_ORDER`, repeats a `DELETE` answered with 409 for up to five seconds, and then
  requires `GET` on the object to answer 404; `assert_clean()` fails while anything marked
  is left;
- `temp_sweeper`, a fixture whose teardown sweeps and asserts clean, and a
  `make_temp_<name>(ticket, label, **fields)` factory per collection.

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
each other's objects. Lists are read as one page; a collection with more marked objects
than one page returns needs the sweeper's `find` adapted. Regeneration follows the same
rule as the skeleton: an edited module is `kept`.

With `--json` the command prints a `testence/seed-scaffold/1` document: `out`, `status`
(`created`, `updated`, `unchanged`, `kept`), `marker`, `collections` (paths, name field,
search parameter, `items_key`, `parent`, `depends_on`), `delete_order` and `skipped`.
Exit code 2 means the document cannot be read or yields no safe cleanup.
