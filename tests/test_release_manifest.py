from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from testence.cli import main
from testence.contracts import DocumentError, loads_document
from testence.release import ReleaseManifestError, validate_release_manifest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "release/rc-manifest.json"
MANIFEST_V2 = ROOT / "release/rc-manifest-v2.json"


def _document() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _document_v2() -> dict:
    return json.loads(MANIFEST_V2.read_text(encoding="utf-8"))


def _write(tmp_path: Path, document: dict) -> Path:
    release = tmp_path / "release"
    release.mkdir(parents=True)
    path = release / "manifest.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_historical_release_manifest_is_strict_valid_but_remains_no_go(capsys):
    # Historical evidence lives in retained local/CI bundles, not in source control.
    result = validate_release_manifest(MANIFEST, repository_root=ROOT, verify_files=False)

    assert result["status"] == "no-go"
    assert result["ready_for_owner_decision"] is False
    assert set(result["gates"]) == {f"G{number}" for number in range(1, 9)}
    assert (
        main(
            [
                "release",
                "validate",
                str(MANIFEST),
                "--root",
                str(ROOT),
                "--structure-only",
                "--json",
            ]
        )
        == 3
    )
    assert json.loads(capsys.readouterr().out)["status"] == "no-go"


def test_v2_alpha_manifest_is_ready_and_owner_approved():
    result = validate_release_manifest(MANIFEST_V2, repository_root=ROOT, verify_files=False)

    assert result["schema"] == "testence/release-manifest/2"
    assert result["legacy"] is False
    assert result["release_profile"] == "alpha"
    assert result["ready_for_owner_decision"] is True
    assert result["status"] == "go"
    assert len(result["requirements"]) == 24


def test_legacy_manifest_checks_real_artifacts_and_receipts(tmp_path):
    document = _document()
    artifact = tmp_path / "artifact.json"
    artifact.write_text("{}", encoding="utf-8")
    receipt = tmp_path / "receipt.json"
    receipt.write_text("synthetic unit-test receipt", encoding="utf-8")
    document["artifacts"] = [artifact.name]
    for gate in document["gates"]:
        gate["receipts"] = [receipt.name]
    path = _write(tmp_path, document)
    result = validate_release_manifest(path, repository_root=tmp_path)
    assert result["artifacts"] and result["receipts"]
    receipt.unlink()
    with pytest.raises(ReleaseManifestError, match="receipt does not exist"):
        validate_release_manifest(path, repository_root=tmp_path)


def test_v2_checks_actual_bytes_and_rejects_tampered_or_missing_artifacts(tmp_path, monkeypatch):
    document = _document_v2()
    artifact = tmp_path / "artifact.json"
    artifact.write_bytes(b"{}")
    reference = {"path": artifact.name, "bytes": 2, "sha256": hashlib.sha256(b"{}").hexdigest()}
    document["artifacts"] = [reference]
    document["inputs"]["dependency_inventory"] = reference
    document["inputs"]["corpus_registry"] = reference
    for check in [*document["gates"], *document["requirements"]]:
        check["receipts"] = []
        check["status"] = "incomplete"
        check["missing"] = ["isolated file-integrity fixture"]
    document["machine_readiness"] = False
    document["owner_decision"] = None
    # Corpus semantics have their own tests. Isolate this test to file integrity.
    monkeypatch.setattr(
        "testence.release.validate_corpus_registry",
        lambda *args, **kwargs: {"digest": document["inputs"]["corpus_digest"]},
    )
    path = _write(tmp_path, document)
    result = validate_release_manifest(path, repository_root=tmp_path)
    assert result["artifacts"][0]["sha256"] == reference["sha256"]
    artifact.write_bytes(b"[]")
    with pytest.raises(ReleaseManifestError, match="metadata mismatch"):
        validate_release_manifest(path, repository_root=tmp_path)
    artifact.unlink()
    with pytest.raises(ReleaseManifestError, match="does not exist"):
        validate_release_manifest(path, repository_root=tmp_path)


def test_clean_complete_v2_fixture_requires_an_exact_bound_owner_decision(tmp_path):
    document = _document_v2()
    rc_sha = document["candidate"]["base_sha"]
    document["candidate"].update(rc_sha=rc_sha, tag="v0.1.0a1", dirty_worktree=False)
    for check in [*document["requirements"], *document["gates"]]:
        check["status"] = "passed"
        check["missing"] = []
        check["receipts"] = [
            {
                "path": "synthetic/receipt.json",
                "bytes": 2,
                "sha256": hashlib.sha256(b"{}").hexdigest(),
                "profile": profile,
                "candidate_sha": rc_sha,
            }
            for profile in check["required_profiles"]
        ]
    document["machine_readiness"] = True
    document["owner_decision"] = None
    payload = dict(document)
    payload["owner_decision"] = None
    digest = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    document["owner_decision"] = {
        "status": "go",
        "owner": "synthetic-owner",
        "reason": "validator fixture only",
        "payload_digest": digest,
        "receipt": {
            "path": "synthetic/owner.json",
            "bytes": 2,
            "sha256": hashlib.sha256(b"{}").hexdigest(),
            "profile": "external",
            "candidate_sha": rc_sha,
        },
    }
    path = _write(tmp_path, document)

    result = validate_release_manifest(path, repository_root=ROOT, verify_files=False)

    assert result["ready_for_owner_decision"] is True
    assert result["status"] == "go"

    document["owner_decision"]["payload_digest"] = "sha256:" + "0" * 64
    path = _write(tmp_path / "stale", document)
    with pytest.raises(ReleaseManifestError, match="not bound"):
        validate_release_manifest(path, repository_root=ROOT, verify_files=False)


def test_alpha_profile_defers_only_non_alpha_checks(tmp_path):
    document = _document_v2()
    rc_sha = document["candidate"]["base_sha"]
    document["release_profile"] = "alpha"
    document["candidate"].update(
        version="0.1.0a1", rc_sha=rc_sha, tag="v0.1.0a1", dirty_worktree=False
    )
    required = {
        "G1",
        "G2",
        "G3",
        "G5",
        "G6",
        "G8",
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
    for check in [*document["requirements"], *document["gates"]]:
        if check["id"] in required:
            check["status"] = "passed"
            check["missing"] = []
            check["receipts"] = [
                {
                    "path": "synthetic/receipt.json",
                    "bytes": 2,
                    "sha256": hashlib.sha256(b"{}").hexdigest(),
                    "profile": "rc",
                    "candidate_sha": rc_sha,
                }
            ]
            check["required_profiles"] = ["rc"]
    document["machine_readiness"] = True
    document["owner_decision"] = None
    path = _write(tmp_path, document)
    assert (
        validate_release_manifest(path, repository_root=ROOT, verify_files=False)[
            "ready_for_owner_decision"
        ]
        is True
    )

    document["requirements"][0]["status"] = "incomplete"
    document["requirements"][0]["missing"] = ["required alpha evidence missing"]
    path = _write(tmp_path / "required-missing", document)
    with pytest.raises(ReleaseManifestError, match="machine_readiness"):
        validate_release_manifest(path, repository_root=ROOT, verify_files=False)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda document: document["candidate"].__setitem__("base_sha", "INVALID"),
        lambda document: document["gates"].__setitem__(7, deepcopy(document["gates"][0])),
        lambda document: document.__setitem__("artifacts", []),
        lambda document: document["gates"][0].__setitem__("missing", ["still missing"]),
    ],
)
def test_release_manifest_rejects_invalid_structure_and_gate_semantics(tmp_path, mutate):
    document = _document()
    mutate(document)
    path = _write(tmp_path, document)

    with pytest.raises(ReleaseManifestError):
        validate_release_manifest(path, repository_root=ROOT, verify_files=False)


def test_release_manifest_rejects_missing_receipts_and_dirty_go(tmp_path):
    document = _document()
    document["gates"][0]["receipts"] = ["does-not-exist.json"]
    path = _write(tmp_path, document)
    with pytest.raises(ReleaseManifestError, match="does not exist"):
        validate_release_manifest(path, repository_root=ROOT)

    document = _document()
    for gate in document["gates"]:
        gate["status"] = "passed"
        gate["missing"] = []
    document["candidate"]["rc_sha"] = document["candidate"]["base_sha"]
    document["decision"]["status"] = "go"
    path = _write(tmp_path / "dirty", document)
    with pytest.raises(ReleaseManifestError, match="cannot authorize"):
        validate_release_manifest(path, repository_root=ROOT, verify_files=False)


@pytest.mark.parametrize(
    "raw",
    [
        b'{"schema":"x","schema":"y"}',
        b'{"value":NaN}',
        b"\xff",
    ],
)
def test_strict_json_rejects_duplicate_keys_nonfinite_numbers_and_invalid_utf8(raw: bytes):
    with pytest.raises(DocumentError):
        loads_document(raw)
