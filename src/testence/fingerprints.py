"""Memory of the last green run: what each step's element looked like when it worked.

This is the minimum state a heal proposal needs. Healenium keeps the equivalent in
PostgreSQL; a JSON file next to the tests is enough for us and has a property a
database does not: it is reviewable and diffable in the project's own repo, so a
proposed heal can be read as "this is what the element used to be".

Keyed by ``(test id, step intent)`` — intent, not locator, on purpose: the locator is
the thing that drifts, the intent is what stays true (the practice the whole DSL is
built around).

Under xdist each worker holds its own half of the keyspace (a test runs on exactly
one worker), so a shared file would be last-writer-wins and N-1 workers' memory
would vanish silently. A worker therefore writes ``fingerprints.<worker>.json``
beside the base file; every store *reads* the base plus all worker shards, and a
single-process run absorbs the shards back into the base file and deletes them, so
the repo keeps one reviewable artifact.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from testence.evidence import WORKER_ENV

DEFAULT_STORE = Path(".testence") / "fingerprints.json"


class FingerprintStore:
    def __init__(self, path: Path | str = DEFAULT_STORE, worker: str | None = None) -> None:
        self.path = Path(path)
        self.worker = worker if worker is not None else os.environ.get(WORKER_ENV, "")
        self.write_path = (
            self.path.with_name(f"{self.path.stem}.{self.worker}{self.path.suffix}")
            if self.worker
            else self.path
        )
        self._data: dict[str, Any] = {}
        for source in self._shards():
            self._data.update(_read_json(source))
        self._dirty = False

    def _shards(self) -> list[Path]:
        """Base file first, then worker shards — later keys win, and they never
        collide because a test lives on one worker."""
        others = sorted(self.path.parent.glob(f"{self.path.stem}.*{self.path.suffix}"))
        return ([self.path] if self.path.exists() else []) + others

    @staticmethod
    def key(test_id: str, intent: str) -> str:
        return f"{test_id}::{intent}"

    def get(self, test_id: str, intent: str) -> dict[str, Any] | None:
        entry = self._data.get(self.key(test_id, intent))
        return entry.get("fingerprint") if entry else None

    def record(self, test_id: str, intent: str, target: str, fingerprint: dict[str, Any]) -> None:
        if not fingerprint:
            return
        self._data[self.key(test_id, intent)] = {
            "target": target,
            "fingerprint": fingerprint,
        }
        self._dirty = True

    def flush(self) -> None:
        if not self._dirty:
            return
        self.write_path.parent.mkdir(parents=True, exist_ok=True)
        self.write_path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=1, sort_keys=True),
            encoding="utf-8",
            newline="\n",
        )
        if not self.worker:
            # A serial run has read every shard already, so its own write is the
            # union: fold the shards away rather than leaving them to rot.
            for shard in self.path.parent.glob(f"{self.path.stem}.*{self.path.suffix}"):
                shard.unlink(missing_ok=True)
        self._dirty = False


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}  # a corrupt cache must never fail a run
