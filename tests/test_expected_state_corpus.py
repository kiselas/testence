from __future__ import annotations

import json
from pathlib import Path

import pytest

from testence.api import Response
from testence.oracle import ExpectedState, observe_expected_state

CORPUS = json.loads(
    (Path(__file__).parents[1] / "corpus" / "expected-state-v1.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize("case", CORPUS["cases"], ids=lambda case: case["id"])
def test_expected_state_corpus(case):
    documents = iter(case["responses"])
    last = case["responses"][-1]

    def read():
        document = next(documents, last)
        body = document["body"]
        text = body if isinstance(body, str) else json.dumps(body)
        return Response(
            document["status"],
            [("content-type", document.get("content_type", "application/json"))],
            text,
        )

    expected = ExpectedState(
        "widget 42 is durably saved",
        lambda body: body["state"] == "saved",
        entity_id="widget-42",
        actor_role="editor",
        correlation_id="run-7",
        minimum_revision=2,
        stability_ms=case.get("stability_ms", 0),
    )
    observed = observe_expected_state(
        read,
        expected,
        deadline_ms=case.get("deadline_ms", 0),
        poll_ms=1,
    )

    assert observed.outcome == case["expected"]
