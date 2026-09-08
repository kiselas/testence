from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from testence.benchmark import REQUIRED_STRATA, CorpusProtocolError, validate_corpus_registry
from testence.cli import main

ROOT = Path(__file__).parents[1]
REGISTRY = ROOT / "corpus/r1-correctness-v2.json"


def test_frozen_r1_registry_has_exact_required_strata_and_holdout():
    result = validate_corpus_registry(REGISTRY)

    assert result["cases"] == 40
    assert result["strata"] == REQUIRED_STRATA
    assert result["holdout"] == 8
    assert result["status"] == "incomplete"
    assert result["oss_targets"] == 0
    assert result["independent_review"] is False


def test_corpus_cli_separates_structure_from_external_acceptance(capsys):
    assert main(["corpus", "validate", str(REGISTRY), "--structure-only", "--json"]) == 0
    structured = json.loads(capsys.readouterr().out)
    assert structured["cases"] == 40 and structured["acceptance_ready"] is False

    assert main(["corpus", "validate", str(REGISTRY), "--json"]) == 3
    assert json.loads(capsys.readouterr().out)["status"] == "incomplete"


def test_registry_rejects_a_case_whose_source_digest_was_invented(tmp_path):
    document = json.loads(REGISTRY.read_text(encoding="utf-8"))
    document["cases"][0]["source_sha256"] = "0" * 64
    altered = tmp_path / "registry.json"
    altered.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(CorpusProtocolError, match="source digest mismatch"):
        validate_corpus_registry(altered, repository_root=ROOT)


def test_registry_rejects_a_selector_not_present_in_the_pinned_source(tmp_path):
    document = json.loads(REGISTRY.read_text(encoding="utf-8"))
    document["cases"][0]["selector"] = "case-that-does-not-exist"
    altered = tmp_path / "registry.json"
    altered.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(CorpusProtocolError, match="selector .* is absent"):
        validate_corpus_registry(altered, repository_root=ROOT)


def test_registry_does_not_count_unverifiable_acceptance_receipts(tmp_path):
    document = json.loads(REGISTRY.read_text(encoding="utf-8"))
    document["oss_targets"] = [
        {
            "id": "target-one",
            "repository": "https://example.test/target-one",
            "license": "MIT",
            "commit": "a" * 40,
            "reproduction_receipt": "outputs/missing-reproduction.json",
            "receipt_sha256": hashlib.sha256(b"plausible").hexdigest(),
        },
        {
            "id": "target-two",
            "repository": "https://example.test/target-two",
            "license": "Apache-2.0",
            "commit": "b" * 40,
            "reproduction_receipt": "outputs/missing-second-reproduction.json",
            "receipt_sha256": hashlib.sha256(b"plausible").hexdigest(),
        },
    ]
    altered = tmp_path / "registry.json"
    altered.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(CorpusProtocolError, match="missing reproduction receipt"):
        validate_corpus_registry(altered, repository_root=ROOT)
