"""Playwright trace and video, kept for the failures that need them (L12 item 6).

``evidence.trace`` and ``evidence.video`` are ``off`` by default: both record the page
raw — DOM snapshots, network and pixels — so a run opts in, the ledger marks each file
``redaction: none``, and only a full export ships them.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from testence.config import Settings
from testence.engine.playwright_cdp import PlaywrightCdpEngine
from testence.evidence import RUN_ID_ENV
from testence.export import export_run

ROOT = Path(__file__).parents[1]

SUITE = """
from testence.engine import Target

PAGE = "data:text/html,<h1>Pending</h1>"


def test_passes(ex):
    ex.goto(PAGE)
    ex.expect_text(Target("css", "h1"), "Pending")


def test_fails(ex):
    ex.goto(PAGE)
    ex.expect_text(Target("css", "h1"), "Paid", intent="the order shows as paid")
"""


def _run(tmp_path: Path, evidence: dict) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    (project / "test_recorded.py").write_text(SUITE, encoding="utf-8")
    (project / "testence.json").write_text(
        json.dumps({"timeout_ms": 1500, "extra": {"evidence": evidence}}), encoding="utf-8"
    )
    env = {
        k: v for k, v in os.environ.items() if k != RUN_ID_ENV and not k.startswith("PYTEST_XDIST")
    }
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["PYTHONPATH"] = str(ROOT / "src")
    runs = tmp_path / "runs"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "testence.pytest_plugin",
            "-q",
            "-p",
            "no:cacheprovider",
            "--testence-headless",
            "--rootdir",
            str(project),
            "--testence-runs-root",
            str(runs),
        ],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    return next(runs.iterdir())


def _recordings(run_dir: Path) -> dict[str, list[dict]]:
    ends = {}
    for line in (run_dir / "run.jsonl").read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event["kind"] == "test.end":
            ends[event["test"].rsplit("::", 1)[-1]] = event.get("recordings", [])
    return ends


def test_retain_on_failure_keeps_the_failed_tests_trace_and_video_only(tmp_path):
    run_dir = _run(tmp_path, {"trace": "retain-on-failure", "video": "retain-on-failure"})
    recordings = _recordings(run_dir)
    assert recordings["test_passes"] == []
    kinds = {entry["kind"]: entry for entry in recordings["test_fails"]}
    assert set(kinds) == {"trace", "video"}
    assert all(entry["redaction"] == "none" for entry in kinds.values())
    trace = run_dir / kinds["trace"]["path"]
    # A Playwright trace archive the viewer opens: trace events plus snapshots.
    assert any(name.endswith(".trace") for name in zipfile.ZipFile(trace).namelist())
    assert (run_dir / kinds["video"]["path"]).stat().st_size > 0
    # Nothing was left behind for the passing test.
    passing_dirs = [path for path in run_dir.rglob("*") if "test_passes" in str(path)]
    assert not any(path.name in ("trace.zip", "video-1.webm") for path in passing_dirs)


def test_on_keeps_a_trace_for_a_passing_test_too(tmp_path):
    run_dir = _run(tmp_path, {"trace": "on"})
    recordings = _recordings(run_dir)
    assert [entry["kind"] for entry in recordings["test_passes"]] == ["trace"]


def test_only_a_full_export_ships_the_recordings(tmp_path):
    run_dir = _run(tmp_path, {"trace": "retain-on-failure"})
    full = export_run(run_dir, "allure", tmp_path / "full")
    minimal = export_run(run_dir, "allure", tmp_path / "minimal", attachments="minimal")
    assert any(path.suffix == ".zip" for path in full)
    assert not any(path.suffix == ".zip" for path in minimal)
    for name in ("junit", "ctrf"):
        shipped = export_run(run_dir, name, tmp_path / f"{name}-full")
        kept = export_run(run_dir, name, tmp_path / f"{name}-min", attachments="minimal")
        assert any(path.name == "trace.zip" for path in shipped), name
        assert not any(path.name == "trace.zip" for path in kept), name


def test_recording_settings_are_checked(tmp_path):
    (tmp_path / "testence.json").write_text(
        '{"extra": {"evidence": {"trace": "always"}}}', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="evidence.trace"):
        Settings.load(tmp_path).evidence_config()
    with pytest.raises(ValueError, match="trace and video"):
        PlaywrightCdpEngine(trace="sometimes")
    with pytest.raises(ValueError, match="attached browser"):
        PlaywrightCdpEngine(cdp_url="http://127.0.0.1:9222", video="retain-on-failure")
