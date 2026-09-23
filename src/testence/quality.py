"""Versioned multi-project quality packs and artifact-free QA summaries."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import shutil
import sys
import time
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from testence.contracts.versions import (
    QUALITY_LOCK_SCHEMA,
    QUALITY_PACK_SCHEMA,
    QUALITY_SUMMARY_SCHEMA,
    QUALITY_SYNC_SCHEMA,
)
from testence.export._model import LoadedRun
from testence.managed_paths import (
    ManagedPathError,
    atomic_write_bytes,
    checked_member,
    is_shell_metadata,
)
from testence.metrics import load_run


class QualityPackError(ValueError):
    pass


def _collision_key(relative: str) -> str:
    """Identity of a path on case-insensitive, normalization-insensitive file systems.

    Default APFS and NTFS store ``A.json`` and ``a.json`` (or the NFC and NFD
    spellings of ``é``) as one file, so a pack listing both would land a single file
    while its lock tracks two. Comparing this key keeps a pack installable on every
    supported platform, not only on the Linux host that built it.
    """
    return unicodedata.normalize("NFC", unicodedata.normalize("NFC", relative).casefold())


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _inside(root: Path, relative: str) -> Path:
    try:
        return checked_member(root, relative)
    except ManagedPathError as exc:
        raise QualityPackError(str(exc)) from exc


def _write_json(root: Path, relative: str, document: dict[str, Any]) -> None:
    raw = _json_bytes(document)
    try:
        atomic_write_bytes(root, relative, raw)
    except (ManagedPathError, OSError) as exc:
        raise QualityPackError(f"cannot write managed quality file {relative!r}: {exc}") from exc


def _json_bytes(document: dict[str, Any]) -> bytes:
    return (
        json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()


@contextmanager
def _quality_lock(project: Path) -> Iterator[None]:
    """Hold a process-scoped nonblocking lock; the OS releases it after a crash."""
    lock_path = _inside(project, ".testence/quality-operation.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+b")
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl = importlib.import_module("fcntl")
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise QualityPackError("another quality pack operation is in progress") from exc
        yield
    finally:
        try:
            handle.seek(0)
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl = importlib.import_module("fcntl")
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        handle.close()


def _cleanup_transaction(project: Path, relative: str) -> None:
    # Windows may briefly retain a deleted child (scanner/indexer handles). Retry
    # only those transient filesystem errors, never a transaction or UI action.
    for attempt in range(4):
        directory = _inside(project, relative)
        if not directory.exists():
            return
        try:
            shutil.rmtree(directory)
            return
        except OSError as exc:
            if getattr(exc, "winerror", None) not in {32, 145} or attempt == 3:
                raise
            time.sleep(0.025 * (attempt + 1))


def _recover_transactions(project: Path) -> None:
    root = _inside(project, ".testence/quality-transactions")
    if not root.exists():
        return
    if not root.is_dir():
        raise QualityPackError("quality transaction state is not a directory")
    for directory in sorted(root.iterdir()):
        if is_shell_metadata(directory):
            # Finder leaves .DS_Store in a folder someone opened; it is not a
            # transaction and must not block recovery of the real ones.
            continue
        relative = f".testence/quality-transactions/{directory.name}"
        journal = _load_json(_inside(project, relative + "/journal.json"))
        if not journal:
            raise QualityPackError(f"incomplete quality transaction journal: {directory.name}")
        if journal.get("state") in {"committed", "recovered"}:
            _cleanup_transaction(project, relative)
            continue
        operations = journal.get("operations")
        if not isinstance(operations, list):
            raise QualityPackError(f"invalid quality transaction journal: {directory.name}")
        recovery: list[tuple[dict[str, Any], Path, bytes | None]] = []
        conflicts: list[dict[str, str]] = []
        for index, operation in enumerate(operations):
            if not isinstance(operation, dict) or not isinstance(operation.get("path"), str):
                raise QualityPackError(f"invalid operation in transaction {directory.name}")
            target = _inside(project, operation["path"])
            observed = _digest(target.read_bytes()) if target.is_file() else None
            old: bytes | None = None
            if operation.get("old_exists"):
                snapshot = _inside(project, f"{relative}/old/{index:04d}.bin")
                if not snapshot.is_file():
                    raise QualityPackError(
                        f"quality transaction recovery snapshot is unavailable: {operation['path']}"
                    )
                raw = snapshot.read_bytes()
                if _digest(raw) != operation.get("old_sha256"):
                    raise QualityPackError(
                        f"quality transaction recovery snapshot is corrupt: {operation['path']}"
                    )
                old = raw
                expected_states = {operation.get("old_sha256"), operation.get("new_sha256")}
                if observed is None and not operation.get("new_exists"):
                    pass
                elif observed not in expected_states:
                    conflicts.append(
                        {
                            "path": operation["path"],
                            "expected": str(sorted(value for value in expected_states if value)),
                            "observed": str(observed or "absent"),
                        }
                    )
            elif observed not in {None, operation.get("new_sha256")}:
                conflicts.append(
                    {
                        "path": operation["path"],
                        "expected": str(operation.get("new_sha256") or "absent"),
                        "observed": str(observed),
                    }
                )
            recovery.append((operation, target, old))
        if conflicts:
            journal["state"] = "conflict"
            journal["recovery_conflicts"] = conflicts
            _write_json(project, relative + "/journal.json", journal)
            raise QualityPackError(
                "quality transaction recovery conflicts with newer project changes: "
                + ", ".join(item["path"] for item in conflicts)
            )
        journal["state"] = "recovering"
        journal["progress"] = 0
        journal.pop("recovery_conflicts", None)
        _write_json(project, relative + "/journal.json", journal)
        for index, (operation, target, old) in enumerate(recovery):
            if old is not None:
                observed = _digest(target.read_bytes()) if target.is_file() else None
                if observed != operation.get("old_sha256"):
                    atomic_write_bytes(project, operation["path"], old)
            elif target.is_file():
                target.unlink()
            journal["progress"] = index + 1
            _write_json(project, relative + "/journal.json", journal)
        journal["state"] = "recovered"
        _write_json(project, relative + "/journal.json", journal)
        _cleanup_transaction(project, relative)


def _commit_transaction(project: Path, operations: list[tuple[str, bytes | None]]) -> None:
    """Apply a set of file replacements/deletions with rollback after interruption."""
    if not operations:
        return
    paths = [relative for relative, _raw in operations]
    if len({_collision_key(relative) for relative in paths}) != len(paths):
        raise QualityPackError("quality transaction contains duplicate target paths")
    for relative in paths:
        _inside(project, relative)

    transaction = uuid4().hex
    base = f".testence/quality-transactions/{transaction}"
    entries: list[dict[str, Any]] = []
    try:
        for index, (relative, incoming) in enumerate(operations):
            target = _inside(project, relative)
            old = target.read_bytes() if target.is_file() else None
            entry = {
                "path": relative,
                "old_exists": old is not None,
                "old_sha256": _digest(old) if old is not None else None,
                "new_exists": incoming is not None,
                "new_sha256": _digest(incoming) if incoming is not None else None,
            }
            entries.append(entry)
            if old is not None:
                atomic_write_bytes(project, f"{base}/old/{index:04d}.bin", old)
            if incoming is not None:
                atomic_write_bytes(project, f"{base}/new/{index:04d}.bin", incoming)
        journal = {
            "schema": "testence/quality-transaction/1",
            "id": transaction,
            "state": "prepared",
            "progress": 0,
            "operations": entries,
        }
        _write_json(project, base + "/journal.json", journal)
        journal["state"] = "applying"
        _write_json(project, base + "/journal.json", journal)
        for index, (relative, incoming) in enumerate(operations):
            if incoming is None:
                target = _inside(project, relative)
                if target.is_file():
                    target.unlink()
            else:
                staged = _inside(project, f"{base}/new/{index:04d}.bin").read_bytes()
                if _digest(staged) != entries[index]["new_sha256"]:
                    raise QualityPackError(f"quality transaction stage is corrupt: {relative}")
                atomic_write_bytes(project, relative, staged)
            journal["progress"] = index + 1
            _write_json(project, base + "/journal.json", journal)
        journal["state"] = "committed"
        _write_json(project, base + "/journal.json", journal)
        _cleanup_transaction(project, base)
    except BaseException:
        if _inside(project, base + "/journal.json").is_file():
            _recover_transactions(project)
        else:
            _cleanup_transaction(project, base)
        raise


@contextmanager
def managed_writer(project: Path) -> Iterator[Any]:
    """Serialize a managed multi-file change and recover an interrupted predecessor."""

    resolved = project.resolve(strict=True)
    try:
        with _quality_lock(resolved):
            _recover_transactions(resolved)
            yield lambda operations: _commit_transaction(resolved, operations)
    except QualityPackError:
        raise


def _inventory_digest(entries: list[dict[str, Any]]) -> str:
    material = bytearray()
    for entry in sorted(entries, key=lambda item: str(item["path"])):
        encoded = str(entry["path"]).encode("utf-8")
        digest = str(entry["sha256"]).encode("ascii")
        material.extend(len(encoded).to_bytes(4, "big") + encoded)
        material.extend(len(digest).to_bytes(2, "big") + digest)
    return _digest(bytes(material))


@dataclass(frozen=True)
class QualityPack:
    root: Path
    name: str
    version: str
    digest: str
    files: tuple[dict[str, Any], ...]
    policy: dict[str, Any]


def load_quality_pack(path: Path | str) -> QualityPack:
    root = Path(path).resolve()
    manifest_path = root / "quality-pack.json"
    try:
        raw = manifest_path.read_bytes()
        document = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QualityPackError(f"cannot read quality-pack.json: {exc}") from exc
    if not isinstance(document, dict) or document.get("schema") != QUALITY_PACK_SCHEMA:
        raise QualityPackError("unsupported quality pack schema")
    name = str(document.get("name") or "").strip()
    version = str(document.get("version") or "").strip()
    files = document.get("files")
    policy = document.get("policy")
    if not name or not version or not isinstance(files, list) or not isinstance(policy, dict):
        raise QualityPackError("quality pack requires name, version, files and policy")
    seen: set[str] = set()
    spellings: dict[str, str] = {}
    checked: list[dict[str, Any]] = []
    hash_material = bytearray(raw)
    for index, entry in enumerate(files):
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
            raise QualityPackError(f"quality pack files[{index}] is invalid")
        relative = str(entry["path"]).replace("\\", "/")
        source = _inside(root, relative)
        if (
            relative in seen
            or relative == "testence.json"
            or relative.startswith(".")
            or "/." in relative
        ):
            raise QualityPackError(f"quality pack file path is duplicate or hidden: {relative!r}")
        other = spellings.setdefault(_collision_key(relative), relative)
        if other != relative:
            raise QualityPackError(
                f"quality pack paths {other!r} and {relative!r} name the same file on "
                "case-insensitive file systems (default macOS and Windows)"
            )
        if re.search(r"(^|/)(?:\.env|credentials?|secrets?)(?:\.|/|$)", relative, re.I):
            raise QualityPackError(f"quality pack must not contain credential files: {relative!r}")
        try:
            content = source.read_bytes()
        except OSError as exc:
            raise QualityPackError(f"quality pack file cannot be read: {relative}: {exc}") from exc
        actual = _digest(content)
        if entry["sha256"] != actual:
            raise QualityPackError(f"quality pack digest mismatch: {relative}")
        if b"BEGIN PRIVATE KEY" in content or re.search(rb"(?im)^\s*password\s*=", content):
            raise QualityPackError(f"quality pack contains credential-like content: {relative}")
        seen.add(relative)
        checked.append({"path": relative, "sha256": actual, "bytes": len(content)})
        hash_material.extend(relative.encode("utf-8") + b"\0" + content)
    return QualityPack(
        root=root,
        name=name,
        version=version,
        digest=_digest(bytes(hash_material)),
        files=tuple(checked),
        policy=dict(policy),
    )


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QualityPackError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise QualityPackError(f"{path} must contain an object")
    return value


def _active_overrides(project: Path) -> dict[str, dict[str, Any]]:
    document = _load_json(_inside(project, ".testence/quality-overrides.json"))
    entries = document.get("overrides", [])
    if not isinstance(entries, list):
        raise QualityPackError("quality-overrides.json overrides must be an array")
    result: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise QualityPackError(f"override[{index}] must be an object")
        required = {"path", "reason", "owner", "expires"}
        if not required <= entry.keys() or not all(str(entry[key]).strip() for key in required):
            raise QualityPackError(f"override[{index}] requires path/reason/owner/expires")
        try:
            expiry = date.fromisoformat(str(entry["expires"]))
        except ValueError as exc:
            raise QualityPackError(f"override[{index}] expires must be YYYY-MM-DD") from exc
        if expiry < date.today():
            raise QualityPackError(f"override expired for {entry['path']}: {expiry.isoformat()}")
        relative = str(entry["path"]).replace("\\", "/")
        _inside(project, relative)
        result[relative] = dict(entry)
    return result


def apply_quality_pack(
    pack_dir: Path | str, project_dir: Path | str, *, dry_run: bool = False
) -> dict[str, Any]:
    project = Path(project_dir).absolute()
    project.mkdir(parents=True, exist_ok=True)
    project = project.resolve(strict=True)
    with _quality_lock(project):
        _recover_transactions(project)
        return _apply_quality_pack(load_quality_pack(pack_dir), project, dry_run=dry_run)


def _apply_quality_pack(
    pack: QualityPack, project: Path, *, dry_run: bool = False
) -> dict[str, Any]:
    _inside(project, ".testence/quality-sync.json")
    lock_path = _inside(project, ".testence/quality-pack.lock.json")
    previous = _load_json(lock_path)
    config_path = _inside(project, "testence.json")
    project_config = _load_json(config_path)
    old_files = {
        str(entry.get("path")): entry
        for entry in previous.get("files", [])
        if isinstance(entry, dict) and entry.get("path")
    }
    overrides = _active_overrides(project)
    changed: list[str] = []
    unchanged: list[str] = []
    preserved: list[dict[str, Any]] = []
    conflicts: list[dict[str, str]] = []
    configured = project_config.get("quality_pack")
    if isinstance(configured, dict) and previous.get("digest"):
        configured_digest = configured.get("digest")
        if configured_digest and configured_digest != previous.get("digest"):
            conflicts.append(
                {
                    "path": "testence.json#quality_pack",
                    "expected_previous": str(previous.get("digest")),
                    "observed": str(configured_digest),
                    "incoming": pack.digest,
                }
            )

    if conflicts:
        report = {
            "schema": QUALITY_SYNC_SCHEMA,
            "project_id": project_config.get("project_id", project.name),
            "pack": {"name": pack.name, "version": pack.version, "digest": pack.digest},
            "status": "conflict",
            "changed": [],
            "unchanged": [],
            "overrides": [],
            "conflicts": conflicts,
        }
        report["plan"] = {
            "add": [],
            "replace": [],
            "delete": [],
            "keep": [],
            "preserve": [],
            "conflicts": [item["path"] for item in conflicts],
        }
        if not dry_run:
            _write_json(project, ".testence/quality-sync.json", report)
        return report

    installed: list[dict[str, Any]] = []
    pending_writes: list[tuple[str, bytes]] = []
    pending_deletes: list[str] = []
    planned_adds: list[str] = []
    planned_replacements: list[str] = []
    incoming_paths = {str(entry["path"]) for entry in pack.files}
    for entry in pack.files:
        relative = str(entry["path"])
        source = _inside(pack.root, relative)
        target = _inside(project, relative)
        current_digest = _digest(target.read_bytes()) if target.is_file() else None
        previous_entry = old_files.get(relative, {})
        previous_digest = previous_entry.get("pack_sha256", previous_entry.get("sha256"))
        if current_digest == entry["sha256"]:
            unchanged.append(relative)
        elif current_digest is None or current_digest == previous_digest:
            changed.append(relative)
            (planned_adds if current_digest is None else planned_replacements).append(relative)
            current_digest = str(entry["sha256"])
            pending_writes.append((relative, source.read_bytes()))
        elif relative in overrides:
            preserved.append({"path": relative, **overrides[relative]})
        else:
            conflicts.append(
                {
                    "path": relative,
                    "expected_previous": str(previous_digest or "absent"),
                    "observed": str(current_digest),
                    "incoming": str(entry["sha256"]),
                }
            )
        installed.append(
            {
                "path": relative,
                "sha256": str(current_digest or entry["sha256"]),
                "pack_sha256": str(entry["sha256"]),
            }
        )

    for relative, previous_entry in old_files.items():
        if relative in incoming_paths:
            continue
        target = _inside(project, relative)
        current_digest = _digest(target.read_bytes()) if target.is_file() else None
        accepted_digest = previous_entry.get("sha256")
        if current_digest is None:
            continue
        if current_digest == accepted_digest:
            changed.append(relative)
            pending_deletes.append(relative)
        elif relative in overrides:
            preserved.append({"path": relative, **overrides[relative]})
            installed.append(
                {
                    "path": relative,
                    "sha256": str(current_digest),
                    "pack_sha256": "removed",
                }
            )
        else:
            conflicts.append(
                {
                    "path": relative,
                    "expected_previous": str(accepted_digest or "absent"),
                    "observed": str(current_digest),
                    "incoming": "removed",
                }
            )

    status = "conflict" if conflicts else "applied"
    lock = {
        "schema": QUALITY_LOCK_SCHEMA,
        "name": pack.name,
        "version": pack.version,
        "digest": pack.digest,
        "effective_digest": _inventory_digest(installed),
        "source": str(pack.root),
        "files": installed,
        "policy": pack.policy,
        "status": status,
    }
    report = {
        "schema": QUALITY_SYNC_SCHEMA,
        "project_id": _load_json(config_path).get("project_id", project.name),
        "pack": {"name": pack.name, "version": pack.version, "digest": pack.digest},
        "status": status,
        "changed": sorted(changed),
        "unchanged": sorted(unchanged),
        "overrides": preserved,
        "conflicts": conflicts,
    }
    report["plan"] = {
        "add": sorted(planned_adds),
        "replace": sorted(planned_replacements),
        "delete": sorted(pending_deletes),
        "keep": sorted(unchanged),
        "preserve": sorted(str(item["path"]) for item in preserved),
        "conflicts": sorted(str(item["path"]) for item in conflicts),
    }
    if dry_run:
        report["status"] = "conflict" if conflicts else "planned"
        return report
    if conflicts:
        _write_json(project, ".testence/quality-sync.json", report)
        return report

    if previous.get("digest"):
        history_relative = ".testence/quality-pack-history/" + str(previous["digest"]).replace(
            ":", "-"
        )
        history_lock = _inside(project, history_relative + "/lock.json")
        if not history_lock.exists():
            history_document = dict(previous)
            history_entries = [
                dict(item) for item in previous.get("files", []) if isinstance(item, dict)
            ]
            for relative, entry in old_files.items():
                current = _inside(project, relative)
                if current.is_file():
                    raw = current.read_bytes()
                    actual = _digest(raw)
                    if actual != entry.get("sha256") and relative not in overrides:
                        raise QualityPackError(
                            f"cannot archive changed quality pack file: {relative}"
                        )
                    atomic_write_bytes(project, history_relative + "/" + relative, raw)
                    for history_entry in history_entries:
                        if history_entry.get("path") == relative:
                            history_entry["sha256"] = actual
            history_document["files"] = history_entries
            history_document["effective_digest"] = _inventory_digest(history_entries)
            _write_json(project, history_relative + "/lock.json", history_document)

    project_config["quality_pack"] = {
        "name": pack.name,
        "version": pack.version,
        "digest": pack.digest,
        "effective_digest": lock["effective_digest"],
    }
    operations: list[tuple[str, bytes | None]] = [
        *pending_writes,
        *((relative, None) for relative in pending_deletes),
        (".testence/quality-pack.lock.json", _json_bytes(lock)),
        ("testence.json", _json_bytes(project_config)),
        (".testence/quality-sync.json", _json_bytes(report)),
    ]
    _commit_transaction(project, operations)
    for entry in installed:
        actual = _digest(_inside(project, str(entry["path"])).read_bytes())
        if actual != entry["sha256"]:
            raise QualityPackError(f"quality pack apply verification failed: {entry['path']}")
    return report


def rollback_quality_pack(project_dir: Path | str, digest: str) -> dict[str, Any]:
    project = Path(project_dir).resolve()
    with _quality_lock(project):
        _recover_transactions(project)
        return _rollback_quality_pack(project, digest)


def _rollback_quality_pack(project: Path, digest: str) -> dict[str, Any]:
    history_relative = ".testence/quality-pack-history/" + digest.replace(":", "-")
    archived_lock = _load_json(_inside(project, history_relative + "/lock.json"))
    if archived_lock.get("digest") != digest:
        raise QualityPackError(f"quality pack history is unavailable for {digest}")
    current_lock = _load_json(_inside(project, ".testence/quality-pack.lock.json"))
    current_files = {
        str(entry.get("path")): entry
        for entry in current_lock.get("files", [])
        if isinstance(entry, dict) and entry.get("path")
    }
    conflicts: list[dict[str, str]] = []
    archived_entries = [
        entry for entry in archived_lock.get("files", []) if isinstance(entry, dict)
    ]
    snapshots: dict[str, bytes] = {}
    for entry in archived_entries:
        relative = str(entry.get("path") or "")
        snapshot = _inside(project, history_relative + "/" + relative)
        if not snapshot.is_file():
            raise QualityPackError(f"quality pack history file is unavailable: {relative}")
        raw = snapshot.read_bytes()
        if _digest(raw) != entry.get("sha256"):
            raise QualityPackError(f"quality pack history digest mismatch: {relative}")
        snapshots[relative] = raw
        target = _inside(project, relative)
        expected = current_files.get(relative, {}).get("pack_sha256")
        observed = _digest(target.read_bytes()) if target.is_file() else None
        if expected and observed not in {expected, entry.get("sha256")}:
            conflicts.append(
                {"path": relative, "expected_current": str(expected), "observed": str(observed)}
            )
    archived_paths = set(snapshots)
    delete_after_restore: list[str] = []
    for relative, entry in current_files.items():
        if relative in archived_paths:
            continue
        target = _inside(project, relative)
        observed = _digest(target.read_bytes()) if target.is_file() else None
        expected = entry.get("sha256")
        if observed is None:
            continue
        if observed == expected:
            delete_after_restore.append(relative)
        else:
            conflicts.append(
                {"path": relative, "expected_current": str(expected), "observed": str(observed)}
            )
    restored: list[str] = []
    status = "conflict" if conflicts else "rolled_back"
    project_config = _load_json(_inside(project, "testence.json"))
    restored_lock: dict[str, Any] | None = None
    if not conflicts:
        restored = [str(entry.get("path") or "") for entry in archived_entries]
        restored_lock = dict(archived_lock)
        restored_lock["status"] = "rolled_back"
        restored_lock["effective_digest"] = _inventory_digest(archived_entries)
        project_config["quality_pack"] = {
            "name": archived_lock.get("name"),
            "version": archived_lock.get("version"),
            "digest": digest,
            "effective_digest": restored_lock["effective_digest"],
        }
    report = {
        "schema": QUALITY_SYNC_SCHEMA,
        "project_id": _load_json(_inside(project, "testence.json")).get("project_id", project.name),
        "pack": {
            "name": archived_lock.get("name"),
            "version": archived_lock.get("version"),
            "digest": digest,
        },
        "status": status,
        "changed": sorted(restored),
        "unchanged": [],
        "overrides": [],
        "conflicts": conflicts,
    }
    if conflicts:
        _write_json(project, ".testence/quality-sync.json", report)
    else:
        assert restored_lock is not None
        operations = [
            *((relative, snapshots[relative]) for relative in restored),
            *((relative, None) for relative in delete_after_restore),
            (".testence/quality-pack.lock.json", _json_bytes(restored_lock)),
            ("testence.json", _json_bytes(project_config)),
            (".testence/quality-sync.json", _json_bytes(report)),
        ]
        _commit_transaction(project, operations)
    return report


def quality_summary(
    run_dirs: list[Path | str],
    *,
    project: str | None = None,
    owner: str | None = None,
    risk: str | None = None,
    case: str | None = None,
) -> dict[str, Any]:
    projects: dict[str, dict[str, Any]] = {}
    actionable: list[dict[str, Any]] = []
    for run_dir in run_dirs:
        run_path = Path(run_dir)
        run = LoadedRun.from_events(load_run(run_path), run_path)
        if project and run.project_id != project:
            continue
        rollup = projects.setdefault(
            run.project_id,
            {"runs": 0, "tests": 0, "passed": 0, "verified": 0, "integrity_errors": 0},
        )
        rollup["runs"] += 1
        rollup["tests"] += len(run.tests)
        rollup["passed"] += run.passed
        rollup["verified"] += sum(test.assurance == "verified" for test in run.tests)
        rollup["integrity_errors"] += len(run.integrity_errors)
        for issue in run.integrity_errors:
            actionable.append(
                {
                    "kind": "integrity",
                    "project_id": run.project_id,
                    "run_id": run.run_id,
                    "case_id": "",
                    "owner": "",
                    "risk": "",
                    "reason": str(issue.get("error") or issue.get("code") or "integrity error"),
                }
            )
        for test in run.tests:
            if owner and test.owner != owner:
                continue
            if risk and test.risk != risk:
                continue
            if case and test.case_id != case:
                continue
            kind = ""
            reason = ""
            if test.status != "passed":
                kind = "missing_execution" if test.status in {"not_run", "skipped"} else "violation"
                reason = test.error or f"execution={test.status}"
            elif test.assurance != "verified":
                kind = "missing_proof"
                reason = "; ".join(test.assurance_reasons) or f"assurance={test.assurance}"
            if kind:
                actionable.append(
                    {
                        "kind": kind,
                        "project_id": run.project_id,
                        "run_id": run.run_id,
                        "case_id": test.case_id,
                        "owner": test.owner,
                        "risk": test.risk,
                        "reason": reason[:500],
                    }
                )
    actionable.sort(key=lambda item: (item["project_id"], item["case_id"], item["kind"]))
    return {
        "schema": QUALITY_SUMMARY_SCHEMA,
        "projects": projects,
        "actionable": actionable,
        "filters": {"project": project, "owner": owner, "risk": risk, "case": case},
    }
