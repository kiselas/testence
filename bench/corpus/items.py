"""Corpus items for the collection screen: what is seeded, and what must happen.

An item names the behaviours to inject and the ground truth for every scale the
benchmark measures. `expect_claims` is what separates this from the older corpus:
it is not enough that the suite went red, it has to go red **for the right reason**.
A run that fails the wrong claim has not caught the defect; it has had an accident
that happened to coincide with one.

Collateral failures are recorded, not punished. A defect that stops the collection
rendering at all breaks half the claims, and that is honest behaviour rather than
imprecision — the runner reports the extra failures so a reader can see the blast
radius without it distorting the score.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Short name -> the test that carries the claim.
CLAIMS = {
    "counter": "test_the_counter_matches_what_the_api_will_hand_over",
    "full-page": "test_a_page_is_full_until_the_last_one",
    "content": "test_rows_show_data_not_placeholders",
    "paging": "test_paging_advances_on_the_first_click",
    "search": "test_search_filters_the_collection",
    "substring": "test_search_matches_a_substring",
    "filter": "test_the_status_filter_shapes_the_result",
    "deleted": "test_deleted_rows_are_not_listed",
    "deep-link": "test_a_deep_link_applies_its_filter",
    "create": "test_a_created_row_appears_without_a_reload",
}


@dataclass
class Item:
    id: str
    defects: list[str]
    verdict: str
    """Ground truth for the triage pass: real_bug | behaviour_change | ui_change |
    flaky_timing | environment | none (ADR-0014)."""
    expect_failure: bool
    expect_claims: list[str] = field(default_factory=list)
    """Claims that MUST fail. Empty for anything expected to stay green."""
    stratum: str = ""
    """Deceptiveness: N (fails naively) · P (precise assertion) · O (needs an
    oracle) · A (green almost always). Empty for controls and drift."""
    expect_heal: bool = False
    note: str = ""


ITEMS: list[Item] = [
    # -- the baseline ------------------------------------------------------
    Item(
        id="healthy",
        defects=[],
        verdict="none",
        expect_failure=False,
        note="nothing seeded; this is the run's false-red floor",
    ),

    # -- defects -----------------------------------------------------------
    Item(
        id="D-40-first-interaction-swallowed",
        defects=["D-40"],
        verdict="real_bug",
        expect_failure=True,
        expect_claims=["paging"],
        stratum="P",
        note="retry_hides_it: the flagship. A framework that repeats the click reports green",
    ),
    Item(
        id="D-13-view-does-not-catch-up",
        defects=["D-13"],
        verdict="real_bug",
        expect_failure=True,
        expect_claims=["create"],
        stratum="O",
        note="retry_hides_it: a reload between acting and asserting hides it entirely",
    ),
    Item(
        id="D-15-placeholders-persist",
        defects=["D-15"],
        verdict="real_bug",
        expect_failure=True,
        expect_claims=["content"],
        stratum="P",
        note="broad collateral is expected: nothing renders, so most reads fail",
    ),
    Item(
        id="D-17-deleted-rows-listed",
        defects=["D-17"],
        verdict="real_bug",
        expect_failure=True,
        expect_claims=["deleted"],
        stratum="O",
        note="the page looks entirely healthy; only the API contract shows it",
    ),
    Item(
        id="D-34-deep-link-ignored",
        defects=["D-34"],
        verdict="real_bug",
        expect_failure=True,
        expect_claims=["deep-link"],
        stratum="P",
    ),
    Item(
        id="D-43-counter-disagrees",
        defects=["D-43-counter"],
        verdict="real_bug",
        expect_failure=True,
        expect_claims=["counter"],
        stratum="O",
        note="only catchable by counting what the API will actually hand over",
    ),
    Item(
        id="D-43-short-page",
        defects=["D-43-short-page"],
        verdict="real_bug",
        expect_failure=True,
        expect_claims=["full-page"],
        stratum="O",
        note="an assertion on the first row passes; the window is one short",
    ),
    Item(
        id="D-44-prefix-not-substring",
        defects=["D-44"],
        verdict="real_bug",
        expect_failure=True,
        expect_claims=["substring"],
        stratum="P",
        note="a whole-word search still works, which is what makes it look like bad test data",
    ),
    Item(
        id="D-45-filter-dropped",
        defects=["D-45"],
        verdict="real_bug",
        expect_failure=True,
        expect_claims=["filter"],
        stratum="O",
        note="the request in the network log carries the filter the server ignored",
    ),

    # -- drift: red, with a proposal ---------------------------------------
    Item(
        id="U-01-renamed-control",
        defects=["U-01-renamed-control"],
        verdict="ui_change",
        expect_failure=True,
        expect_claims=["create"],
        expect_heal=True,
        note="a renamed accessible name must fail loudly AND carry a heal proposal",
    ),

    # -- controls: must stay green -----------------------------------------
    Item(
        id="C-08-restyle",
        defects=["C-08-restyle"],
        verdict="none",
        expect_failure=False,
        note="classes only; semantic addressing must survive it",
    ),
    Item(
        id="C-08-reorder",
        defects=["C-08-reorder"],
        verdict="none",
        expect_failure=False,
        note="pure reordering of controls",
    ),
    Item(
        id="C-08-wrap",
        defects=["C-08-wrap"],
        verdict="none",
        expect_failure=False,
        note="the control gains a container and keeps its semantics",
    ),
    Item(
        id="C-10-slow-responses",
        defects=["C-10"],
        verdict="none",
        expect_failure=False,
        note="300 ms per response; auto-waiting must absorb it without a flake",
    ),
    Item(
        id="C-12-console-noise",
        defects=["C-12"],
        verdict="none",
        expect_failure=False,
        note="a permanent console error that affects nothing — must reach the pack, "
             "must not fail the run",
    ),
    Item(
        id="C-13-commit-on-enter-only",
        defects=["C-13"],
        verdict="none",
        expect_failure=False,
        note="typing alone is inert by design; a suite that assumes a commit model cries wolf",
    ),
]


def by_id(item_id: str) -> Item:
    for item in ITEMS:
        if item.id == item_id:
            return item
    raise KeyError(item_id)
