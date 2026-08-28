"""Append-only run.jsonl writer.

Crash-safety over cleverness: every event is flushed on write, so a hung browser or
killed process still leaves a readable ledger up to the last completed action —
the evidence must survive exactly the situations it exists for. Measured cost of
that guarantee: 0.5 ms per event, 0.09 s across a nine-case run.

**One file per process, never per run.** The lock here is a ``threading.Lock``,
which means nothing between processes: four workers appending to one ``run.jsonl``
lost 27 % of events and produced torn lines. So a worker writes
``run-<worker>.jsonl`` beside the controller's ``run.jsonl`` and the readers
(``metrics``, ``report``) merge every ``run*.jsonl`` in the directory. All workers
share one run directory, named by ``TESTENCE_RUN_ID`` — set once by the pytest
plugin before xdist spawns anyone, and inherited from there.
"""

from __future__ import annotations

import os
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

from .events import Event


#: Environment variable carrying the run id to every xdist worker, so all of them
#: write into one run directory instead of inventing a directory each.
RUN_ID_ENV = "TESTENCE_RUN_ID"
#: Set by pytest-xdist in each worker process; empty in a single-process run.
WORKER_ENV = "PYTEST_XDIST_WORKER"


def new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"r-{stamp}-{secrets.token_hex(3)}"


def ledger_paths(run_dir: Path | str) -> list[Path]:
    """Every ledger file of a run, controller first then workers in name order.

    A reader must go through this rather than opening ``run.jsonl``: under xdist
    the controller's file holds only run.start/run.end and all the test events
    live in the per-worker files.
    """
    run_dir = Path(run_dir)
    main = run_dir / "run.jsonl"
    workers = sorted(p for p in run_dir.glob("run-*.jsonl"))
    return ([main] if main.exists() else []) + workers


class EvidenceWriter:
    """One writer per process; safe to call from callbacks on other threads."""

    def __init__(self, runs_root: Path | str, run_id: str | None = None,
                 worker: str | None = None) -> None:
        self.run_id = run_id or os.environ.get(RUN_ID_ENV) or new_run_id()
        self.worker = worker if worker is not None else os.environ.get(WORKER_ENV, "")
        self.run_dir = Path(runs_root) / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        name = f"run-{self.worker}.jsonl" if self.worker else "run.jsonl"
        self.path = self.run_dir / name
        self._fh: TextIO = open(self.path, "a", encoding="utf-8", newline="\n")
        self._lock = threading.Lock()
        self._seq = 0

    def emit(self, kind: str, test: str | None = None, **payload: Any) -> Event:
        event = Event(kind=kind, run=self.run_id, test=test, payload=payload)
        with self._lock:
            self._seq += 1
            event.stamp(self._seq)
            self._fh.write(event.to_json() + "\n")
            self._fh.flush()
            os.fsync(self._fh.fileno())
        return event

    def test_dir(self, test_id: str) -> Path:
        """Per-test directory for large artifacts (screenshots, bodies, packs)."""
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in test_id)[:80]
        d = self.run_dir / safe
        d.mkdir(parents=True, exist_ok=True)
        return d

    def close(self) -> None:
        with self._lock:
            if not self._fh.closed:
                self._fh.close()

    def __enter__(self) -> "EvidenceWriter":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
