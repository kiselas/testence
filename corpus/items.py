"""The failure corpus: seeded defects with ground-truth labels.

Mutation testing applied to a test framework. Each item mutates the target page in
a way whose *correct* interpretation we know in advance, which turns otherwise
unfalsifiable claims ("the evidence is sufficient", "healing works") into measured
numbers:

- **mechanically measurable, no LLM needed** — did the suite fail when it should
  (``false_green_rate``), did it stay green when it should (false reds), did the
  heal proposer name the right new address (``heal_precision``/``heal_recall``),
  and did it refuse to heal a deleted element (``disappearance_discrimination``,
  a guardrail that must be perfect);
- **ground truth for agent scoring** — ``verdict`` is the label an agent's triage
  is graded against (``verdict_accuracy``, ``real_bug_recall``).

Controls matter as much as defects: a framework that reports failures for harmless
reordering or restyling is unusable, so those items must stay green.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class CorpusItem:
    name: str
    verdict: str
    """Ground truth: real_bug | test_bug | behaviour_change | ui_change | flaky_timing |
    environment | none (ADR-0014)."""
    mutate: Callable[[str], str]
    note: str
    expect_failure: bool = True
    expect_heal: list[dict[str, str]] | None = None
    """For drift items: addresses that would be a *correct* proposal. A list,
    because several addressings of the same element are equally valid (role+name,
    a test id, an id selector) — grading against one arbitrary form would measure
    the corpus author's taste, not the proposer's accuracy."""
    expect_no_heal: bool = False
    """For deleted elements: proposing a heal here would be the worst failure mode."""
    extra: dict[str, str] = field(default_factory=dict)


def _replace(old: str, new: str) -> Callable[[str], str]:
    def mutate(html: str) -> str:
        if old not in html:
            raise AssertionError(f"corpus mutation target not found: {old!r}")
        return html.replace(old, new, 1)

    return mutate


ITEMS: list[CorpusItem] = [
    # -- locator drift: the element moved or was renamed -------------------
    CorpusItem(
        name="ui_change_button_renamed",
        verdict="ui_change",
        mutate=_replace('<button id="add">add</button>', '<button id="add">append</button>'),
        note="the add button's accessible name changed; the feature still works",
        expect_heal=[
            {"kind": "role", "value": "button", "name": "append"},
            {"kind": "css", "value": "#add"},
        ],
    ),
    CorpusItem(
        name="ui_change_placeholder_renamed",
        verdict="ui_change",
        mutate=_replace('placeholder="name"', 'placeholder="full name"'),
        note="the name field's placeholder changed; addressing by placeholder breaks",
        expect_heal=[
            {"kind": "role", "value": "textbox", "name": "full name"},
            {"kind": "css", "value": "#name"},
        ],
    ),
    CorpusItem(
        name="ui_change_wrapped_in_container",
        verdict="ui_change",
        mutate=_replace('<button id="inc">inc</button>',
                        '<div class="toolbar"><button id="inc" class="primary">inc</button></div>'),
        note="element moved into a wrapper and gained a class; semantics unchanged",
        expect_failure=False,
        extra={"why_green": "semantic addressing survives restructuring — a control"},
    ),
    # -- behavioural defects ----------------------------------------------
    CorpusItem(
        name="real_bug_element_removed",
        verdict="real_bug",
        mutate=_replace('<button id="add">add</button>', ""),
        note="the add button is gone; healing around this would hide a broken feature",
        expect_no_heal=True,
    ),
    CorpusItem(
        name="real_bug_wrong_value",
        verdict="real_bug",
        mutate=_replace("n += 1;", "n += 2;"),
        note="counter increments by 2; element is present, the behaviour is wrong",
        expect_no_heal=True,
    ),
    CorpusItem(
        name="real_bug_action_does_nothing",
        verdict="real_bug",
        mutate=_replace('document.getElementById("list").appendChild(li);', ""),
        note="add button no longer appends a row; the button itself is fine",
    ),
    # -- timing ------------------------------------------------------------
    CorpusItem(
        name="flaky_timing_slow_async",
        verdict="flaky_timing",
        mutate=_replace("}, 250);", "}, 12000);"),
        note="async result arrives after the step timeout but does arrive",
    ),
    # -- controls that must stay green -------------------------------------
    CorpusItem(
        name="control_reordered",
        verdict="none",
        mutate=_replace(
            '<input id="name" placeholder="name">\n    <button id="add">add</button>',
            '<button id="add">add</button>\n    <input id="name" placeholder="name">',
        ),
        note="pure reordering: reading this as a failure would make the tool unusable",
        expect_failure=False,
    ),
    CorpusItem(
        name="control_restyled",
        verdict="none",
        mutate=_replace('<button id="inc">inc</button>',
                        '<button id="inc" class="btn btn-lg accent">inc</button>'),
        note="classes changed only",
        expect_failure=False,
    ),
]


def by_name(name: str) -> CorpusItem:
    for item in ITEMS:
        if item.name == name:
            return item
    raise KeyError(name)
