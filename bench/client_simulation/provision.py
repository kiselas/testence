"""Explicit baseline-authoring phase, never called by accepted replay."""

import json
import time
from contextlib import contextmanager
from pathlib import Path

from testence.config import Settings
from testence.engine import Target, create_engine
from testence.visual import capture_baseline

SNAPSHOT = """() => ({readyState: document.readyState, fonts: document.fonts.status,
    width: innerWidth, height: innerHeight,
    resources: performance.getEntriesByType('resource').length,
    incompleteResources: performance.getEntriesByType('resource').filter(x => !x.responseEnd).length})"""


class DiagnosticEngine:
    """Authoring-only call observations; no retries, options or replay changes."""

    def __init__(self, engine):
        self.engine = engine
        self.state = None
        self.capture = 0
        self.records = 0
        self.started = time.perf_counter()

    def __getattr__(self, name):
        return getattr(self.engine, name)

    def emit(self, stage, outcome, **fields):
        if self.records >= 64:
            return
        self.records += 1
        row = {
            "schema": "testence/provision-diagnostic/1",
            "state": self.state,
            "stage": stage,
            "outcome": outcome,
            "since_start_ms": round((time.perf_counter() - self.started) * 1000, 3),
            **fields,
        }
        try:
            print("PROVISION " + json.dumps(row, allow_nan=False), flush=True)
        except (OSError, UnicodeError):
            # A closed diagnostic sink must not replace the engine's exception.
            pass

    @contextmanager
    def phase(self, stage, **fields):
        started = time.perf_counter()
        self.emit(stage, "started", **fields)
        try:
            yield
        except BaseException as exc:
            self.emit(
                stage,
                "error",
                error_type=type(exc).__name__,
                elapsed_ms=round((time.perf_counter() - started) * 1000, 3),
                **fields,
            )
            raise
        else:
            self.emit(
                stage,
                "returned",
                elapsed_ms=round((time.perf_counter() - started) * 1000, 3),
                **fields,
            )

    def observe(self):
        # One extra read-only observation, not a readiness gate or polling loop.
        try:
            value = self.engine.eval_js(SNAPSHOT)
            safe = {}
            if isinstance(value, dict):
                for key, allowed in (
                    ("readyState", {"loading", "interactive", "complete"}),
                    ("fonts", {"loading", "loaded"}),
                ):
                    if type(value.get(key)) is str and value[key] in allowed:
                        safe[key] = value[key]
                for key in ("width", "height", "resources", "incompleteResources"):
                    if type(value.get(key)) is int and 0 <= value[key] <= 10_000_000:
                        safe[key] = value[key]
            self.emit("snapshot", "observed" if len(safe) == 6 else "incomplete", values=safe)
        except Exception as exc:
            self.emit("snapshot", "unavailable", error_type=type(exc).__name__)

    def screenshot(self, path):
        self.capture += 1
        with self.phase("screenshot", capture=self.capture):
            self.engine.screenshot(path)


def main():
    root = Path.cwd()
    engine = DiagnosticEngine(create_engine(Settings.load(root)))
    try:
        with engine.phase("start"):
            engine.start()
        bindings = {}
        for state in ("overview", "dialog"):
            engine.state = state
            engine.capture = 0
            with engine.phase("navigate"):
                engine.goto("/")
            if state == "dialog":
                with engine.phase("open-dialog"):
                    engine.click(Target("role", "button", name="Invite teammate"))
            with engine.phase("visible"):
                engine.expect_visible(
                    Target(
                        "role",
                        "heading",
                        name="Invite teammate" if state == "dialog" else "Workspace overview",
                    )
                )
            engine.observe()
            with engine.phase("baseline"):
                bindings[state] = capture_baseline(
                    engine,
                    root / "baselines" / state,
                    provenance="Synthetic Northstar healthy fixture; automatic candidate capture, agent review recorded separately in audit",
                )
        (root / "baselines.json").write_text(
            json.dumps(bindings, indent=2) + "\n", encoding="utf-8"
        )
    finally:
        with engine.phase("stop"):
            engine.stop()


if __name__ == "__main__":
    main()
