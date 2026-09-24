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

import hashlib
import json
import os
import secrets
import threading
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TextIO

from testence.contracts.versions import RUN_MANIFEST_SCHEMA
from testence.identity import UNKNOWN_PROJECT_ID, proof_id, source_case_id

from .events import Event
from .sanitize import DEFAULT_POLICY, RedactionPolicy, sanitize, sanitize_text

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
    run_root = run_dir.resolve()

    def contained_file(path: Path) -> Path | None:
        try:
            resolved = path.resolve()
            resolved.relative_to(run_root)
        except (OSError, RuntimeError, ValueError):
            return None
        return resolved if resolved.is_file() else None

    main = contained_file(run_dir / "run.jsonl")
    workers = [
        resolved
        for path in sorted(run_dir.glob("run-*.jsonl"))
        if (resolved := contained_file(path)) is not None
    ]
    return ([main] if main is not None else []) + workers


class EvidenceWriter:
    """One writer per process; safe to call from callbacks on other threads."""

    def __init__(
        self,
        runs_root: Path | str,
        run_id: str | None = None,
        worker: str | None = None,
        project_id: str = UNKNOWN_PROJECT_ID,
        redact_values: tuple[str, ...] | list[str] = (),
        redaction_policy: RedactionPolicy = DEFAULT_POLICY,
    ) -> None:
        self.run_id = run_id or os.environ.get(RUN_ID_ENV) or new_run_id()
        self.worker = worker if worker is not None else os.environ.get(WORKER_ENV, "")
        self.project_id = project_id
        self.run_dir = Path(runs_root) / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        name = f"run-{self.worker}.jsonl" if self.worker else "run.jsonl"
        self.path = self.run_dir / name
        self._fh: TextIO = open(self.path, "a", encoding="utf-8", newline="\n")
        self._lock = threading.Lock()
        self._seq = 0
        self._redact_values = tuple(value for value in redact_values if value)
        self._policy = redaction_policy
        self._listeners: list[Callable[[dict[str, Any]], None]] = []
        self._test_context: dict[str, dict[str, Any]] = {}
        self._failed_oracle_diffs: dict[str, list[dict[str, Any]]] = {}

    def bind_test(
        self,
        test_id: str,
        *,
        identity: Mapping[str, Any] | None = None,
        plan: Mapping[str, Any] | None = None,
        claims: list[str] | tuple[str, ...] = (),
        assertions: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] = (),
        plan_digest: str | None = None,
        test_digest: str | None = None,
        policy_digest: str | None = None,
    ) -> None:
        """Attach the semantic contract to every event emitted for one test.

        The binding is intentionally writer-side: DSL steps, network callbacks and
        oracle helpers should not each need to remember traceability fields.
        """
        with self._lock:
            self._test_context[test_id] = {
                **dict(identity or {}),
                **({"plan": dict(plan)} if plan else {}),
                "claims": list(claims),
                "assertions": [dict(assertion) for assertion in assertions],
                **({"plan_digest": plan_digest} if plan_digest else {}),
                **({"test_digest": test_digest} if test_digest else {}),
                **({"policy_digest": policy_digest} if policy_digest else {}),
            }

    def context_for(self, test_id: str) -> dict[str, Any]:
        with self._lock:
            context = self._test_context.get(test_id) or {}
            result = dict(context)
            if isinstance(result.get("plan"), dict):
                result["plan"] = dict(result["plan"])
            if isinstance(result.get("claims"), list):
                result["claims"] = list(result["claims"])
            if isinstance(result.get("assertions"), list):
                result["assertions"] = [dict(item) for item in result["assertions"]]
            return result

    def last_oracle_diff(self, test_id: str) -> list[dict[str, Any]] | None:
        with self._lock:
            diffs = self._failed_oracle_diffs.get(test_id)
            return [dict(row) for row in diffs] if diffs else None

    def unbind_test(self, test_id: str) -> None:
        with self._lock:
            self._test_context.pop(test_id, None)
            self._failed_oracle_diffs.pop(test_id, None)

    def add_listener(self, listener: Callable[[dict[str, Any]], None]) -> None:
        """Receive every event document after it is written (redacted, as persisted)."""
        self._listeners.append(listener)

    def emit(self, kind: str, test: str | None = None, **payload: Any) -> Event:
        event = self._emit(kind, test, **payload)
        if self._listeners:
            document = json.loads(event.to_json())
            for listener in list(self._listeners):
                try:
                    listener(document)
                except Exception as exc:  # noqa: BLE001 - a sink never changes the run
                    if kind != "note":
                        self._emit(
                            "note",
                            text="evidence listener failed",
                            error=f"{type(exc).__name__}: {exc}",
                        )
        return event

    def _emit(self, kind: str, test: str | None = None, **payload: Any) -> Event:
        with self._lock:
            merged: dict[str, Any] = {}
            if test is not None:
                merged.update(self._test_context.get(test) or {})
                if not merged.get("case_id"):
                    case_id = source_case_id(test)
                    attempt_id = "attempt-direct-1"
                    merged.update(
                        {
                            "project_id": self.project_id,
                            "case_id": case_id,
                            "variant_id": "default",
                            "attempt_id": attempt_id,
                            "run_id": self.run_id,
                            "proof_id": proof_id(self.run_id, case_id, "default", attempt_id),
                            "parameters": {},
                        }
                    )
            merged.update(payload)
            merged = sanitize(merged, secrets=self._redact_values, policy=self._policy)
            safe_test = (
                sanitize_text(test, secrets=self._redact_values, policy=self._policy, limit=500)
                if test is not None
                else None
            )
            event = Event(
                kind=kind,
                run=self.run_id,
                project_id=self.project_id,
                worker=self.worker or "controller",
                test=safe_test,
                payload=merged,
            )
            self._seq += 1
            event.stamp(self._seq)
            self._fh.write(event.to_json() + "\n")
            self._fh.flush()
            os.fsync(self._fh.fileno())
            if not self.worker and kind in {"run.start", "collection.end", "run.end"}:
                self._write_run_manifest(kind, event, merged)
            if (
                kind in {"oracle", "assertion"}
                and test is not None
                and (merged.get("ok") is False or merged.get("outcome") == "failed")
            ):
                diffs = merged.get("diff")
                if isinstance(diffs, list):
                    self._failed_oracle_diffs[test] = [
                        dict(row) for row in diffs if isinstance(row, dict)
                    ]
        return event

    def _write_run_manifest(self, kind: str, event: Event, payload: dict[str, Any]) -> None:
        """Atomically checkpoint controller-owned run identity and shard digests."""

        target = self.run_dir / "manifest.json"
        previous: dict[str, Any] = {}
        if target.is_file():
            try:
                loaded = json.loads(target.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    previous = loaded
            except (OSError, json.JSONDecodeError):
                previous = {}

        ledgers = []
        for path in ledger_paths(self.run_dir):
            content = path.read_bytes()
            ledgers.append(
                {
                    "path": path.name,
                    "bytes": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            )
        document: dict[str, Any] = {
            "schema": RUN_MANIFEST_SCHEMA,
            "project_id": self.project_id,
            "run_id": self.run_id,
            "status": "complete" if kind == "run.end" else "running",
            "ledgers": ledgers,
        }
        if previous.get("selected") is not None:
            document["selected"] = previous["selected"]
        if kind == "collection.end":
            document["selected"] = payload.get("cases") or []
            document["selected_count"] = int(payload.get("selected") or 0)
        elif previous.get("selected_count") is not None:
            document["selected_count"] = previous["selected_count"]
        if kind == "run.end":
            document["run_status"] = payload.get("run_status") or "unknown"
            document["exit_code"] = payload.get("exit_code")
            document["completed_at"] = event.ts

        document = sanitize(document, secrets=self._redact_values, policy=self._policy)
        temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        with open(temporary, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(document, ensure_ascii=False, indent=1) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)

    def sanitized(self, value: Any, *, limit: int = 16_384) -> Any:
        """Sanitize a pack value with the same policy as the ledger."""
        return sanitize(value, secrets=self._redact_values, policy=self._policy, limit=limit)

    @property
    def redact_values(self) -> tuple[str, ...]:
        return self._redact_values

    @property
    def redaction_policy(self) -> RedactionPolicy:
        return self._policy

    def test_dir(self, test_id: str) -> Path:
        """Per-test directory for large artifacts (screenshots, bodies, packs)."""
        redacted_id = sanitize_text(
            test_id, secrets=self._redact_values, policy=self._policy, limit=80
        )
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in redacted_id)[:80]
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
