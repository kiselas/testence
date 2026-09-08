"""Validation for the frozen R1 correctness corpus and its acceptance boundary."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .contracts.document import DocumentError, load_document, validate_document
from .managed_paths import ManagedPathError, checked_member

CORPUS_REGISTRY_SCHEMA = "testence/correctness-corpus/2"
CORPUS_FREEZE_SCHEMA = "testence/correctness-corpus-freeze/1"
REQUIRED_STRATA = {
    "product_defect": 20,
    "healthy_control": 10,
    "repairable_drift": 5,
    "ambiguous_infrastructure": 5,
}
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


class CorpusProtocolError(ValueError):
    """The frozen corpus registry violates its public protocol."""


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _corpus_digest(document: dict[str, Any]) -> str:
    """Hash the immutable experiment definition, excluding evolving acceptance receipts."""
    frozen = {"revision": document["revision"], "cases": document["cases"]}
    raw = json.dumps(frozen, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return "sha256:" + _sha256(raw)


def _member(root: Path, relative: str, *, label: str) -> Path:
    try:
        path = checked_member(root, relative)
    except ManagedPathError as exc:
        raise CorpusProtocolError(f"unsafe {label} path {relative!r}: {exc}") from exc
    if not path.is_file():
        raise CorpusProtocolError(f"missing {label}: {relative}")
    return path


def _validate_receipt(
    root: Path, item: dict[str, Any], *, receipt_key: str, digest_key: str, label: str
) -> None:
    relative = item[receipt_key]
    receipt = _member(root, relative, label=label)
    actual = _sha256(receipt.read_bytes())
    if actual != item[digest_key]:
        raise CorpusProtocolError(
            f"{label} digest mismatch for {relative}: expected {item[digest_key]}, actual {actual}"
        )


def validate_corpus_registry(
    path: Path | str, *, repository_root: Path | str | None = None
) -> dict[str, Any]:
    source = Path(path).resolve()
    try:
        document = load_document(source)
        validate_document(document, "correctness-corpus.schema.json")
    except (DocumentError, OSError) as exc:
        raise CorpusProtocolError(f"cannot validate corpus registry {source}: {exc}") from exc
    if not isinstance(document, dict) or document.get("schema") != CORPUS_REGISTRY_SCHEMA:
        raise CorpusProtocolError("unsupported correctness corpus schema")

    root = (
        Path(repository_root).resolve(strict=True)
        if repository_root is not None
        else source.parent.parent.resolve(strict=True)
    )
    cases = document["cases"]
    ids: set[str] = set()
    counts: Counter[str] = Counter()
    holdout = 0
    source_files: dict[str, tuple[int, str]] = {}
    for case in cases:
        case_id = case["id"]
        if case_id in ids:
            raise CorpusProtocolError(f"duplicate corpus case id: {case_id!r}")
        ids.add(case_id)
        counts[case["stratum"]] += 1
        holdout += int(case["split"] == "holdout")

        relative = case["source"]
        candidate = _member(root, relative, label=f"source for {case_id}")
        raw = candidate.read_bytes()
        actual = _sha256(raw)
        if actual != case["source_sha256"]:
            raise CorpusProtocolError(
                f"source digest mismatch for {case_id}: "
                f"expected {case['source_sha256']}, actual {actual}"
            )
        try:
            searchable = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CorpusProtocolError(f"source for {case_id} is not UTF-8: {relative}") from exc
        if case["selector"] not in searchable:
            raise CorpusProtocolError(
                f"selector for {case_id} is absent from {relative}: {case['selector']!r}"
            )
        source_files[relative] = (len(raw), actual)

    if dict(counts) != REQUIRED_STRATA:
        raise CorpusProtocolError(
            f"corpus strata must equal {REQUIRED_STRATA}, observed {dict(counts)}"
        )
    if holdout < 8:
        raise CorpusProtocolError("frozen corpus needs at least eight holdout cases")

    corpus_digest = _corpus_digest(document)
    freeze_path = _member(root, document["freeze_manifest"], label="freeze manifest")
    try:
        freeze = load_document(freeze_path)
        validate_document(freeze, "correctness-corpus-freeze.schema.json")
    except (DocumentError, OSError) as exc:
        raise CorpusProtocolError(f"invalid corpus freeze manifest: {exc}") from exc
    if not isinstance(freeze, dict) or freeze["corpus_digest"] != corpus_digest:
        raise CorpusProtocolError("freeze manifest corpus digest does not match the registry")
    frozen_files = {entry["path"]: entry for entry in freeze["files"]}
    if len(frozen_files) != len(freeze["files"]):
        raise CorpusProtocolError("freeze manifest contains duplicate input paths")
    if set(frozen_files) != set(source_files):
        raise CorpusProtocolError(
            "freeze manifest inputs differ from case sources: "
            f"expected {sorted(source_files)}, observed {sorted(frozen_files)}"
        )
    for relative, (size, digest) in source_files.items():
        entry = frozen_files[relative]
        if entry["bytes"] != size or entry["sha256"] != digest:
            raise CorpusProtocolError(f"freeze metadata mismatch for {relative}")

    accepted_targets: list[dict[str, Any]] = []
    target_ids: set[str] = set()
    repositories: set[str] = set()
    for target in document["oss_targets"]:
        if target["id"] in target_ids or target["repository"] in repositories:
            raise CorpusProtocolError("OSS acceptance targets must be distinct")
        target_ids.add(target["id"])
        repositories.add(target["repository"])
        if not _COMMIT.fullmatch(target["commit"]):
            raise CorpusProtocolError(f"target {target['id']} must pin a full lowercase commit SHA")
        _validate_receipt(
            root,
            target,
            receipt_key="reproduction_receipt",
            digest_key="receipt_sha256",
            label=f"reproduction receipt for {target['id']}",
        )
        accepted_targets.append(target)

    review = document["independent_review"]
    reviews = review["reviews"]
    reviewer_ids: set[str] = set()
    for item in reviews:
        if item["reviewer_id"] in reviewer_ids:
            raise CorpusProtocolError("independent reviewer identities must be distinct")
        reviewer_ids.add(item["reviewer_id"])
        if item["scope_digest"] != corpus_digest:
            raise CorpusProtocolError(
                f"review {item['reviewer_id']} is not bound to the frozen corpus"
            )
        _validate_receipt(
            root,
            item,
            receipt_key="receipt",
            digest_key="receipt_sha256",
            label=f"independent review receipt for {item['reviewer_id']}",
        )

    review_complete = len(reviews) >= 2
    acceptance_ready = len(accepted_targets) >= 2 and review_complete
    return {
        "schema": CORPUS_REGISTRY_SCHEMA,
        "status": "accepted" if acceptance_ready else "incomplete",
        "registry": str(source),
        "digest": corpus_digest,
        "freeze_manifest": str(freeze_path),
        "cases": len(cases),
        "strata": dict(counts),
        "holdout": holdout,
        "oss_targets": len(accepted_targets),
        "independent_review": review_complete,
        "acceptance_ready": acceptance_ready,
    }


__all__ = [
    "CORPUS_FREEZE_SCHEMA",
    "CORPUS_REGISTRY_SCHEMA",
    "REQUIRED_STRATA",
    "CorpusProtocolError",
    "validate_corpus_registry",
]
