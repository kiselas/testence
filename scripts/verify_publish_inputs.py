"""Fail closed unless a tag, candidate distributions, and release decision agree."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
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
