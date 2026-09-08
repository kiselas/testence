"""Bind release smoke evidence to the exact installed wheel under test."""

from __future__ import annotations

import hashlib
import re
import zipfile
from email.parser import BytesParser
from email.policy import default
from importlib import metadata
from pathlib import Path, PurePosixPath
from typing import Any


class DistributionError(ValueError):
    """A wheel is malformed or differs from the installed distribution."""


def _normalized_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def inspect_wheel(path: Path | str) -> dict[str, Any]:
    wheel = Path(path).resolve()
    if wheel.suffix != ".whl" or not wheel.is_file() or not zipfile.is_zipfile(wheel):
        raise DistributionError(f"distribution is not a wheel archive: {wheel}")
    filename = wheel.stem.split("-")
    if len(filename) < 5:
        raise DistributionError(f"invalid wheel filename: {wheel.name}")

    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise DistributionError("wheel contains duplicate archive members")
        for name in names:
            parts = PurePosixPath(name).parts
            if not parts or name.startswith("/") or "\\" in name or ".." in parts:
                raise DistributionError(f"wheel contains unsafe archive member: {name!r}")
        metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
        wheel_names = [name for name in names if name.endswith(".dist-info/WHEEL")]
        record_names = [name for name in names if name.endswith(".dist-info/RECORD")]
        if len(metadata_names) != 1 or len(wheel_names) != 1 or len(record_names) != 1:
            raise DistributionError("wheel must contain exactly one METADATA, WHEEL, and RECORD")
        message = BytesParser(policy=default).parsebytes(archive.read(metadata_names[0]))
        distribution_name = str(message.get("Name") or "")
        distribution_version = str(message.get("Version") or "")
        if not distribution_name or not distribution_version:
            raise DistributionError("wheel METADATA is missing Name or Version")
        if _normalized_name(filename[0]) != _normalized_name(distribution_name):
            raise DistributionError("wheel filename distribution name differs from METADATA")
        if filename[1].replace("_", "-") != distribution_version.replace("_", "-"):
            raise DistributionError("wheel filename version differs from METADATA")
        package_members = [
            member
            for member in names
            if member.startswith("testence/") and not member.endswith("/")
        ]
        if not package_members:
            raise DistributionError("wheel does not contain the testence package")

    return {
        "path": wheel,
        "name": distribution_name,
        "version": distribution_version,
        "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "package_members": package_members,
    }


def compare_wheel_payloads(first: Path | str, second: Path | str) -> dict[str, Any]:
    """Compare the install-relevant bytes of two independently built wheels.

    ZIP container metadata and ``RECORD`` are build products.  Every other file,
    including package resources and dist-info metadata, must have the same path and
    bytes for an sdist rebuild to be accepted.
    """

    left = inspect_wheel(first)
    right = inspect_wheel(second)
    if (left["name"], left["version"]) != (right["name"], right["version"]):
        raise DistributionError("rebuilt wheel name/version differs from candidate wheel")

    def normative_members(path: Path) -> dict[str, str]:
        with zipfile.ZipFile(path) as archive:
            result: dict[str, str] = {}
            for info in archive.infolist():
                if info.is_dir() or info.filename.endswith(".dist-info/RECORD"):
                    continue
                result[info.filename] = hashlib.sha256(archive.read(info.filename)).hexdigest()
            return result

    left_members = normative_members(left["path"])
    right_members = normative_members(right["path"])
    if left_members != right_members:
        missing = sorted(set(left_members) - set(right_members))
        extra = sorted(set(right_members) - set(left_members))
        changed = sorted(
            name
            for name in set(left_members) & set(right_members)
            if left_members[name] != right_members[name]
        )
        raise DistributionError(
            "rebuilt wheel payload differs from candidate: "
            f"missing={missing}, extra={extra}, changed={changed}"
        )
    return {
        "candidate_sha256": left["sha256"],
        "rebuilt_sha256": right["sha256"],
        "name": left["name"],
        "version": left["version"],
        "normative_files": len(left_members),
        "normative_payload_sha256": hashlib.sha256(
            b"".join(
                len(name.encode("utf-8")).to_bytes(4, "big")
                + name.encode("utf-8")
                + bytes.fromhex(left_members[name])
                for name in sorted(left_members)
            )
        ).hexdigest(),
    }


def verify_installed_wheel(path: Path | str) -> dict[str, Any]:
    inspected = inspect_wheel(path)
    try:
        installed = metadata.distribution(inspected["name"])
    except metadata.PackageNotFoundError as exc:
        raise DistributionError(f"{inspected['name']} is not installed") from exc
    if installed.version != inspected["version"]:
        raise DistributionError(
            f"installed version {installed.version!r} differs from wheel {inspected['version']!r}"
        )

    wheel = inspected["path"]
    checked = 0
    with zipfile.ZipFile(wheel) as archive:
        for member in inspected["package_members"]:
            relative = PurePosixPath(member)
            installed_path = Path(str(installed.locate_file(Path(*relative.parts))))
            if not installed_path.is_file():
                raise DistributionError(f"installed wheel payload is missing {member}")
            expected = hashlib.sha256(archive.read(member)).digest()
            actual = hashlib.sha256(installed_path.read_bytes()).digest()
            if actual != expected:
                raise DistributionError(f"installed payload differs from wheel for {member}")
            checked += 1
    return {
        "path": wheel.name,
        "name": inspected["name"],
        "version": inspected["version"],
        "sha256": inspected["sha256"],
        "verified_package_files": checked,
    }


__all__ = [
    "DistributionError",
    "compare_wheel_payloads",
    "inspect_wheel",
    "verify_installed_wheel",
]
