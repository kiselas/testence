"""The canonical suite for the collection screen.

One test per claim, and every claim is the smallest true statement about the
product that a defect in the corpus can falsify. Deliberately ordinary code: what
the benchmark measures is the framework's behaviour on the kind of suite a project
would actually write, not on a rig built to flatter it.

Three rules hold everywhere in this file, and all three are load-bearing.

**Nothing is retried.** Waiting for a condition is fine — that is what an
auto-waiting engine is for. Repeating an *interaction* is not, because the corpus
contains defects that a repeat cures (`retry_hides_it`). A suite that clicks twice
scores zero on exactly the items that distinguish this framework from a retry loop.

**Every oracle claim is self-checkable.** The oracle calls the API with the same
run and the same defect list the page carries, so the API misleads it exactly as it
misleads the page. A claim therefore has to be answerable by the API against
itself — "the reported total equals what you will actually hand over", "no row you
return is marked deleted" — rather than by comparing against a copy of the product
known to be healthy. No real oracle has one of those.

**A parameter change is committed exactly once, through one path.** The search box
both debounces typing and commits on Enter, and that ambiguity collided with the
corpus the first time this file was written: pressing Enter satisfies the control
where typing alone is inert by design, but the debounce then fires as a *second*
update and cures the swallowed-first-interaction defect, hiding it. So the search
claims commit explicitly and the swallowed-first-interaction defect is caught
through paging, whose commit path is a single click. That is also truer to the
original: it swallowed the first search, page change *or* sort alike.
"""

from __future__ import annotations

import pytest

from testence.engine import Target

TOTAL = Target("css", "[data-testid='total']")
ANY_ROW = Target("css", "tbody tr")
ROWS = Target("css", "tbody tr[data-key]")
NAMES = Target("css", "tbody tr[data-key] td:first-child")
STATUSES = Target("css", "tbody tr[data-key] td:nth-child(3)")
SKELETONS = Target("css", "tbody tr.skeleton")
SEARCH = Target("role", "searchbox")
STATUS_FILTER = Target("role", "combobox")
NEW_ROW = Target("placeholder", "new row name")
CREATE = Target("role", "button", name="Create")
NEXT_PAGE = Target("role", "button", name="next")

PAGE_SIZE = 10
SETTLE_MS = 4_000


@pytest.fixture(autouse=True)
def _open(ex, sut):
    ex.goto(sut.url(), intent="open the collection")
    # Any row, placeholders included: whether placeholders gave way to data is a
    # claim of its own, and setup must not decide it.
    ex.engine.wait_for_count(ANY_ROW, minimum=1)


def commit_search(ex, term: str) -> None:
    """Type and commit, once. See the third rule in the module docstring."""
    ex.fill(SEARCH, term, intent=f"search for {term!r}")
    with ex.step("commit the search"):
        ex.engine.press("Enter")


def loaded(ex) -> None:
    """Wait until the collection has finished loading.

    A claim that reads the counter must state this itself. Setup only waits for a
    row to exist, and placeholders are rows — so without this a read lands on the
    empty pre-load state. Three claims here passed purely because the target was
    fast enough, and a control that adds 300 ms to every response is what exposed
    them. That is the control doing its job: it found a fragile suite.
    """
    ex.engine.wait_while_visible(SKELETONS, timeout_ms=SETTLE_MS)


def settled_on(ex, total: str, intent: str) -> None:
    """Wait for the collection to actually be the one just asked for.

    "At least one row carries text" is satisfied by the rows that were already on
    screen, so reading straight after an interaction reads the *previous* result —
    a common stale-view trap. The counter is the cheapest honest signal that the
    new result has landed.
    """
    ex.expect_text(TOTAL, total, intent=intent)


def test_the_counter_matches_what_the_api_will_hand_over(ex, sut, oracle):
    """The heading claims a size; the collection must actually contain it.

    Checked by paging to exhaustion rather than by reading `total` back, because
    `total` is one of the things under test.
    """
    loaded(ex)
    shown = ex.engine.read_text(TOTAL)
    with ex.step("count what the API will actually hand over"):
        actual = len(sut.all_rows(oracle))
    assert shown == str(actual), (
        f"the heading says {shown} rows; paging the API to exhaustion yields {actual}"
    )


def test_a_page_is_full_until_the_last_one(ex, sut, oracle):
    """A page that is not the last one holds a full window."""
    loaded(ex)
    with ex.step("read the first page through the API"):
        page = sut.rows_page(oracle, page=1)
    rendered = ex.engine.count(ROWS)
    assert page["total"] > PAGE_SIZE, "fixture: the collection must span several pages"
    assert len(page["rows"]) == PAGE_SIZE, (
        f"page 1 of {page['total']} returned {len(page['rows'])} rows, not {PAGE_SIZE}"
    )
    assert rendered == PAGE_SIZE, f"the page renders {rendered} rows, not {PAGE_SIZE}"


def test_rows_show_data_not_placeholders(ex):
    """Presence is not content.

    A collection that paints placeholders satisfies "the elements exist" and "there
    are ten of them" while showing nothing. The claim has to be about text.
    """
    ex.engine.wait_for_content(NAMES, minimum=1, timeout_ms=SETTLE_MS)
    names = ex.engine.read_all_texts(NAMES)
    assert len(names) == PAGE_SIZE, f"{len(names)} rows carry text, expected {PAGE_SIZE}"
    assert all(name.strip() for name in names), f"blank cells among {names}"
    assert ex.engine.count(SKELETONS) == 0, "placeholders are still on the page"


def test_paging_advances_on_the_first_click(ex, sut, oracle):
    """One click, one page. The click is not repeated — that is the whole claim."""
    ex.engine.wait_for_content(NAMES, minimum=1, timeout_ms=SETTLE_MS)
    before = ex.engine.read_all_texts(NAMES)
    with ex.step("ask the API what the second page holds"):
        second = sut.rows_page(oracle, page=2)["rows"]

    ex.click(NEXT_PAGE, intent="go to the second page")
    # Not the pager: it renders the page that was *requested*, straight from local
    # state, so it says "page 2" while the table still shows page one's rows. The
    # honest synchronisation point is a row that only the second page contains.
    ex.expect_visible(Target("css", f"tbody tr[data-key='{second[0]['id']}']"),
                      intent="a row belonging to the second page is on screen")

    after = ex.engine.read_all_texts(NAMES)
    expected = [row["name"] for row in second]
    assert after != before, "one click on 'next' left the first page on screen"
    assert after == expected, f"the second page shows {after}, the API returned {expected}"


def test_search_filters_the_collection(ex):
    """A committed search narrows the collection."""
    commit_search(ex, "ember")
    ex.expect_text(TOTAL, "2", intent="the collection narrows to the matches")


def test_search_matches_a_substring(ex):
    """Matching is documented as substring, not prefix."""
    # The fragment sits mid-word in two different names, so a prefix matcher finds
    # nothing at all while a substring matcher finds four. Chosen for that gap: a
    # term where prefix matching returned an empty page would fail loudly, and this
    # class of defect is the quiet kind.
    commit_search(ex, "mber")
    settled_on(ex, "4", intent="the collection narrows to the mid-word matches")
    names = ex.engine.read_all_texts(NAMES)
    assert sorted(names) == ["ember-04", "ember-30", "umber-20", "umber-46"], (
        f"a fragment from the middle of a name returned {names}"
    )


def test_the_status_filter_shapes_the_result(ex, sut, oracle):
    """Every row that comes back matches the filter that was asked for."""
    # Asked of the API rather than written down here. A literal count would be a
    # claim about the fixture's seed data, and it broke the moment a neighbouring
    # claim added a row. Under a server that drops the filter this simply settles
    # on the unfiltered total, and the assertion below is what catches it.
    with ex.step("what the API says a draft filter returns"):
        expected_total = sut.rows_page(oracle, status="draft")["total"]
    ex.select(STATUS_FILTER, "draft", intent="filter to one status")
    settled_on(ex, str(expected_total), intent="the collection settles on that result")
    shown = ex.engine.read_all_texts(STATUSES)
    assert shown and set(shown) == {"draft"}, f"filtered to draft, got {sorted(set(shown))}"
    with ex.step("the API agrees it filtered"):
        returned = sut.all_rows(oracle, status="draft")
    offenders = sorted({row["status"] for row in returned} - {"draft"})
    assert not offenders, f"the API returned rows with status {offenders} under a draft filter"


def test_deleted_rows_are_not_listed(ex, sut, oracle):
    """A removed row is gone from every listing."""
    with ex.step("read the whole collection through the API"):
        returned = sut.all_rows(oracle)
    dead = [row["id"] for row in returned if row.get("deleted")]
    assert not dead, f"deleted rows are still listed: {dead}"


def test_a_deep_link_applies_its_filter(ex, sut):
    """Arriving with a filter in the address is the same as typing it."""
    ex.goto(sut.url(search="ember"), intent="arrive with a filter in the address")
    ex.expect_text(TOTAL, "2", intent="the filter is applied on arrival")


def test_a_created_row_appears_without_a_reload(ex):
    """A write the user just made is visible to the user who made it.

    Asserted on the counter, and deliberately not by searching for the new row:
    a search is a fresh request, the server has the row, and the claim would pass
    while the stale view it is about sat untouched on the screen. The whole class
    is hidden by anything that re-asks the server — that is what makes it
    `retry_hides_it`.
    """
    loaded(ex)
    before = int(ex.engine.read_text(TOTAL))
    ex.fill(NEW_ROW, "zzz-probe", intent="name a new row")
    ex.click(CREATE, intent="create it")
    ex.expect_text(TOTAL, str(before + 1),
                   intent="the collection the user is looking at grew by one")
