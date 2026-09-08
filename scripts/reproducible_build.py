"""Build wheel and sdist twice and compare their exact bytes."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True, check=False
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or f"git {' '.join(args)} failed")
    return completed.stdout.strip()


def _artifacts(directory: Path) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for path in directory.iterdir():
        if path.suffix == ".whl" or path.name.endswith(".tar.gz"):
            raw = path.read_bytes()
            result[path.name] = {
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
    if len(result) != 2:
        raise RuntimeError(f"expected one wheel and one sdist, observed {sorted(result)}")
    return result


def _canonicalize_sdist(path: Path, epoch: int) -> None:
    temporary = path.with_suffix(path.suffix + ".canonical")
    with tarfile.open(path, "r:gz") as source:
        members = source.getmembers()
        with temporary.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=epoch) as compressed:
                with tarfile.open(
                    fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT
                ) as target:
                    for member in sorted(members, key=lambda item: item.name):
                        content = source.extractfile(member) if member.isfile() else None
                        member.mtime = epoch
                        member.uid = 0
                        member.gid = 0
                        member.uname = ""
                        member.gname = ""
                        member.pax_headers = {}
                        target.addfile(member, content)
    os.replace(temporary, path)


def verify_reproducible_build(
    root: Path,
    *,
    allow_dirty: bool = False,
    dist_dir: Path | None = None,
) -> dict[str, object]:
    root = root.resolve()
    revision = _git(root, "rev-parse", "HEAD")
    dirty = bool(_git(root, "status", "--porcelain=v1", "--untracked-files=all"))
    if dirty and not allow_dirty:
        raise RuntimeError("reproducible RC build requires a clean worktree")
    epoch = int(_git(root, "show", "-s", "--format=%ct", revision))
    environment = {**os.environ, "SOURCE_DATE_EPOCH": str(epoch)}
    with tempfile.TemporaryDirectory(prefix="testence-repro-build-") as temporary:
        parent = Path(temporary)
        arms = []
        for name in ("first", "second"):
            output = parent / name
            completed = subprocess.run(
                ["uv", "build", "--out-dir", str(output)],
                cwd=root,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
            if completed.returncode:
                raise RuntimeError(completed.stderr or completed.stdout)
            for sdist in output.glob("*.tar.gz"):
                _canonicalize_sdist(sdist, epoch)
            arms.append(_artifacts(output))
        if arms[0] == arms[1] and dist_dir is not None:
            destination = dist_dir.resolve()
            destination.mkdir(parents=True, exist_ok=True)
            for artifact in (parent / "first").iterdir():
                if artifact.suffix == ".whl" or artifact.name.endswith(".tar.gz"):
                    shutil.copy2(artifact, destination / artifact.name)
    matched = arms[0] == arms[1]
    return {
        "schema": "testence/reproducible-build/1",
        "status": "passed" if matched and not dirty else "development",
        "revision": revision,
        "dirty": dirty,
        "source_date_epoch": epoch,
        "matched": matched,
        "artifacts": arms[0],
        "second_build": arms[1],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dist-dir", type=Path)
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args()
    try:
        result = verify_reproducible_build(
            args.root,
            allow_dirty=args.allow_dirty,
            dist_dir=args.dist_dir,
        )
    except RuntimeError as exc:
        parser.error(str(exc))
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0 if result["matched"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
