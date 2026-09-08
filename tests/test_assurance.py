from __future__ import annotations

from copy import deepcopy

from testence.assurance import POLICY_DIGEST
from testence.export._model import LoadedRun


def _events(*assertions: dict, status: str = "passed", inventory: list[dict] | None = None):
    plan_digest = "sha256:" + "a" * 64
    base = {
        "v": "testence/2",
        "run": "r-proof",
        "run_id": "r-proof",
        "project_id": "shop",
        "worker": "controller",
        "test": "tests/test_checkout.py::test_checkout",
        "case_id": "checkout",
        "variant_id": "default",
        "attempt_id": "attempt-controller-1",
        "proof_id": "proof-checkout",
        "parameters": {},
    }
    declared = inventory or [
        {
            "id": "assert.checkout.persisted",
            "claim_id": "checkout.persisted",
            "oracle": "api",
            "required": True,
        }
    ]
    documents = [
        {
            **base,
            "event_id": "controller:1",
            "seq": 1,
            "kind": "test.start",
            "assertions": deepcopy(declared),
            "plan": {"id": "checkout", "digest": plan_digest},
            "plan_digest": plan_digest,
            "test_digest": "sha256:" + "b" * 64,
            "policy_digest": POLICY_DIGEST,
        }
    ]
    for index, assertion in enumerate(assertions, start=2):
        documents.append(
            {
                **base,
                "event_id": f"controller:{index}",
                "seq": index,
                "kind": "assertion",
                **assertion,
            }
        )
    documents.append(
        {
            **base,
            "event_id": f"controller:{len(documents) + 1}",
            "seq": len(documents) + 1,
            "kind": "test.end",
            "status": status,
        }
    )
    return documents


def _assertion(outcome: str = "passed") -> dict:
    return {
        "assertion_id": "assert.checkout.persisted",
        "claim_id": "checkout.persisted",
        "oracle_kind": "api",
        "outcome": outcome,
        "expected": {"id": 42},
        "actual": {"id": 42 if outcome == "passed" else None},
        "source": "tests/test_checkout.py:20",
    }


def test_passed_execution_without_required_proof_is_unverified():
    test = LoadedRun.from_events(_events()).tests[0]

    assert test.status == "passed"
    assert test.assurance == "unverified"
    assert "missing required assertions" in test.assurance_reasons[0]


def test_all_required_assertions_and_digests_make_assurance_verified():
    test = LoadedRun.from_events(_events(_assertion())).tests[0]

    assert test.status == "passed"
    assert test.assurance == "verified"
    assert test.assurance_reasons == ()


def test_failed_assertion_violates_assurance_without_rewriting_execution():
    test = LoadedRun.from_events(_events(_assertion("failed"))).tests[0]

    assert test.status == "passed"
    assert test.assurance == "violated"


def test_optional_assertion_does_not_increase_required_denominator():
    optional = {
        "id": "assert.checkout.cosmetic",
        "claim_id": "checkout.persisted",
        "oracle": "visual",
        "required": False,
    }
    event = {
        **_assertion(),
        "assertion_id": "assert.checkout.cosmetic",
        "oracle_kind": "visual",
    }
    test = LoadedRun.from_events(
        _events(_assertion(), event, inventory=[*_events()[0]["assertions"], optional])
    ).tests[0]

    assert test.assurance == "verified"


def test_stale_plan_digest_and_duplicate_assertion_fail_closed():
    events = _events(_assertion(), _assertion())
    events[0]["plan"]["digest"] = "sha256:" + "c" * 64

    test = LoadedRun.from_events(events).tests[0]

    assert test.assurance == "unverified"
    assert any("duplicate assertions" in reason for reason in test.assurance_reasons)
    assert any("plan_digest" in reason for reason in test.assurance_reasons)


def test_unknown_failed_assertion_cannot_claim_a_product_violation():
    unknown = {
        **_assertion("failed"),
        "assertion_id": "assert.unknown",
        "claim_id": "claim.unknown",
    }

    test = LoadedRun.from_events(_events(unknown)).tests[0]

    assert test.status == "passed"
    assert test.assurance == "unverified"
    assert any("unknown assertions" in reason for reason in test.assurance_reasons)
