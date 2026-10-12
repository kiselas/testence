"""Frictions a first-time user hit with 0.1.0a2 (new-user re-audit, 2026-10-12)."""

from __future__ import annotations

from pathlib import Path

import pytest

from testence.agent.install import AgentInstallError, verify_skills
from testence.application import _target_checks
from testence.cli import main
from testence.config import Settings
from testence.discovery import explore
from testence.metrics import load_run


@pytest.mark.parametrize(
    ("url", "hint"),
    [
        ("C:/Program Files/Git/", "MSYS_NO_PATHCONV"),
        ("file:///C:/Users", ""),
        ("login", ""),
    ],
)
def test_explore_refuses_what_is_not_a_page_of_the_app(tmp_path, url, hint):
    """Git Bash turned `explore /` into the Git install folder, and explore mapped the
    local disk as a file:// page and exited 0."""
    (tmp_path / "testence.json").write_text('{"base_url": "http://127.0.0.1:9"}')
    with pytest.raises(ValueError, match="path on base_url") as caught:
        explore(tmp_path, url)
    assert hint in str(caught.value)


def test_verify_before_install_says_to_install(tmp_path):
    """Twenty "missing" drift entries and exit 3 read as breakage."""
    with pytest.raises(AgentInstallError, match="testence agent install"):
        verify_skills(tmp_path, ["claude"])


def test_agent_install_prints_a_summary_not_a_receipt(tmp_path, capsys):
    assert main(["agent", "install", "--project", str(tmp_path), "--client", "claude"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("installed: skill pack") and "{" not in out
    assert main(["agent", "verify", "--project", str(tmp_path)]) == 0
    assert "claude: valid" in capsys.readouterr().out


def test_inspect_of_a_bare_run_id_points_at_the_run_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "runs" / "r-1").mkdir(parents=True)
    with pytest.raises(FileNotFoundError, match=r"did you mean runs[\\/]r-1"):
        load_run(Path("r-1"))


def test_doctor_target_names_a_base_url_without_a_scheme():
    checks = _target_checks(Settings(base_url="localhost:3000", auth="none"), lambda _: None)
    (target,) = [check for check in checks if check["name"] == "target"]
    assert not target["ok"] and "must start with http://" in target["detail"]


def test_a_failed_run_points_at_its_evidence(tmp_path, capsys, monkeypatch):
    project = tmp_path / "p"
    project.mkdir()
    (project / "testence.json").write_text("{}", encoding="utf-8")
    (project / "test_fails.py").write_text("def test_fails():\n    assert False\n")
    monkeypatch.chdir(project)
    code = main(["run", "--project", str(project), "--run-id", "r-fail", "--", "test_fails.py"])
    assert code == 1
    assert f"testence inspect {Path('runs') / 'r-fail'}" in capsys.readouterr().out
