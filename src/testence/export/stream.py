"""Allure results written while the run is still going (ADR-0026).

``testence export`` renders a finished run; a TestOps launch fed by ``allurectl watch``
wants each result the moment its test ends, and a CI job killed halfway must still
leave the results it produced. This sink listens to the evidence writer and renders
one test at a time with exactly the functions the post-run export uses, so the files
are byte-identical to ``testence export --to allure``.

Every file lands atomically (written in a staging directory beside the results
directory, then renamed), so a watcher never uploads half a document. Attachments are
written before the result that references them.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from testence.evidence.sanitize import recorded_policy, redact_events
from testence.identity import adapt_event

from . import allure
from ._model import LoadedRun

ALLURE_RESULTS_ENV = "TESTENCE_ALLURE_RESULTS"


class AllureStream:
    """An evidence-writer listener that writes Allure results per finished test."""

    def __init__(self, out_dir: Path | str, run_dir: Path | str) -> None:
        self.out_dir = Path(out_dir)
        self.run_dir = Path(run_dir)
        self._start: dict[str, Any] | None = None
        self._pending: dict[str, list[dict[str, Any]]] = {}
        self._run_events: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def __call__(self, document: dict[str, Any]) -> None:
        event = adapt_event(json.loads(json.dumps(document)))
        kind = event.get("kind")
        with self._lock:
            if kind == "run.start":
                self._start = event
                return
            if kind == "testplan.unresolved":
                self._run_events.append(event)
                return
            if kind == "run.end":
                self._finish(event)
                return
            test = event.get("test")
            if not test:
                return
            self._pending.setdefault(str(test), []).append(event)
            if kind == "test.end":
                self._flush(str(test))

    def _run(self, events: list[dict[str, Any]]) -> LoadedRun:
        base = [self._start] if self._start is not None else []
        everything = [*base, *events]
        policy = recorded_policy(everything)
        run = LoadedRun.from_events(redact_events(everything, policy), self.run_dir)
        run.redaction_policy = policy
        return run

    def _flush(self, test: str) -> None:
        run = self._run(self._pending.pop(test, []))
        for loaded in run.tests:
            allure.write_test(run, loaded, self.out_dir)

    def _finish(self, end: dict[str, Any]) -> None:
        allure.write_run_files(self._run([*self._run_events, end]), self.out_dir)
