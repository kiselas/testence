from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from testence.agent import AgentInstallError, install_skills
from testence.application import ApplicationError, init_project
from testence.managed_paths import (
    ManagedPathError,
    atomic_write_bytes,
    checked_member,
    portable_parts,
)


@pytest.mark.parametrize(
    "value",
    [
        "../outside",
        "/outside",
        "D:/outside",
        "C:relative",
        "\\\\server\\share",
        "folder\\file",
        "name:stream",
        "safe/../outside",
        "safe//file",
        "safe/trailing.",
        "safe/trailing ",
        "CON/file",
    ],
)
def test_portable_managed_paths_reject_ambiguous_spellings(value: str):
    with pytest.raises(ManagedPathError):
        portable_parts(value)


def test_atomic_replace_does_not_modify_a_hardlink_sentinel(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"outside")
    target = root / "managed.txt"
    os.link(outside, target)

    atomic_write_bytes(root, "managed.txt", b"managed")

    assert outside.read_bytes() == b"outside"
    assert target.read_bytes() == b"managed"


def _make_directory_link(link: Path, target: Path) -> None:
    if os.name == "nt":
        command = f"New-Item -ItemType Junction -Path '{link}' -Target '{target}'"
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode:
            pytest.skip(f"junctions are unavailable: {completed.stderr.strip()}")
    else:
        link.symlink_to(target, target_is_directory=True)


def test_checked_member_rejects_a_directory_link_below_root(tmp_path: Path):
    root = tmp_path / "project"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    link = root / ".testence"
    _make_directory_link(link, outside)
    try:
        with pytest.raises(ManagedPathError, match="link or reparse"):
            checked_member(root, ".testence/state.json")
    finally:
        if os.name == "nt" and link.exists():
            os.rmdir(link)


@pytest.mark.parametrize(
    ("action", "error"),
    [
        (lambda project: install_skills(project, ["codex"]), AgentInstallError),
        (init_project, ApplicationError),
    ],
)
def test_project_commands_refuse_a_linked_state_root(tmp_path: Path, action, error):
    project = tmp_path / "project"
    outside = tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_bytes(b"unchanged")
    link = project / ".testence"
    _make_directory_link(link, outside)
    try:
        with pytest.raises(error, match="link or reparse"):
            action(project)
        assert sentinel.read_bytes() == b"unchanged"
        assert sorted(item.name for item in outside.iterdir()) == ["sentinel.txt"]
    finally:
        if os.name == "nt" and link.exists():
            os.rmdir(link)
