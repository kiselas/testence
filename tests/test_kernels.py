"""Kernel conformance suite.

Every registered backend runs these tests. When a native backend appears, it is
added to ``BACKENDS`` and must pass unchanged — that is the whole contract: the
reference implementation defines correctness, native ones only change speed.
"""

from __future__ import annotations

import json

import pytest

from testence import kernels
from testence.kernels import reference
from testence.kernels.contracts import KERNEL_ABI

BACKENDS = [reference]  # + native backend when installed


@pytest.fixture(params=BACKENDS, ids=lambda b: b.name)
def backend(request):
    previous = kernels.use_backend(request.param)
    yield request.param
    kernels.use_backend(previous)


def test_backend_declares_matching_abi(backend):
    assert backend.abi == KERNEL_ABI


def test_parse_ledger_roundtrip(backend):
    data = b"\n".join(
        [
            json.dumps({"v": "testence/1", "kind": "run.start", "seq": 1}).encode(),
            b"",  # blank lines are skipped, not an error
            json.dumps({"v": "testence/1", "kind": "note", "seq": 2, "text": "кир"}).encode(),
        ]
    )
    events = kernels.parse_ledger(data)
    assert [e["seq"] for e in events] == [1, 2]
    assert events[1]["text"] == "кир"


def test_parse_ledger_rejects_malformed(backend):
    with pytest.raises(ValueError):
        kernels.parse_ledger(b'{"v": "testence/1"}\n{not json}')


def test_estimate_tokens_monotonic_and_positive(backend):
    assert kernels.estimate_tokens("") >= 1
    assert kernels.estimate_tokens("word " * 100) > kernels.estimate_tokens("word")


def test_percentiles_semantics(backend):
    assert kernels.percentiles([], [50, 95]) == [None, None]
    assert kernels.percentiles([10.0], [50]) == [10.0]
    assert kernels.percentiles([100.0, 200.0, 300.0], [50]) == [200.0]
    p50, p95 = kernels.percentiles([1.0, 2.0, 3.0, 4.0], [50, 95])
    assert p50 < p95


def test_diff_aria_detects_added_and_removed(backend):
    before = '- button "save"\n- textbox "name"'
    after = '- button "save"\n- textbox "name"\n- alert "error"'
    diff = kernels.diff_aria(before, after)
    assert diff["added"] == [{"depth": 0, "role": "alert", "name": "error"}]
    assert diff["removed"] == []
    assert diff["same"] == 2


def test_diff_aria_identical_is_empty(backend):
    snapshot = '- button "a"\n  - text "b"'
    diff = kernels.diff_aria(snapshot, snapshot)
    assert diff["added"] == [] and diff["removed"] == []
    assert diff["same"] == 2


def test_diff_aria_reorder_is_moved_not_disappeared(backend):
    """A triage agent must not read reordering as an element vanishing —
    'gone' means real_bug, 'moved' does not."""
    before = '- button "a"\n- button "b"\n- button "c"'
    after = '- button "c"\n- button "a"\n- button "b"'
    diff = kernels.diff_aria(before, after)
    assert diff["removed"] == []
    assert diff["added"] == []
    assert diff["moved"] >= 1


def test_score_candidates_ranks_exact_match_first(backend):
    target = {
        "tag": "button",
        "role": "button",
        "ariaLabel": "save",
        "testid": "save-btn",
        "text": "Save",
        "id": "save",
        "classes": ["btn"],
    }
    candidates = [
        {
            "tag": "div",
            "role": None,
            "ariaLabel": None,
            "testid": None,
            "text": "unrelated",
            "id": "x",
            "classes": ["card"],
        },
        dict(target),
        {
            "tag": "button",
            "role": "button",
            "ariaLabel": "save",
            "testid": None,
            "text": "Save",
            "id": "save2",
            "classes": ["btn"],
        },
    ]
    scores = kernels.score_candidates(target, candidates)
    assert scores[1] == max(scores)
    assert scores[1] > scores[2] > scores[0]
    assert all(0.0 <= s <= 1.0 for s in scores)


def test_score_candidates_empty_list(backend):
    assert kernels.score_candidates({"tag": "button"}, []) == []


def test_active_backend_reported(backend):
    info = kernels.active_backend()
    assert info == {"name": backend.name, "abi": backend.abi}


def test_kernels_are_pure(backend):
    """Same input twice → identical output (no hidden state between calls)."""
    before, after = '- button "a"', '- button "b"'
    assert kernels.diff_aria(before, after) == kernels.diff_aria(before, after)
    target = {"tag": "button", "text": "x"}
    cands = [{"tag": "button", "text": "y"}]
    assert kernels.score_candidates(target, cands) == kernels.score_candidates(target, cands)
