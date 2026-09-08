"""Rebuild a wheel from the exact sdist and compare its normative payload."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

from testence.distribution import DistributionError, compare_wheel_payloads

MAX_ENTRIES = 10_000
MAX_EXPANDED_BYTES = 512 * 1024 * 1024


def _only(directory: Path, pattern: str, kind: str) -> Path:
    matches = sorted(directory.glob(pattern))
    if len(matches) != 1:
        raise RuntimeError(
            f"expected exactly one {kind}, observed {[item.name for item in matches]}"
        )
    return matches[0].resolve()


def _extract_sdist(sdist: Path, destination: Path) -> Path:
    if not sdist.is_file() or not tarfile.is_tarfile(sdist):
        raise RuntimeError(f"distribution is not an sdist archive: {sdist}")
    with tarfile.open(sdist, "r:*") as archive:
        members = archive.getmembers()
        if not members or len(members) > MAX_ENTRIES:
            raise RuntimeError("sdist has an invalid archive entry count")
        expanded = sum(member.size for member in members if member.isfile())
        if expanded > MAX_EXPANDED_BYTES:
            raise RuntimeError("sdist exceeds the expanded-byte limit")
        roots: set[str] = set()
        for member in members:
            path = PurePosixPath(member.name)
            if (
                not path.parts
                or member.name.startswith("/")
                or "\\" in member.name
                or ":" in member.name
                or any(part in {"", ".", ".."} for part in path.parts)
                or member.issym()
                or member.islnk()
                or not (member.isfile() or member.isdir())
            ):
                raise RuntimeError(f"sdist contains unsafe archive member: {member.name!r}")
            roots.add(path.parts[0])
        if len(roots) != 1:
            raise RuntimeError("sdist must contain exactly one top-level directory")

        destination.mkdir(parents=True, exist_ok=False)
        resolved_destination = destination.resolve()
        for member in members:
            relative = PurePosixPath(member.name)
            target = destination.joinpath(*relative.parts)
            if os.path.commonpath((resolved_destination, target.resolve(strict=False))) != str(
                resolved_destination
            ):
                raise RuntimeError(f"sdist member escapes extraction root: {member.name!r}")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise RuntimeError(f"cannot read sdist member: {member.name!r}")
            raw = source.read(MAX_EXPANDED_BYTES + 1)
            if len(raw) != member.size:
                raise RuntimeError(f"sdist member size mismatch: {member.name!r}")
            target.write_bytes(raw)
    root = destination / next(iter(roots))
    if not (root / "pyproject.toml").is_file():
        raise RuntimeError("sdist root is missing pyproject.toml")
    return root


def verify_sdist_rebuild(dist_dir: Path) -> dict[str, object]:
    dist_dir = dist_dir.resolve()
    candidate = _only(dist_dir, "*.whl", "wheel")
    sdist = _only(dist_dir, "*.tar.gz", "sdist")
    sdist_before = hashlib.sha256(sdist.read_bytes()).hexdigest()
    candidate_before = hashlib.sha256(candidate.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="testence-sdist-rebuild-") as temporary:
        parent = Path(temporary)
        source = _extract_sdist(sdist, parent / "source")
        rebuilt_dir = parent / "dist"
        completed = subprocess.run(
            ["uv", "build", "--wheel", "--out-dir", str(rebuilt_dir)],
            cwd=source,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
        rebuilt = _only(rebuilt_dir, "*.whl", "rebuilt wheel")
        comparison = compare_wheel_payloads(candidate, rebuilt)
    if hashlib.sha256(sdist.read_bytes()).hexdigest() != sdist_before:
        raise RuntimeError("sdist bytes changed while rebuilding")
    if hashlib.sha256(candidate.read_bytes()).hexdigest() != candidate_before:
        raise RuntimeError("candidate wheel bytes changed while rebuilding")
    return {
        "schema": "testence/sdist-rebuild/1",
        "status": "passed",
        "sdist": {"path": sdist.name, "sha256": sdist_before},
        "candidate": {"path": candidate.name, "sha256": candidate_before},
        "comparison": comparison,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = verify_sdist_rebuild(args.dist_dir)
    except (DistributionError, OSError, RuntimeError, tarfile.TarError) as exc:
        parser.error(str(exc))
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
