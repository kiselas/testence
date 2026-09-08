"""Semantic validation for release acceptance receipts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .document import DocumentError, load_document, validate_document
from .versions import ACCEPTANCE_RECEIPT_SCHEMA


class AcceptanceReceiptError(ValueError):
    pass


def validate_acceptance_receipt(
    path: Path | str,
    *,
    expected_check: str | None = None,
    expected_profile: str | None = None,
    expected_candidate_sha: str | None = None,
) -> dict[str, Any]:
    try:
        document = load_document(path)
        if not isinstance(document, dict):
            raise DocumentError("acceptance receipt must be an object")
        validate_document(document, "acceptance-receipt.schema.json")
    except DocumentError as exc:
        raise AcceptanceReceiptError(str(exc)) from exc
    if document["schema"] != ACCEPTANCE_RECEIPT_SCHEMA:
        raise AcceptanceReceiptError("unsupported acceptance receipt schema")
    if expected_check is not None and expected_check not in document["check_ids"]:
        raise AcceptanceReceiptError(f"receipt does not cover check {expected_check}")
    if expected_profile is not None and document["profile"] != expected_profile:
        raise AcceptanceReceiptError(
            f"receipt profile {document['profile']!r} differs from {expected_profile!r}"
        )
    source = document["source"]
    if expected_candidate_sha is not None and source["candidate_sha"] != expected_candidate_sha:
        raise AcceptanceReceiptError("receipt is bound to another candidate SHA")
    if document["profile"] in {"rc", "external"} and (
        source["candidate_sha"] is None or source["dirty"]
    ):
        raise AcceptanceReceiptError("RC/external receipt requires a clean candidate SHA")
    executed = document["evidence_kind"] in {"unit", "negative_probe", "consumer", "hosted_ci"}
    if executed and document["command"] is None:
        raise AcceptanceReceiptError("executed evidence requires command timing and exit status")
    external = document["evidence_kind"] in {"external_review", "pilot"}
    if external and document["review"] is None:
        raise AcceptanceReceiptError("external evidence requires a scoped review record")
    if document["status"] == "passed" and document["skipped"]:
        raise AcceptanceReceiptError("passed acceptance receipt cannot contain skipped checks")
    return document


__all__ = ["AcceptanceReceiptError", "validate_acceptance_receipt"]
