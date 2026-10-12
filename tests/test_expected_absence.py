"""Proving that something is gone (product review 2026-09-28, P0-6).

An empty answer was always inconclusive, so "the UI says deleted, the row is still
there" could not be caught and the honest version of the check could never pass.
"""

from __future__ import annotations

import pytest

from testence.api import Response
from testence.evidence import EvidenceWriter
from testence.oracle import ExpectedState, OracleInconclusive, verify_expected_state

GONE = ExpectedState.absent("the widget is deleted")


def _response(status: int, body: str = "", content_type: str = "application/json") -> Response:
    return Response(status=status, headers=[("Content-Type", content_type)], body=body)


def _check(tmp_path, response: Response):
    writer = EvidenceWriter(tmp_path, run_id="r-absence", worker="")
    try:
        return verify_expected_state(
            writer, "t::absence", "widget gone", lambda: response, GONE, deadline_ms=300, poll_ms=50
        )
    finally:
        writer.close()


@pytest.mark.parametrize(
    "response",
    [
        _response(404),
        _response(404, '{"detail": "not found"}'),
        _response(404, "Not Found", "text/plain"),
        _response(200, "[]"),
        _response(200, "{}"),
    ],
    ids=["404-empty", "404-json", "404-text", "empty-list", "empty-object"],
)
def test_an_empty_or_not_found_read_proves_absence(tmp_path, response):
    assert _check(tmp_path, response).outcome == "passed"


def test_a_row_that_is_still_there_is_a_violation(tmp_path):
    with pytest.raises(AssertionError) as caught:
        _check(tmp_path, _response(200, '{"id": "w1", "name": "still here"}'))
    assert not isinstance(caught.value, OracleInconclusive)


@pytest.mark.parametrize(
    "response",
    [
        _response(401, '{"detail": "not authenticated"}'),
        _response(404, "<!doctype html><h1>Not found</h1>", "text/html"),
        _response(200, "not json", "text/plain"),
    ],
    ids=["unauthenticated", "html-404", "non-json"],
)
def test_a_read_that_cannot_answer_stays_inconclusive(tmp_path, response):
    with pytest.raises(OracleInconclusive):
        _check(tmp_path, response)


def test_an_ordinary_expected_state_still_refuses_empty_reads(tmp_path):
    writer = EvidenceWriter(tmp_path, run_id="r-absence", worker="")
    present = ExpectedState("the widget exists", lambda value: bool(value))
    try:
        with pytest.raises(OracleInconclusive):
            verify_expected_state(
                writer,
                "t::present",
                "widget",
                lambda: _response(200, "[]"),
                present,
                deadline_ms=200,
                poll_ms=50,
            )
    finally:
        writer.close()


def _check_bound(tmp_path, response: Response):
    writer = EvidenceWriter(tmp_path, run_id="r-absence", worker="")
    expected = ExpectedState.absent("widget w7 is gone", entity_id="w7")
    try:
        return verify_expected_state(
            writer, "t::bound", "w7 gone", lambda: response, expected, deadline_ms=300, poll_ms=50
        )
    finally:
        writer.close()


@pytest.mark.parametrize(
    "response",
    [_response(404, '{"detail": "not found"}'), _response(200, "[]"), _response(200, "{}")],
    ids=["404-json", "empty-list", "empty-object"],
)
def test_absence_bound_to_an_entity_passes_on_an_empty_read(tmp_path, response):
    """`oracle suggest` writes `ExpectedState.absent(..., entity_id=...)` for a DELETE.
    The binding was checked first, an empty answer has no `id`, so it never passed."""
    assert _check_bound(tmp_path, response).outcome == "passed"


@pytest.mark.parametrize("body", ['{"id": "w7", "name": "x"}', '{"id": "w8", "name": "x"}'])
def test_absence_bound_to_an_entity_still_fails_on_a_present_row(tmp_path, body):
    with pytest.raises(AssertionError) as caught:
        _check_bound(tmp_path, _response(200, body))
    assert not isinstance(caught.value, OracleInconclusive)
