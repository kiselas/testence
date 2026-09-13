"""Accepted client replay: deliberately unaware of harness mutations/expected labels."""

import json
from pathlib import Path

import pytest

from testence.engine import Target

ROOT = Path(__file__).parent


@pytest.mark.parametrize("state", ["overview", "dialog"])
@pytest.mark.testence(
    plan=str(ROOT / "plan.md"), case_id="workspace-view", claims=["workspace.visual"]
)
def test_viewport(ex, state):
    ex.goto("/", intent="Open the synthetic workspace")
    if state == "dialog":
        ex.click(
            Target("role", "button", name="Invite teammate"), intent="Open invitation explanation"
        )
    heading = "Invite teammate" if state == "dialog" else "Workspace overview"
    ex.expect_visible(
        Target("role", "heading", name=heading), assertion_id="a.ready", claim_id="workspace.visual"
    )
    lock = json.loads((ROOT / "baselines.json").read_text())
    ex.expect_screenshot(
        str(ROOT / "baselines" / state),
        baseline_digest=lock[state],
        assertion_id="a.visual",
        claim_id="workspace.visual",
    )
