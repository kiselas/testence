"""Fail-closed validation of release decision manifests and their local evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from testence.benchmark import CorpusProtocolError, validate_corpus_registry
from testence.contracts.acceptance import AcceptanceReceiptError, validate_acceptance_receipt
from testence.contracts.document import DocumentError, load_document, validate_document
from testence.contracts.versions import RELEASE_MANIFEST_SCHEMA
from testence.managed_paths import ManagedPathError, checked_member

LEGACY_RELEASE_MANIFEST_SCHEMA = "testence/release-manifest/1"

ALPHA_REQUIRED_GATES = {"G1", "G2", "G3", "G5", "G6", "G8"}
ALPHA_REQUIRED_REQUIREMENTS = {
    "R01",
    "R02",
    "R03",
    "R04",
    "R05",
    "R06",
    "R07",
    "R08",
    "R09",
    "R10",
    "R11",
    "R12",
    "R15",
    "R16",
    "R18",
    "R19",
    "R20",
    "R21",
    "R22",
    "R24",
}


class ReleaseManifestError(ValueError):
    """A release manifest is malformed, incomplete, or points at invalid evidence."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _checked_file(root: Path, reference: dict[str, Any], *, label: str) -> dict[str, Any]:
    try:
        path = checked_member(root, reference["path"])
    except ManagedPathError as exc:
        raise ReleaseManifestError(f"unsafe {label} path {reference['path']!r}: {exc}") from exc
    if not path.is_file():
        raise ReleaseManifestError(f"{label} does not exist: {reference['path']}")
    size = path.stat().st_size
    digest = _sha256(path)
    if size != reference["bytes"] or digest != reference["sha256"]:
        raise ReleaseManifestError(
            f"{label} metadata mismatch for {reference['path']}: "
            f"expected {reference['bytes']} bytes/{reference['sha256']}, "
            f"observed {size} bytes/{digest}"
        )
    return {"path": str(path), "bytes": size, "sha256": digest}


def _payload_digest(document: dict[str, Any]) -> str:
    payload = dict(document)
    payload["owner_decision"] = None
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _check_set(
    items: list[dict[str, Any]],
    *,
    prefix: str,
    count: int,
    rc_sha: str | None,
    root: Path,
    verify_files: bool,
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    expected = {
        f"{prefix}{number:02d}" if prefix == "R" else f"{prefix}{number}"
        for number in range(1, count + 1)
    }
    ids = [item["id"] for item in items]
    if len(ids) != len(set(ids)) or set(ids) != expected:
        raise ReleaseManifestError(
            f"release manifest must contain every required {prefix} check exactly once"
        )
    checked_receipts: list[dict[str, Any]] = []
    for item in items:
        profiles = {receipt["profile"] for receipt in item["receipts"]}
        if item["status"] == "passed":
            if item["missing"]:
                raise ReleaseManifestError(
                    f"passed check {item['id']} must not list missing evidence"
                )
            if not item["receipts"]:
                raise ReleaseManifestError(f"passed check {item['id']} must reference evidence")
            missing_profiles = set(item["required_profiles"]) - profiles
            if missing_profiles:
                raise ReleaseManifestError(
                    f"passed check {item['id']} lacks profiles: {sorted(missing_profiles)}"
                )
            if rc_sha is None or any(
                receipt["candidate_sha"] != rc_sha for receipt in item["receipts"]
            ):
                raise ReleaseManifestError(
                    f"passed check {item['id']} is not bound to the exact RC SHA"
                )
        elif not item["missing"]:
            raise ReleaseManifestError(
                f"incomplete check {item['id']} must explain missing evidence"
            )
        if verify_files:
            for receipt in item["receipts"]:
                checked = _checked_file(root, receipt, label=f"receipt for {item['id']}")
                checked["profile"] = receipt["profile"]
                checked["candidate_sha"] = receipt["candidate_sha"]
                try:
                    validate_acceptance_receipt(
                        checked["path"],
                        expected_check=item["id"],
                        expected_profile=receipt["profile"],
                        expected_candidate_sha=receipt["candidate_sha"],
                    )
                except AcceptanceReceiptError as exc:
                    raise ReleaseManifestError(
                        f"invalid acceptance receipt for {item['id']}: {exc}"
                    ) from exc
                checked_receipts.append(checked)
    return {item["id"]: item["status"] for item in items}, checked_receipts


def _validate_legacy(document: dict[str, Any], root: Path, *, verify_files: bool) -> dict[str, Any]:
    gates = document["gates"]
    ids = [item["id"] for item in gates]
    if len(ids) != len(set(ids)) or set(ids) != {f"G{number}" for number in range(1, 9)}:
        raise ReleaseManifestError("legacy manifest must contain each of G1-G8 exactly once")
    for gate in gates:
        if gate["status"] == "passed" and (gate["missing"] or not gate["receipts"]):
            raise ReleaseManifestError(f"legacy passed gate {gate['id']} has incomplete evidence")
        if gate["status"] != "passed" and not gate["missing"]:
            raise ReleaseManifestError(f"legacy incomplete gate {gate['id']} lacks a reason")
    if document["decision"]["status"] == "go":
        raise ReleaseManifestError("legacy release manifests cannot authorize a release")
    artifacts: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    if verify_files:
        for relative in document["artifacts"]:
            try:
                path = checked_member(root, relative)
            except ManagedPathError as exc:
                raise ReleaseManifestError(f"unsafe artifact path {relative!r}: {exc}") from exc
            if not path.is_file():
                raise ReleaseManifestError(f"release artifact does not exist: {relative}")
            artifacts.append(
                {"path": str(path), "bytes": path.stat().st_size, "sha256": _sha256(path)}
            )
        for gate in gates:
            for relative in gate["receipts"]:
                try:
                    path = checked_member(root, relative)
                except ManagedPathError as exc:
                    raise ReleaseManifestError(f"unsafe receipt path {relative!r}: {exc}") from exc
                if not path.is_file():
                    raise ReleaseManifestError(f"release receipt does not exist: {relative}")
                receipts.append({"path": str(path), "sha256": _sha256(path)})
    return {
        "schema": LEGACY_RELEASE_MANIFEST_SCHEMA,
        "status": "no-go",
        "legacy": True,
        "ready_for_owner_decision": False,
        "gates": {item["id"]: item["status"] for item in gates},
        "artifacts": artifacts,
        "receipts": receipts,
    }


def validate_release_manifest(
    path: Path | str,
    *,
    repository_root: Path | str | None = None,
    verify_files: bool = True,
) -> dict[str, Any]:
    source = Path(path).resolve()
    root = (
        Path(repository_root).resolve(strict=True)
        if repository_root is not None
        else source.parent.parent.resolve(strict=True)
    )
    try:
        document = load_document(source)
        if not isinstance(document, dict):
            raise DocumentError("release manifest must be an object")
        schema = document.get("schema")
        filename = (
            "release-manifest-v1.schema.json"
            if schema == LEGACY_RELEASE_MANIFEST_SCHEMA
            else "release-manifest.schema.json"
        )
        validate_document(document, filename)
    except DocumentError as exc:
        raise ReleaseManifestError(str(exc)) from exc
    if document.get("schema") == LEGACY_RELEASE_MANIFEST_SCHEMA:
        return _validate_legacy(document, root, verify_files=verify_files)
    if document.get("schema") != RELEASE_MANIFEST_SCHEMA:
        raise ReleaseManifestError("unsupported release manifest schema")

    candidate = document["candidate"]
    rc_sha = candidate["rc_sha"]
    gate_statuses, gate_receipts = _check_set(
        document["gates"],
        prefix="G",
        count=8,
        rc_sha=rc_sha,
        root=root,
        verify_files=verify_files,
    )
    requirement_statuses, requirement_receipts = _check_set(
        document["requirements"],
        prefix="R",
        count=24,
        rc_sha=rc_sha,
        root=root,
        verify_files=verify_files,
    )

    artifacts: list[dict[str, Any]] = []
    if len({item["path"] for item in document["artifacts"]}) != len(document["artifacts"]):
        raise ReleaseManifestError("release artifact paths must be unique")
    if verify_files:
        artifacts = [
            _checked_file(root, item, label="release artifact") for item in document["artifacts"]
        ]
        dependency = _checked_file(
            root, document["inputs"]["dependency_inventory"], label="dependency inventory"
        )
        corpus = _checked_file(root, document["inputs"]["corpus_registry"], label="corpus registry")
        try:
            corpus_result = validate_corpus_registry(corpus["path"], repository_root=root)
        except CorpusProtocolError as exc:
            raise ReleaseManifestError(f"release corpus is invalid: {exc}") from exc
        if corpus_result["digest"] != document["inputs"]["corpus_digest"]:
            raise ReleaseManifestError("release corpus digest differs from the frozen registry")
    else:
        dependency = {}
        corpus = {}

    release_profile = document.get("release_profile", "r1")
    required_gates = ALPHA_REQUIRED_GATES if release_profile == "alpha" else set(gate_statuses)
    required_requirements = (
        ALPHA_REQUIRED_REQUIREMENTS if release_profile == "alpha" else set(requirement_statuses)
    )
    ready = bool(
        rc_sha
        and candidate["tag"]
        and not candidate["dirty_worktree"]
        and not document["exemptions"]
        and all(gate_statuses[item] == "passed" for item in required_gates)
        and all(requirement_statuses[item] == "passed" for item in required_requirements)
    )
    if document["machine_readiness"] is not ready:
        raise ReleaseManifestError(
            f"machine_readiness must equal computed readiness ({str(ready).lower()})"
        )

    decision = document["owner_decision"]
    if decision is not None:
        expected_payload = _payload_digest(document)
        if decision["payload_digest"] != expected_payload:
            raise ReleaseManifestError("owner decision is not bound to this manifest payload")
        if verify_files:
            _checked_file(root, decision["receipt"], label="owner decision receipt")
        if decision["status"] == "go":
            if not ready:
                raise ReleaseManifestError("go requires a complete clean release candidate")
            if (
                decision["receipt"]["profile"] != "external"
                or decision["receipt"]["candidate_sha"] != rc_sha
            ):
                raise ReleaseManifestError(
                    "go owner receipt must be external and bound to the RC SHA"
                )

    status = "go" if decision is not None and decision["status"] == "go" else "no-go"
    return {
        "schema": RELEASE_MANIFEST_SCHEMA,
        "release_profile": release_profile,
        "status": status,
        "legacy": False,
        "ready_for_owner_decision": ready,
        "payload_digest": _payload_digest(document),
        "gates": gate_statuses,
        "requirements": requirement_statuses,
        "artifacts": artifacts,
        "receipts": gate_receipts + requirement_receipts,
        "inputs": {"dependency_inventory": dependency, "corpus_registry": corpus},
    }


__all__ = [
    "LEGACY_RELEASE_MANIFEST_SCHEMA",
    "ReleaseManifestError",
    "validate_release_manifest",
]
