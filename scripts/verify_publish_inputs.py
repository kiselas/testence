"""Fail closed unless a tag, candidate distributions, and release decision agree."""

from __future__ import annotations

import argparse
import email.policy
import hashlib
import json
import re
import subprocess
import tarfile
import zipfile
from email.parser import BytesParser
from pathlib import Path
from typing import Any

from testence.contracts import load_document
from testence.release import ReleaseManifestError, validate_release_manifest


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True, check=False
    )
    if completed.returncode:
        raise ValueError(completed.stderr.strip() or f"git {' '.join(args)} failed")
    return completed.stdout.strip()


def _canonical_project_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).casefold()


def _package_identity(path: Path) -> tuple[str, str]:
    try:
        if path.suffix == ".whl":
            with zipfile.ZipFile(path) as archive:
                wheel_metadata = [
                    name
                    for name in archive.namelist()
                    if name.endswith(".dist-info/METADATA") and name.count("/") == 1
                ]
                if len(wheel_metadata) != 1:
                    raise ValueError(f"wheel must contain exactly one METADATA file: {path.name}")
                raw = archive.read(wheel_metadata[0])
        elif path.name.endswith(".tar.gz"):
            with tarfile.open(path, "r:gz") as archive:
                sdist_metadata = [
                    member
                    for member in archive.getmembers()
                    if member.isfile()
                    and member.name.endswith("/PKG-INFO")
                    and member.name.count("/") == 1
                ]
                if len(sdist_metadata) != 1:
                    raise ValueError(
                        f"sdist must contain exactly one top-level PKG-INFO: {path.name}"
                    )
                extracted = archive.extractfile(sdist_metadata[0])
                if extracted is None:
                    raise ValueError(f"cannot read sdist package metadata: {path.name}")
                raw = extracted.read()
        else:
            raise ValueError(f"unsupported distribution artifact: {path.name}")
    except (tarfile.TarError, zipfile.BadZipFile) as exc:
        raise ValueError(f"cannot read distribution archive: {path.name}") from exc
    metadata = BytesParser(policy=email.policy.compat32).parsebytes(raw)
    name = metadata.get("Name")
    version = metadata.get("Version")
    if not name or not version:
        raise ValueError(f"distribution metadata has no Name or Version: {path.name}")
    return str(name), str(version)


def verify_publish_inputs(
    root: Path,
    dist_dir: Path,
    build_receipt_path: Path,
    manifest_path: Path,
    candidate_sha: str,
    tag: str,
    evidence_root: Path | None = None,
) -> dict[str, Any]:
    root = root.resolve(strict=True)
    evidence = evidence_root.resolve(strict=True) if evidence_root is not None else root
    if not re.fullmatch(r"[0-9a-f]{40}", candidate_sha):
        raise ValueError("candidate SHA must be 40 lowercase hexadecimal characters")
    if not re.fullmatch(r"v[0-9]+(?:\.[0-9]+){2}[0-9A-Za-z.!+_-]*", tag):
        raise ValueError("release tag must be a version tag such as v1.2.3")
    tag_sha = _git(root, "rev-parse", f"refs/tags/{tag}^{{commit}}")
    if tag_sha != candidate_sha:
        raise ValueError(f"tag {tag} points at {tag_sha}, expected {candidate_sha}")

    build = load_document(build_receipt_path)
    if not isinstance(build, dict) or build.get("schema") != "testence/reproducible-build/1":
        raise ValueError("unsupported reproducible build receipt")
    if (
        build.get("status") != "passed"
        or build.get("matched") is not True
        or build.get("dirty") is not False
        or build.get("revision") != candidate_sha
    ):
        raise ValueError("build receipt is not a clean reproducible build of the candidate")

    artifacts = sorted(
        path
        for path in dist_dir.resolve(strict=True).iterdir()
        if path.is_file() and (path.suffix == ".whl" or path.name.endswith(".tar.gz"))
    )
    if len(artifacts) != 2 or sum(path.suffix == ".whl" for path in artifacts) != 1:
        raise ValueError("publish input must contain exactly one wheel and one sdist")
    observed = {
        path.name: {"bytes": path.stat().st_size, "sha256": _sha(path)} for path in artifacts
    }
    if build.get("artifacts") != observed:
        raise ValueError("candidate distribution bytes differ from the reproducible build receipt")

    release = validate_release_manifest(manifest_path, repository_root=evidence, verify_files=True)
    if release["status"] != "go" or not release["ready_for_owner_decision"]:
        raise ValueError("release manifest does not contain a complete owner go decision")
    manifest = load_document(manifest_path)
    candidate = manifest["candidate"]
    if candidate["rc_sha"] != candidate_sha or candidate["tag"] != tag:
        raise ValueError("release manifest candidate/tag differs from publish request")
    if candidate["version"] != tag.removeprefix("v"):
        raise ValueError("release manifest version differs from release tag")
    expected_version = candidate["version"]
    for artifact in artifacts:
        package_name, package_version = _package_identity(artifact)
        if _canonical_project_name(package_name) != "testence":
            raise ValueError(f"distribution package name is not testence: {artifact.name}")
        if package_version != expected_version:
            raise ValueError(
                f"distribution version {package_version} differs from release version "
                f"{expected_version}: {artifact.name}"
            )
    release_artifacts = {Path(item["path"]).name: item for item in manifest["artifacts"]}
    for name, details in observed.items():
        reference = release_artifacts.get(name)
        if (
            reference is None
            or reference["bytes"] != details["bytes"]
            or reference["sha256"] != details["sha256"]
        ):
            raise ValueError(f"release manifest does not bind exact distribution {name}")
    return {
        "schema": "testence/publishing-prepared/1",
        "status": "passed",
        "candidate_sha": candidate_sha,
        "tag": tag,
        "manifest_payload_digest": release["payload_digest"],
        "distributions": [{"path": name, **details} for name, details in observed.items()],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--dist-dir", type=Path, required=True)
    parser.add_argument("--build-receipt", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = verify_publish_inputs(
            args.root,
            args.dist_dir,
            args.build_receipt,
            args.manifest,
            args.candidate_sha,
            args.tag,
            evidence_root=args.evidence_root,
        )
    except (OSError, ValueError, ReleaseManifestError) as exc:
        parser.error(str(exc))
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
