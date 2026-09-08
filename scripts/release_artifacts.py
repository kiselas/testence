"""Generate checksums, an SPDX SBOM and a local build provenance statement."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from spdx_tools.spdx.parser.parse_anything import parse_file
from spdx_tools.spdx.validation.document_validator import validate_full_spdx_document

try:
    import tomllib
except ImportError:  # Python 3.10; pytest's supported runtime includes tomli there.
    import tomli as tomllib  # type: ignore[import-not-found,no-redef]


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _revision(root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True, check=False
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


def _git_state(root: Path) -> tuple[str, bool]:
    revision = _revision(root)
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if not re.fullmatch(r"[0-9a-f]{40}", revision) or status.returncode:
        raise ValueError("release provenance requires an accessible Git worktree and full HEAD SHA")
    return revision, bool(status.stdout)


def _dependency_name(requirement: str) -> str:
    return re.split(r"[ <>=!~;\[]", requirement, maxsplit=1)[0]


def _normalized_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _materialized_source(artifacts: list[Path]) -> tuple[str, int]:
    sdist = next((path for path in artifacts if path.name.endswith(".tar.gz")), None)
    if sdist is None:
        raise ValueError("release provenance requires an sdist subject")
    material = bytearray()
    count = 0
    with tarfile.open(sdist, "r:gz") as archive:
        for member in sorted(archive.getmembers(), key=lambda item: item.name):
            if not member.isfile():
                continue
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError(f"cannot read sdist member: {member.name}")
            relative = "/".join(Path(member.name).parts[1:])
            raw = stream.read()
            encoded = relative.encode("utf-8")
            material.extend(len(encoded).to_bytes(4, "big") + encoded)
            material.extend(len(raw).to_bytes(8, "big") + raw)
            count += 1
    return "sha256:" + hashlib.sha256(material).hexdigest(), count


def validate_spdx(path: Path) -> dict[str, Any]:
    document = parse_file(str(path))
    messages = validate_full_spdx_document(document)
    if messages:
        rendered = "; ".join(message.validation_message for message in messages)
        raise ValueError(f"SPDX validation failed: {rendered}")
    return {
        "tool": "spdx-tools",
        "version": importlib.metadata.version("spdx-tools"),
        "status": "passed",
    }


def build_documents(
    root: Path,
    dist_dir: Path,
    repository: str,
    revision: str,
    *,
    dependency_inventory: dict[str, Any] | None = None,
    dependency_inventory_digest: str | None = None,
    source_dirty: bool = False,
) -> dict[str, Any]:
    artifacts = sorted(
        path
        for path in dist_dir.iterdir()
        if path.is_file() and (path.suffix == ".whl" or path.name.endswith(".tar.gz"))
    )
    if not artifacts:
        raise ValueError(f"no distribution artifacts in {dist_dir}")
    configuration = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    project = configuration["project"]
    created = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    checksums: list[dict[str, Any]] = [
        {"path": artifact.name, "bytes": artifact.stat().st_size, "sha256": _digest(artifact)}
        for artifact in artifacts
    ]
    if dependency_inventory is not None:
        wheel = [item for item in checksums if item["path"].endswith(".whl")]
        binding = dependency_inventory.get("distribution")
        smoke_binding = dependency_inventory.get("smoke_receipt")
        environment_binding = dependency_inventory.get("environment")
        if len(wheel) != 1 or not isinstance(binding, dict):
            raise ValueError("resolved dependency inventory must bind exactly one candidate wheel")
        if binding.get("sha256") != wheel[0]["sha256"] or binding.get("bytes") != wheel[0]["bytes"]:
            raise ValueError("dependency inventory is bound to a different candidate wheel")
        if not isinstance(smoke_binding, dict) or not re.fullmatch(
            r"[0-9a-f]{64}", str(smoke_binding.get("sha256", ""))
        ):
            raise ValueError("resolved dependency inventory must bind a smoke receipt")
        if not isinstance(environment_binding, dict):
            raise ValueError("resolved dependency inventory must identify its environment")
    namespace_seed = hashlib.sha256(
        (revision + "\n" + "\n".join(item["sha256"] for item in checksums)).encode()
    ).hexdigest()
    root_package = {
        "SPDXID": "SPDXRef-Package-testence",
        "name": project["name"],
        "versionInfo": project["version"],
        "downloadLocation": "NOASSERTION",
        "filesAnalyzed": False,
        "licenseConcluded": project["license"],
        "licenseDeclared": project["license"],
        "copyrightText": "NOASSERTION",
        "externalRefs": [
            {
                "referenceCategory": "PACKAGE-MANAGER",
                "referenceType": "purl",
                "referenceLocator": f"pkg:pypi/{project['name']}@{project['version']}",
            }
        ],
    }
    dependencies = []
    relationships = []
    inventory_packages = (
        dependency_inventory.get("packages", [])
        if isinstance(dependency_inventory, dict)
        and dependency_inventory.get("schema") == "testence/dependency-inventory/1"
        else []
    )
    package_inputs: list[dict[str, Any]]
    if inventory_packages:
        package_inputs = [
            {
                "name": str(item["name"]),
                "version": str(item["version"]),
                "license": str(item["license"]),
                "requires": list(item.get("requires", [])),
            }
            for item in inventory_packages
            if _normalized_name(str(item.get("name", ""))) != _normalized_name(str(project["name"]))
        ]
        sbom_scope = "resolved_runtime"
    else:
        package_inputs = [
            {
                "name": _dependency_name(requirement),
                "version": requirement[len(_dependency_name(requirement)) :] or "unspecified",
                "license": "NOASSERTION",
                "requires": [],
            }
            for requirement in sorted(project.get("dependencies", []))
        ]
        sbom_scope = "declared_direct_only"
    for item in package_inputs:
        name = item["name"]
        spdx_id = "SPDXRef-Dependency-" + re.sub(r"[^A-Za-z0-9.-]", "-", name)
        dependencies.append(
            {
                "SPDXID": spdx_id,
                "name": name,
                "versionInfo": item["version"],
                "downloadLocation": "NOASSERTION",
                "filesAnalyzed": False,
                "licenseConcluded": item["license"],
                "licenseDeclared": item["license"],
                "copyrightText": "NOASSERTION",
                "externalRefs": [
                    {
                        "referenceCategory": "PACKAGE-MANAGER",
                        "referenceType": "purl",
                        "referenceLocator": f"pkg:pypi/{name}@{item['version']}",
                    }
                ],
            }
        )
    package_ids = {
        _normalized_name(project["name"]): "SPDXRef-Package-testence",
        **{_normalized_name(item["name"]): item["SPDXID"] for item in dependencies},
    }
    sources = (
        inventory_packages
        if inventory_packages
        else [{"name": project["name"], "requires": project.get("dependencies", [])}]
    )
    for source in sources:
        source_id = package_ids.get(_normalized_name(str(source.get("name", ""))))
        if source_id is None:
            continue
        for requirement in source.get("requires", []):
            target_id = package_ids.get(_normalized_name(_dependency_name(str(requirement))))
            if target_id is not None:
                relationships.append(
                    {
                        "spdxElementId": source_id,
                        "relationshipType": "DEPENDS_ON",
                        "relatedSpdxElement": target_id,
                    }
                )
    sbom = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"testence-{project['version']}",
        "documentNamespace": f"https://spdx.org/spdxdocs/testence-{namespace_seed}",
        "creationInfo": {"created": created, "creators": ["Tool: testence-release-artifacts/1"]},
        "documentDescribes": ["SPDXRef-Package-testence"],
        "comment": f"Dependency scope: {sbom_scope}",
        "packages": [root_package, *dependencies],
        "relationships": relationships,
    }
    inputs = []
    for relative in ("pyproject.toml", "uv.lock", "MANIFEST.in"):
        path = root / relative
        inputs.append({"path": relative, "sha256": _digest(path)})
    source_digest, source_files = _materialized_source(artifacts)
    build_system = configuration.get("build-system", {})
    provenance = {
        "schema": "testence/build-provenance/1",
        "source": {
            "repository": repository,
            "revision": revision,
            "dirty": source_dirty,
            "materialized_digest": source_digest,
            "materialized_files": source_files,
        },
        "builder": {
            "name": "github-actions" if os.environ.get("GITHUB_ACTIONS") else "local",
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "workflow_ref": os.environ.get("GITHUB_WORKFLOW_REF"),
            "build_backend": build_system.get("build-backend"),
            "build_requires": build_system.get("requires", []),
        },
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "inputs": inputs,
        "subjects": checksums,
    }
    if dependency_inventory is not None:
        provenance["runtime_inventory"] = {
            "sha256": dependency_inventory_digest,
            "environment": dependency_inventory["environment"],
            "distribution": dependency_inventory["distribution"],
            "smoke_receipt": dependency_inventory["smoke_receipt"],
            "components": dependency_inventory.get("components", {}),
        }
    return {
        "checksums": checksums,
        "sbom": sbom,
        "sbom_scope": sbom_scope,
        "provenance": provenance,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--dist-dir", type=Path, default=Path("dist"))
    parser.add_argument("--output-dir", type=Path, default=Path("release-artifacts"))
    parser.add_argument(
        "--repository",
        default=os.environ.get("GITHUB_SERVER_URL", "local")
        + "/"
        + os.environ.get("GITHUB_REPOSITORY", "testence"),
    )
    parser.add_argument("--revision")
    parser.add_argument("--dependency-inventory", type=Path)
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="emit development provenance marked dirty; never suitable for an RC",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    head, dirty = _git_state(root)
    if args.revision and args.revision != head:
        parser.error(f"--revision {args.revision} does not match Git HEAD {head}")
    if dirty and not args.allow_dirty:
        parser.error(
            "release provenance requires a clean worktree (use --allow-dirty for development)"
        )
    inventory = None
    inventory_digest = None
    if args.dependency_inventory:
        inventory_path = args.dependency_inventory.resolve()
        inventory_raw = inventory_path.read_bytes()
        inventory_digest = hashlib.sha256(inventory_raw).hexdigest()
        inventory = json.loads(inventory_raw)
        smoke_ref = inventory.get("smoke_receipt", {})
        smoke_path = inventory_path.parent / str(smoke_ref.get("path", ""))
        if (
            not smoke_path.is_file()
            or smoke_ref.get("bytes") != smoke_path.stat().st_size
            or smoke_ref.get("sha256") != _digest(smoke_path)
        ):
            parser.error("dependency inventory references a missing or changed smoke receipt")
    documents = build_documents(
        root,
        args.dist_dir.resolve(),
        args.repository,
        head,
        dependency_inventory=inventory,
        dependency_inventory_digest=inventory_digest,
        source_dirty=dirty,
    )
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "checksums.sha256").write_text(
        "".join(f"{item['sha256']}  {item['path']}\n" for item in documents["checksums"]),
        encoding="utf-8",
        newline="\n",
    )
    for name in ("sbom", "provenance"):
        (output / f"{name}.json").write_text(
            json.dumps(documents[name], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    spdx_validation = validate_spdx(output / "sbom.json")
    status = "development" if dirty else "passed"
    print(
        json.dumps(
            {
                "status": status,
                "output": str(output),
                "spdx_validation": spdx_validation,
                **documents["provenance"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
