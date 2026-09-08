from __future__ import annotations

import json

import pytest

from testence.contracts import AcceptanceReceiptError, validate_acceptance_receipt


def _receipt() -> dict:
    return {
        "schema": "testence/acceptance-receipt/1",
        "task_ids": ["S3-09"],
        "check_ids": ["WHEEL-06"],
        "profile": "rc",
        "evidence_kind": "hosted_ci",
        "producer": {"tool": "pytest", "version": "8.4.2", "runner": "github-hosted"},
        "source": {
            "candidate_sha": "a" * 40,
            "dirty": False,
            "materialized_digest": "sha256:" + "b" * 64,
        },
        "subjects": [],
        "environment": {"os": "linux", "python": "3.12"},
        "command": {
            "argv": ["python", "-m", "pytest"],
            "cwd_profile": "fresh-checkout",
            "started_at": "2026-09-07T10:00:00Z",
            "finished_at": "2026-09-07T10:01:00Z",
            "exit_code": 0,
        },
        "expected": {"status": "passed"},
        "observed": {"status": "passed"},
        "status": "passed",
        "skipped": [],
        "limitations": [],
        "artifacts": [],
        "review": None,
    }


def _write(tmp_path, document: dict):
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_acceptance_receipt_binds_check_profile_and_candidate(tmp_path):
    result = validate_acceptance_receipt(
        _write(tmp_path, _receipt()),
        expected_check="WHEEL-06",
        expected_profile="rc",
        expected_candidate_sha="a" * 40,
    )
    assert result["status"] == "passed"


def test_rc_acceptance_receipt_rejects_dirty_or_foreign_source(tmp_path):
    document = _receipt()
    document["source"]["dirty"] = True
    with pytest.raises(AcceptanceReceiptError, match="clean candidate"):
        validate_acceptance_receipt(_write(tmp_path, document))

    document["source"]["dirty"] = False
    with pytest.raises(AcceptanceReceiptError, match="another candidate"):
        validate_acceptance_receipt(_write(tmp_path, document), expected_candidate_sha="c" * 40)


def test_passed_receipt_cannot_hide_a_skip(tmp_path):
    document = _receipt()
    document["skipped"] = [{"id": "link-case", "reason": "privilege unavailable"}]
    with pytest.raises(AcceptanceReceiptError, match="cannot contain skipped"):
        validate_acceptance_receipt(_write(tmp_path, document))
