from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _corpus_runner():
    path = Path(__file__).parents[1] / "bench" / "corpus" / "run.py"
    spec = importlib.util.spec_from_file_location("testence_corpus_runner", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_healthy_control_requires_a_complete_successful_run():
    runner = _corpus_runner()
    healthy = next(item for item in runner.ITEMS if not item.expect_failure)

    checks = runner.evaluate(
        healthy,
        {
            "failed_claims": [],
            "heal_proposals": [],
            "claims_seen": len(runner.CLAIMS),
            "complete": True,
            "incomplete_reasons": [],
        },
    )

    assert checks["outcome_ok"] is True
    assert checks["observed"] == "green"


def test_empty_or_crashed_control_is_incomplete_instead_of_green():
    runner = _corpus_runner()
    healthy = next(item for item in runner.ITEMS if not item.expect_failure)

    checks = runner.evaluate(
        healthy,
        {
            "failed_claims": [],
            "heal_proposals": [],
            "claims_seen": 0,
            "complete": False,
            "incomplete_reasons": ["pytest exit code 2", "missing tests"],
        },
    )

    assert checks["outcome_ok"] is False
    assert checks["observed"] == "incomplete"
    assert checks["incomplete_reasons"]


@pytest.mark.parametrize("complete,exit_code", [(True, 0), (False, 1)])
def test_corpus_cli_exit_reflects_proof_completeness(tmp_path, monkeypatch, complete, exit_code):
    runner = _corpus_runner()
    healthy = next(item for item in runner.ITEMS if not item.expect_failure)
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "RESULTS", tmp_path / "results")
    monkeypatch.setattr(runner.sys, "argv", ["run.py", "--only", healthy.id])
    monkeypatch.setattr(runner, "start_target", lambda port: None)
    monkeypatch.setattr(
        runner,
        "run_item",
        lambda *args: {
            "failed_claims": [],
            "heal_proposals": [],
            "claims_seen": len(runner.CLAIMS),
            "complete": complete,
            "incomplete_reasons": [] if complete else ["missing tests"],
            "run": "synthetic",
            "stdout_tail": "",
        },
    )
    assert runner.main() == exit_code
