"""Bundled, client-neutral Agent Skills for the Testence proof workflow."""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import PurePosixPath
from typing import Any

try:
    from importlib.resources.abc import Traversable
except ImportError:  # Python 3.10
    from importlib.abc import Traversable

SKILL_PACK_SCHEMA = "testence/skill-pack/1"


def load_skill_pack() -> dict[str, Any]:
    """Load the packaged skill manifest without depending on a source checkout."""
    resource = files(__package__).joinpath("skill-pack.json")
    document = json.loads(resource.read_text(encoding="utf-8"))
    if document.get("schema") != SKILL_PACK_SCHEMA:
        raise RuntimeError(f"unsupported bundled skill-pack schema: {document.get('schema')!r}")
    return document


def bundled_skills() -> dict[str, Traversable]:
    """Return skill names mapped to their packaged roots in manifest order."""
    root = files(__package__)
    result: dict[str, Traversable] = {}
    for entry in load_skill_pack()["skills"]:
        path = PurePosixPath(entry["path"])
        if path.is_absolute() or ".." in path.parts or path.parts[:1] != ("skills",):
            raise RuntimeError(f"unsafe bundled skill path: {entry['path']!r}")
        result[entry["name"]] = root.joinpath(*path.parts)
    return result


__all__ = ["SKILL_PACK_SCHEMA", "bundled_skills", "load_skill_pack"]
