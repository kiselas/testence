"""``ExpectedState.fields``: a stored entity holds these values, and a miss names the field.

Every scaffolded and documented oracle was "read once, diff two dicts", or a predicate
that failed with "expected predicate did not match" (product review 2026-09-28, P1-2).
"""

from __future__ import annotations

import pytest

from testence.api import Response
from testence.evidence import EvidenceWriter
from testence.oracle import ExpectedState, OracleFailed, verify_expected_state


def _json(body: str) -> Response:
    return Response(status=200, headers=[("Content-Type", "application/json")], body=body)


def _verify(tmp_path, body: str, expected: ExpectedState):
    writer = EvidenceWriter(tmp_path, run_id="r-fields", worker="")
    try:
        return verify_expected_state(
            writer,
            "t::fields",
            "widget",
            lambda: _json(body),
            expected,
            deadline_ms=200,
            poll_ms=50,
        )
    finally:
        writer.close()


SAVED = ExpectedState.fields("the widget is saved", {"name": "edge", "state": "saved"})


def test_extra_fields_of_the_entity_are_fine(tmp_path):
    body = '{"id": "w1", "name": "edge", "state": "saved", "revision": 3}'
    assert _verify(tmp_path, body, SAVED).outcome == "passed"


def test_a_false_green_names_the_field_expected_and_held(tmp_path):
    with pytest.raises(OracleFailed) as caught:
        _verify(tmp_path, '{"name": "edge", "state": "draft"}', SAVED)
    assert "state expected 'saved', the API has 'draft'" in str(caught.value)
    assert "name expected" not in str(caught.value)


def test_a_missing_field_reads_as_missing(tmp_path):
    with pytest.raises(OracleFailed) as caught:
        _verify(tmp_path, '{"name": "edge"}', SAVED)
    assert "state expected 'saved', the API has missing" in str(caught.value)


def test_a_boolean_is_not_a_number(tmp_path):
    expected = ExpectedState.fields("the flag is on", {"enabled": True})
    with pytest.raises(OracleFailed):
        _verify(tmp_path, '{"enabled": 1}', expected)


def test_bindings_still_apply(tmp_path):
    expected = ExpectedState.fields("saved", {"state": "saved"}, entity_id="w2")
    with pytest.raises(OracleFailed) as caught:
        _verify(tmp_path, '{"id": "w1", "state": "saved"}', expected)
    assert "wrong entity binding" in str(caught.value)


def test_an_empty_expectation_is_refused():
    with pytest.raises(ValueError, match="at least one field"):
        ExpectedState.fields("nothing", {})


def test_the_public_form_lists_the_fields():
    assert SAVED.public()["fields"] == {"name": "edge", "state": "saved"}
