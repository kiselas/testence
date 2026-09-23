"""Conflict-safe installation of the bundled Testence skills into agent clients."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path, PurePosixPath
from typing import Any

from testence.managed_paths import ManagedPathError, checked_member, is_shell_metadata

from .pack import bundled_skills, load_skill_pack

AGENT_INSTALL_SCHEMA = "testence/agent-install/1"
AGENT_INSTALL_RECEIPT_SCHEMA = "testence/agent-install-receipt/1"
CLIENT_ROOTS = {"codex": PurePosixPath(".agents/skills"), "claude": PurePosixPath(".claude/skills")}


class AgentInstallError(ValueError):
    """The requested client install is unsafe or its state is invalid."""


@dataclass(frozen=True)
class SkillFile:
    relative: PurePosixPath
    content: bytes
    digest: str


def _sha(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def skill_pack_digest() -> str:
    material = bytearray(files(__package__).joinpath("skill-pack.json").read_bytes())
    for item in bundled_files():
        encoded = item.relative.as_posix().encode("utf-8")
        material.extend(len(encoded).to_bytes(4, "big") + encoded)
        material.extend(len(item.content).to_bytes(8, "big") + item.content)
    return _sha(bytes(material))


def _walk(root: Any, prefix: PurePosixPath) -> list[SkillFile]:
    result: list[SkillFile] = []
    for child in sorted(root.iterdir(), key=lambda item: item.name):
        relative = prefix / child.name
        # An editable checkout reads skills from the source tree, where Finder may
        # have left .DS_Store; it is not part of the pack and must not change its digest.
        if isinstance(child, Path) and is_shell_metadata(child):
            continue
        if child.is_dir():
            result.extend(_walk(child, relative))
        elif child.is_file():
            raw = child.read_bytes()
            result.append(SkillFile(relative, raw, _sha(raw)))
    return result


def bundled_files() -> tuple[SkillFile, ...]:
    result: list[SkillFile] = []
    for name, root in bundled_skills().items():
        result.extend(_walk(root, PurePosixPath(name)))
    return tuple(result)


def _state_path(project: Path) -> Path:
    try:
        return checked_member(project, ".testence/agents.json")
    except ManagedPathError as exc:
        raise AgentInstallError(str(exc)) from exc


def _read_state(project: Path) -> dict[str, Any]:
    path = _state_path(project)
    if not path.exists():
        return {"schema": AGENT_INSTALL_SCHEMA, "clients": {}}
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("schema") != AGENT_INSTALL_SCHEMA:
        raise AgentInstallError(f"unsupported agent install state: {path}")
    if not isinstance(document.get("clients"), dict):
        raise AgentInstallError(f"invalid agent install state: {path}")
    return document


def _state_bytes(document: dict[str, Any]) -> bytes:
    return (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _target(project: Path, client: str, relative: PurePosixPath) -> Path:
    if client not in CLIENT_ROOTS:
        raise AgentInstallError(f"unsupported agent client: {client!r}")
    member = CLIENT_ROOTS[client] / relative
    try:
        return checked_member(project, member)
    except ManagedPathError as exc:
        raise AgentInstallError(f"unsafe agent skill target {member.as_posix()!r}: {exc}") from exc


def _install_skills_locked(
    project: Path,
    clients: list[str] | tuple[str, ...],
    commit: Any,
) -> dict[str, Any]:
    """Install/update the exact bundled pack while preserving locally modified files."""
    project = project.resolve()
    if not project.is_dir():
        raise AgentInstallError(f"project directory does not exist: {project}")
    requested = list(dict.fromkeys(clients))
    if not requested:
        raise AgentInstallError("at least one agent client is required")
    state = _read_state(project)
    pack = load_skill_pack()
    digest = skill_pack_digest()
    source_files = bundled_files()
    results: list[dict[str, Any]] = []
    pending: list[tuple[str, PurePosixPath, SkillFile]] = []

    for client in requested:
        if client not in CLIENT_ROOTS:
            raise AgentInstallError(f"unsupported agent client: {client!r}")
        prior = state["clients"].get(client, {})
        tracked = {
            item["path"]: item["sha256"]
            for item in prior.get("files", [])
            if isinstance(item, dict) and isinstance(item.get("path"), str)
        }
        installed: list[str] = []
        unchanged: list[str] = []
        conflicts: list[dict[str, str]] = []
        accepted: list[dict[str, str]] = []
        for item in source_files:
            relative = item.relative.as_posix()
            target = _target(project, client, item.relative)
            current = _sha(target.read_bytes()) if target.is_file() else None
            prior_digest = tracked.get(relative)
            if current == item.digest:
                unchanged.append(relative)
                accepted.append({"path": relative, "sha256": item.digest})
                continue
            if current is not None and current != prior_digest:
                conflicts.append(
                    {"path": relative, "expected": prior_digest or "unmanaged", "actual": current}
                )
                continue
            installed.append(relative)
            accepted.append({"path": relative, "sha256": item.digest})
            pending.append((client, item.relative, item))

        client_status = "conflict" if conflicts else "installed"
        if not conflicts:
            state["clients"][client] = {
                "root": CLIENT_ROOTS[client].as_posix(),
                "status": client_status,
                "pack_version": pack["version"],
                "pack_digest": digest,
                "files": accepted,
                "conflicts": conflicts,
            }
        results.append(
            {
                "client": client,
                "status": client_status,
                "root": CLIENT_ROOTS[client].as_posix(),
                "installed": installed,
                "unchanged": unchanged,
                "conflicts": conflicts,
            }
        )

    has_conflicts = any(item["conflicts"] for item in results)
    if has_conflicts:
        return {
            "schema": AGENT_INSTALL_RECEIPT_SCHEMA,
            "status": "conflict",
            "project": str(project),
            "pack_schema": pack["schema"],
            "pack_version": pack["version"],
            "pack_digest": digest,
            "clients": results,
            "state": ".testence/agents.json",
        }
    state.update(
        {
            "schema": AGENT_INSTALL_SCHEMA,
            "pack_schema": pack["schema"],
            "pack_version": pack["version"],
            "pack_digest": digest,
        }
    )
    operations = [
        ((CLIENT_ROOTS[client] / pending_relative).as_posix(), item.content)
        for client, pending_relative, item in pending
    ]
    operations.append((".testence/agents.json", _state_bytes(state)))
    commit(operations)
    return {
        "schema": AGENT_INSTALL_RECEIPT_SCHEMA,
        "status": "installed",
        "project": str(project),
        "pack_schema": pack["schema"],
        "pack_version": pack["version"],
        "pack_digest": digest,
        "clients": results,
        "state": str(_state_path(project).relative_to(project)).replace("\\", "/"),
    }


def install_skills(project: Path, clients: list[str] | tuple[str, ...]) -> dict[str, Any]:
    """Install/update one exact pack as a recoverable project transaction."""

    from testence.quality import QualityPackError, managed_writer

    resolved = project.resolve()
    if not resolved.is_dir():
        raise AgentInstallError(f"project directory does not exist: {resolved}")
    try:
        with managed_writer(resolved) as commit:
            return _install_skills_locked(resolved, clients, commit)
    except (ManagedPathError, OSError, QualityPackError) as exc:
        raise AgentInstallError(f"cannot install agent skills: {exc}") from exc


def verify_skills(project: Path, clients: list[str] | tuple[str, ...]) -> dict[str, Any]:
    """Verify that every bundled file is present byte-for-byte for each client."""
    project = project.resolve()
    state = _read_state(project)
    pack = load_skill_pack()
    digest = skill_pack_digest()
    requested = list(dict.fromkeys(clients))
    if not requested:
        requested = sorted(state["clients"])
    if not requested:
        raise AgentInstallError("no installed agent clients to verify")
    source_files = bundled_files()
    results: list[dict[str, Any]] = []
    for client in requested:
        drift: list[dict[str, str]] = []
        for item in source_files:
            relative = item.relative.as_posix()
            target = _target(project, client, item.relative)
            actual = _sha(target.read_bytes()) if target.is_file() else "missing"
            if actual != item.digest:
                drift.append({"path": relative, "expected": item.digest, "actual": actual})
        record = state["clients"].get(client)
        state_matches = bool(record) and record.get("pack_digest") == digest
        status = "valid" if not drift and state_matches else "drift"
        results.append(
            {"client": client, "status": status, "drift": drift, "state_matches": state_matches}
        )
    return {
        "schema": AGENT_INSTALL_RECEIPT_SCHEMA,
        "status": "valid" if all(item["status"] == "valid" for item in results) else "drift",
        "project": str(project),
        "pack_schema": pack["schema"],
        "pack_version": pack["version"],
        "pack_digest": digest,
        "clients": results,
        "state": str(_state_path(project).relative_to(project)).replace("\\", "/"),
    }


__all__ = [
    "AGENT_INSTALL_RECEIPT_SCHEMA",
    "AGENT_INSTALL_SCHEMA",
    "AgentInstallError",
    "CLIENT_ROOTS",
    "bundled_files",
    "install_skills",
    "skill_pack_digest",
    "verify_skills",
]
