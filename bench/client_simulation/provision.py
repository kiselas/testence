"""Explicit baseline-authoring phase, never called by accepted replay."""

import json
from pathlib import Path

from testence.config import Settings
from testence.engine import Target, create_engine
from testence.visual import capture_baseline

root = Path.cwd()
engine = create_engine(Settings.load(root))
try:
    engine.start()
    bindings = {}
    for state in ("overview", "dialog"):
        engine.goto("/")
        if state == "dialog":
            engine.click(Target("role", "button", name="Invite teammate"))
        engine.expect_visible(
            Target(
                "role",
                "heading",
                name="Invite teammate" if state == "dialog" else "Workspace overview",
            )
        )
        bindings[state] = capture_baseline(
            engine,
            root / "baselines" / state,
            provenance="Synthetic Northstar healthy fixture; automatic candidate capture, agent review recorded separately in audit",
        )
    (root / "baselines.json").write_text(json.dumps(bindings, indent=2) + "\n", encoding="utf-8")
finally:
    engine.stop()
