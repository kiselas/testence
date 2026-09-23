"""Portable containment and atomic replacement for Testence-managed project files."""

from __future__ import annotations

import os
import re
import stat
import tempfile
import time
from pathlib import Path, PurePosixPath


class ManagedPathError(ValueError):
    """A managed path is ambiguous or crosses its declared root."""


_DRIVE = re.compile(r"^[A-Za-z]:")
_WINDOWS_RESERVED = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
}


#: Files a desktop shell writes into any folder a person opens: Finder's ``.DS_Store``,
#: the AppleDouble ``._name`` companions macOS leaves on SMB/exFAT volumes, and
#: Explorer's ``Thumbs.db``/``desktop.ini``. They carry no Testence state, so a walker
#: over a managed directory skips them instead of treating them as members.
_SHELL_METADATA = {".ds_store", "thumbs.db", "desktop.ini"}


def is_shell_metadata(path: Path) -> bool:
    """True for a regular file the OS file manager created, never for a directory."""
    name = path.name
    if name.casefold() not in _SHELL_METADATA and not name.startswith("._"):
        return False
    try:
        return stat.S_ISREG(path.lstat().st_mode)
    except OSError:
        return False


def portable_parts(relative: str | PurePosixPath) -> tuple[str, ...]:
    """Parse one portable, project-relative member without host-specific shortcuts."""
    value = relative.as_posix() if isinstance(relative, PurePosixPath) else relative
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ManagedPathError("managed path must be a non-empty string")
    if value.startswith(("/", "\\")) or "\\" in value or _DRIVE.match(value) or ":" in value:
        raise ManagedPathError(f"managed path must be portable and relative: {value!r}")
    parts = value.split("/")
    for part in parts:
        stem = part.split(".", 1)[0].casefold()
        if (
            not part
            or part in {".", ".."}
            or part.endswith((" ", "."))
            or stem in _WINDOWS_RESERVED
        ):
            raise ManagedPathError(
                f"managed path escapes its root or contains an unsafe component: {value!r}"
            )
    return tuple(parts)


def _is_link_like(path: Path) -> bool:
    """Detect symbolic links and Windows junction/reparse-point ancestors."""
    try:
        details = path.lstat()
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(details.st_mode):
        return True
    attributes = getattr(details, "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse)


def _within(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return candidate != root


def checked_member(root: Path, relative: str | PurePosixPath) -> Path:
    """Return a contained member and reject link-like components below ``root``."""
    resolved_root = root.resolve(strict=True)
    parts = portable_parts(relative)
    current = resolved_root
    for part in parts:
        current = current / part
        if os.path.lexists(current) and _is_link_like(current):
            raise ManagedPathError(f"managed path crosses a link or reparse point: {relative!s}")
    candidate = resolved_root.joinpath(*parts)
    resolved_candidate = candidate.resolve(strict=False)
    if not _within(resolved_candidate, resolved_root):
        raise ManagedPathError(f"managed path escapes its root: {relative!s}")
    return candidate


def ensure_parent(root: Path, relative: str | PurePosixPath) -> Path:
    """Create missing directories for a checked member and revalidate each component."""
    member = checked_member(root, relative)
    resolved_root = root.resolve(strict=True)
    cursor = resolved_root
    relative_parent = member.parent.relative_to(resolved_root)
    for part in relative_parent.parts:
        cursor = cursor / part
        try:
            cursor.mkdir()
        except FileExistsError:
            pass
        if not cursor.is_dir() or _is_link_like(cursor):
            raise ManagedPathError(f"managed parent is not a safe directory: {cursor}")
    return checked_member(resolved_root, "/".join(member.relative_to(resolved_root).parts))


def atomic_write_bytes(
    root: Path,
    relative: str | PurePosixPath,
    content: bytes,
    *,
    replace_retries: int = 3,
) -> Path:
    """Replace a contained regular file without following its prior hardlink inode."""
    target = ensure_parent(root, relative)
    parent_relative = target.parent.relative_to(root.resolve(strict=True)).as_posix()
    if parent_relative != ".":
        checked_member(root, parent_relative)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(replace_retries + 1):
            target = checked_member(root, relative)
            try:
                os.replace(temporary, target)
                break
            except PermissionError:
                if attempt >= replace_retries:
                    raise
                time.sleep(0.02 * (attempt + 1))
        if target.read_bytes() != content:
            raise OSError(f"managed write verification failed: {target}")
        return target
    finally:
        if temporary.exists():
            temporary.unlink()


__all__ = [
    "ManagedPathError",
    "atomic_write_bytes",
    "checked_member",
    "ensure_parent",
    "is_shell_metadata",
    "portable_parts",
]
