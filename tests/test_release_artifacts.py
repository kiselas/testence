from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import tarfile
from pathlib import Path

import pytest


def _module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "release_artifacts.py"
    spec = importlib.util.spec_from_file_location("release_artifacts", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sdist(path: Path) -> None:
    raw = b"[project]\nname='sample'\n"
    member = tarfile.TarInfo("sample-1.2.3/pyproject.toml")
    member.size = len(raw)
    with tarfile.open(path, "w:gz") as archive:
        archive.addfile(member, io.BytesIO(raw))


def test_release_documents_bind_distributions_dependencies_and_inputs(tmp_path):
    root = tmp_path / "source"
    dist = root / "dist"
    dist.mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        '[project]\nname="sample"\nversion="1.2.3"\nlicense="Apache-2.0"\n'
        'dependencies=["pytest>=8", "playwright>=1.49"]\n',
        encoding="utf-8",
    )
    (root / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (root / "MANIFEST.in").write_text("include README.md\n", encoding="utf-8")
    (dist / "sample-1.2.3.whl").write_bytes(b"wheel")
    _sdist(dist / "sample-1.2.3.tar.gz")

    documents = _module().build_documents(root, dist, "https://example.invalid/sample", "a" * 40)

    assert [item["path"] for item in documents["checksums"]] == [
        "sample-1.2.3.tar.gz",
        "sample-1.2.3.whl",
    ]
    assert documents["sbom"]["spdxVersion"] == "SPDX-2.3"
    assert documents["sbom_scope"] == "declared_direct_only"
    assert {package["name"] for package in documents["sbom"]["packages"]} == {
        "sample",
        "playwright",
        "pytest",
    }
    assert documents["provenance"]["source"]["revision"] == "a" * 40
    assert {item["path"] for item in documents["provenance"]["inputs"]} == {
        "pyproject.toml",
        "uv.lock",
        "MANIFEST.in",
    }
    assert json.dumps(documents)


def test_release_sbom_uses_the_resolved_installed_runtime_closure(tmp_path):
    root = tmp_path / "source"
    dist = root / "dist"
    dist.mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        '[project]\nname="sample"\nversion="1.2.3"\nlicense="Apache-2.0"\n'
        'dependencies=["parent>=2"]\n',
        encoding="utf-8",
    )
    (root / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (root / "MANIFEST.in").write_text("include README.md\n", encoding="utf-8")
    (dist / "sample-1.2.3.whl").write_bytes(b"wheel")
    _sdist(dist / "sample-1.2.3.tar.gz")
    inventory = {
        "schema": "testence/dependency-inventory/1",
        "root": "sample",
        "environment": {"python": "3.12.0", "platform": "test"},
        "distribution": {
            "path": "sample-1.2.3.whl",
            "bytes": 5,
            "sha256": hashlib.sha256(b"wheel").hexdigest(),
        },
        "smoke_receipt": {"path": "smoke.json", "bytes": 2, "sha256": "a" * 64},
        "packages": [
            {
                "name": "sample",
                "version": "1.2.3",
                "license": "Apache-2.0",
                "requires": ["parent>=2"],
            },
            {"name": "parent", "version": "2.4.0", "license": "MIT", "requires": ["child>=1"]},
            {"name": "child", "version": "1.7.0", "license": "BSD-3-Clause", "requires": []},
        ],
    }

    documents = _module().build_documents(
        root,
        dist,
        "https://example.invalid/sample",
        "a" * 40,
        dependency_inventory=inventory,
        dependency_inventory_digest="b" * 64,
        source_dirty=True,
    )

    assert documents["sbom_scope"] == "resolved_runtime"
    packages = {item["name"]: item for item in documents["sbom"]["packages"]}
    assert packages["parent"]["versionInfo"] == "2.4.0"
    assert packages["child"]["licenseDeclared"] == "BSD-3-Clause"
    edges = {
        (item["spdxElementId"], item["relatedSpdxElement"])
        for item in documents["sbom"]["relationships"]
    }
    assert ("SPDXRef-Dependency-parent", "SPDXRef-Dependency-child") in edges
    assert documents["provenance"]["source"]["dirty"] is True
    assert documents["provenance"]["source"]["materialized_digest"].startswith("sha256:")
    assert documents["provenance"]["runtime_inventory"]["sha256"] == "b" * 64


def test_release_sbom_rejects_inventory_for_another_wheel(tmp_path):
    root = tmp_path / "source"
    dist = root / "dist"
    dist.mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        '[project]\nname="sample"\nversion="1.2.3"\nlicense="Apache-2.0"\n',
        encoding="utf-8",
    )
    (root / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (root / "MANIFEST.in").write_text("include README.md\n", encoding="utf-8")
    (dist / "sample-1.2.3.whl").write_bytes(b"wheel")
    _sdist(dist / "sample-1.2.3.tar.gz")
    inventory = {
        "schema": "testence/dependency-inventory/1",
        "root": "sample",
        "environment": {},
        "distribution": {"path": "other.whl", "bytes": 5, "sha256": "0" * 64},
        "smoke_receipt": {"path": "smoke.json", "bytes": 2, "sha256": "a" * 64},
        "packages": [],
    }

    with pytest.raises(ValueError, match="different candidate wheel"):
        _module().build_documents(
            root,
            dist,
            "https://example.invalid/sample",
            "a" * 40,
            dependency_inventory=inventory,
        )
