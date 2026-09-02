"""Heal proposer: unit-level guarantees, independent of a browser.

The corpus (corpus/run.py) measures the same behaviour end to end; these tests pin
the decision rules so a regression is caught in a second rather than a minute.
"""

from __future__ import annotations

from typing import Any

from testence.engine import Target
from testence.triage.heal import MIN_SCORE, propose

SAVE_FP = {
    "tag": "button",
    "role": "button",
    "ariaLabel": None,
    "testid": None,
    "text": "Save",
    "id": "save",
    "classes": ["btn"],
}


class FakeEngine:
    """Only the two calls the proposer makes; keeps these tests browser-free."""

    def __init__(self, candidates: list[dict[str, Any]]) -> None:
        self._candidates = candidates

    def candidate_elements(self) -> list[dict[str, Any]]:
        return self._candidates


def _candidate(fingerprint: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    return {"fingerprint": fingerprint, "target": target}


def test_renamed_element_is_a_drift_with_a_new_address():
    renamed = dict(SAVE_FP, text="Store")
    engine = FakeEngine(
        [
            _candidate(renamed, {"kind": "role", "value": "button", "name": "Store"}),
            _candidate(
                {"tag": "a", "role": "link", "text": "Help", "id": "help", "classes": []},
                {"kind": "role", "value": "link", "name": "Help"},
            ),
        ]
    )
    proposal = propose(engine, "save the form", Target("role", "button", name="Save"), SAVE_FP)

    assert proposal is not None
    assert proposal.verdict_hint == "ui_change"
    assert proposal.new_target == {"kind": "role", "value": "button", "name": "Store"}
    assert proposal.score >= MIN_SCORE
    assert "text" in proposal.rationale
    assert "Target('role', 'button', name='Store')" in proposal.suggested_edit


def test_deleted_element_is_a_bug_and_gets_no_address():
    """The guardrail: healing around a removed control would hide a broken feature."""
    engine = FakeEngine(
        [
            _candidate(
                {
                    "tag": "a",
                    "role": "link",
                    "ariaLabel": None,
                    "testid": None,
                    "text": "Help",
                    "id": "help",
                    "classes": [],
                },
                {"kind": "role", "value": "link", "name": "Help"},
            ),
            _candidate(
                {
                    "tag": "input",
                    "role": "textbox",
                    "ariaLabel": None,
                    "testid": None,
                    "text": "",
                    "id": "query",
                    "classes": [],
                },
                {"kind": "role", "value": "textbox", "name": "query"},
            ),
        ]
    )
    proposal = propose(engine, "save the form", Target("role", "button", name="Save"), SAVE_FP)

    assert proposal is not None
    assert proposal.verdict_hint == "real_bug"
    assert proposal.new_target is None
    assert "gone" in proposal.rationale


def test_empty_page_is_a_bug_not_a_drift():
    proposal = propose(FakeEngine([]), "save", Target("css", "#save"), SAVE_FP)
    assert proposal is not None and proposal.verdict_hint == "real_bug"
    assert proposal.new_target is None


def test_no_baseline_means_no_opinion():
    """Without a green run to compare against, a proposal would be a guess."""
    engine = FakeEngine([_candidate(SAVE_FP, {"kind": "css", "value": "#save"})])
    assert propose(engine, "save", Target("css", "#save"), None) is None
    assert propose(engine, "save", Target("css", "#save"), {}) is None


def test_ambiguous_match_is_flagged_for_review():
    """Two candidates that agree on every weighted attribute: the proposer must
    still pick one, but a reviewer has to be told it was a coin flip."""
    unlabelled = {
        "tag": "button",
        "role": "button",
        "ariaLabel": None,
        "testid": None,
        "text": "Save",
        "id": None,
        "classes": [],
    }
    engine = FakeEngine(
        [
            _candidate(dict(unlabelled), {"kind": "role", "value": "button", "name": "Save"}),
            _candidate(
                dict(unlabelled), {"kind": "role", "value": "button", "name": "Save", "nth": 1}
            ),
        ]
    )
    proposal = propose(engine, "save", Target("role", "button", name="Save"), unlabelled)

    assert proposal is not None and proposal.new_target is not None
    assert proposal.ambiguous
    assert "review before accepting" in proposal.rationale


def test_testid_survives_a_full_rename():
    """A test id is the strongest identity signal: everything else may change."""
    known = dict(SAVE_FP, testid="save-btn")
    moved = {
        "tag": "a",
        "role": "link",
        "ariaLabel": "Persist",
        "testid": "save-btn",
        "text": "Persist",
        "id": "totally-different",
        "classes": ["x"],
    }
    engine = FakeEngine([_candidate(moved, {"kind": "testid", "value": "save-btn"})])
    proposal = propose(engine, "save", Target("testid", "save-btn"), known)

    assert proposal is not None and proposal.verdict_hint == "ui_change"
    assert proposal.new_target == {"kind": "testid", "value": "save-btn"}


def test_proposal_json_is_evidence_safe():
    engine = FakeEngine(
        [_candidate(dict(SAVE_FP, text="Store"), {"kind": "css", "value": "#save"})]
    )
    document = propose(engine, "save", Target("css", "#save"), SAVE_FP).to_json()
    assert set(document) >= {
        "intent",
        "old_target",
        "verdict_hint",
        "score",
        "new_target",
        "rationale",
        "suggested_edit",
    }
    assert len(document["considered"]) <= 5
