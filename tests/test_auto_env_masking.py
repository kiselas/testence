"""Secret-looking environment variables are masked without being listed (stage 6, T06).

Before, only ``evidence.redact.env`` named a variable whose value was replaced, so an
``API_TOKEN`` nobody listed reached the ledger, the pack and every export.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from testence.application import doctor, init_project
from testence.config import Settings, is_maskable_env_value, is_secret_env_name
from testence.evidence import RUN_ID_ENV
from testence.export import export_run
from testence.mcp import McpServer
from testence.report import render_report
from tests.owned_pytest import run_pytest

ROOT = Path(__file__).parents[1]
CANARY = "synth-canary-4f9c1e7a2b"


@pytest.mark.parametrize(
    "name",
    [
        "API_TOKEN",
        "SYNTH_API_TOKEN",
        "github_token",
        "DB_PASSWORD",
        "LEGACY_PASSWD",
        "AWS_SECRET_ACCESS_KEY",
        "STRIPE_API_KEY",
        "SIGNING_PRIVATE_KEY",
        "GOOGLE_CREDENTIALS",
    ],
)
def test_names_that_look_like_secrets_match(name):
    assert is_secret_env_name(name)


@pytest.mark.parametrize("name", ["PATH", "HOME", "SORT_KEY", "KEYBOARD_LAYOUT", "PASSAGE"])
def test_ordinary_names_do_not_match(name):
    assert not is_secret_env_name(name)


@pytest.mark.parametrize(
    "value",
    ["", "short", "1234567", "true", "FALSE", "  yes   ", "12345678901", "3.14159265", "null"],
)
def test_short_boolean_and_numeric_values_are_not_masked(value):
    assert not is_maskable_env_value(value)


@pytest.mark.parametrize("value", [CANARY, "correct-horse-battery", "12345678-abcd"])
def test_other_values_are_masked(value):
    assert is_maskable_env_value(value)


@pytest.fixture
def clean_env(monkeypatch):
    """Only the variables a test sets: the host's own tokens must not enter asserts."""
    for name in list(os.environ):
        if is_secret_env_name(name):
            monkeypatch.delenv(name)


def test_an_unlisted_secret_variable_is_masked(clean_env, monkeypatch):
    monkeypatch.setenv("SYNTH_API_TOKEN", CANARY)
    monkeypatch.setenv("PASSWORD_MAX_AGE", "31536000")
    monkeypatch.setenv("TOKENIZERS_PARALLELISM", "false")
    monkeypatch.setenv("SYNTH_PASSWORD", "short")
    settings = Settings()
    assert CANARY in settings.redaction_values()
    assert settings.auto_masked_env() == ("SYNTH_API_TOKEN",)
    assert "31536000" not in settings.redaction_values()


def test_values_from_env_files_are_masked_too(clean_env, tmp_path):
    (tmp_path / ".env.local").write_text(f"SHOP_SECRET={CANARY}\nSHOP_REGION=eu-west-long\n")
    settings = Settings.load(tmp_path)
    assert CANARY in settings.redaction_values()
    assert settings.auto_masked_env() == ("SHOP_SECRET",)


def test_switching_it_off_is_explicit_and_leaves_declared_names_alone(clean_env, monkeypatch):
    monkeypatch.setenv("SYNTH_API_TOKEN", CANARY)
    monkeypatch.setenv("SYNTH_DECLARED", "tiny")
    redact = {"auto_env": False, "env": ["SYNTH_DECLARED"]}
    settings = Settings(extra={"evidence": {"redact": redact}})
    assert settings.redaction_values() == ("tiny",)
    assert settings.auto_masked_env() == ()


def test_the_rule_only_adds_to_what_a_project_declared(clean_env, monkeypatch):
    """A declared variable keeps its value in the mask whatever it looks like."""
    monkeypatch.setenv("SYNTH_API_TOKEN", CANARY)
    monkeypatch.setenv("SYNTH_PIN", "1234")
    monkeypatch.setenv("TESTENCE_PASSWORD", "pw")
    settings = Settings(extra={"evidence": {"redact": {"env": ["SYNTH_PIN"]}}})
    values = settings.redaction_values()
    assert {CANARY, "1234", "pw"} <= set(values)
    assert len(values) == len(set(values))


def test_auto_env_must_be_a_boolean(clean_env):
    settings = Settings(extra={"evidence": {"redact": {"auto_env": "no"}}})
    with pytest.raises(ValueError, match="auto_env must be true or false"):
        settings.redaction_values()


def test_the_policy_written_to_the_ledger_carries_no_values(clean_env, monkeypatch):
    monkeypatch.setenv("SYNTH_API_TOKEN", CANARY)
    policy = Settings().redaction_policy()
    assert CANARY not in json.dumps(policy.to_json())


def test_doctor_lists_the_masked_names_and_never_the_values(clean_env, monkeypatch, tmp_path):
    monkeypatch.setenv("SYNTH_API_TOKEN", CANARY)
    project = tmp_path / "doctor"
    init_project(project)
    checks = {item["name"]: item for item in doctor(project)["checks"]}
    assert "SYNTH_API_TOKEN" in checks["settings"]["detail"]
    assert CANARY not in json.dumps(checks)


def run_project(
    project: Path, files: dict[str, str], settings: dict[str, Any], env_extra: dict[str, str]
) -> Path:
    """Run a nested pytest session in ``project``; returns the one run directory."""
    project.mkdir()
    (project / "testence.json").write_text(json.dumps(settings), encoding="utf-8")
    for name, text in files.items():
        (project / name).write_text(text, encoding="utf-8")
    env = os.environ.copy()
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env.update(env_extra)
    env.pop(RUN_ID_ENV, None)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "src"), value] if (value := env.get("PYTHONPATH")) else [str(ROOT / "src")]
    )
    result = run_pytest(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "testence.pytest_plugin",
            "--rootdir",
            str(project),
            "--testence-runs-root",
            str(project / "runs"),
            "-p",
            "no:cacheprovider",
            "-q",
        ],
        cwd=project,
        env=env,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    (run_dir,) = [path for path in (project / "runs").iterdir() if path.is_dir()]
    return run_dir


def tree_text(root: Path) -> str:
    return "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in root.rglob("*")
        if path.is_file()
    )


def inspect_via_mcp(project: Path, run_dir: Path) -> str:
    reply = McpServer(project).handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "testence_inspect",
                "arguments": {"run_dir": run_dir.relative_to(project).as_posix()},
            },
        }
    )
    return json.dumps(reply)


_LEAKY_TEST = """
import os


def test_leaks_the_token(testence_writer, request):
    token = os.environ["SYNTH_API_TOKEN"]
    nodeid = request.node.nodeid
    testence_writer.emit("note", test=nodeid, text=f"saw {token} in a log")
    testence_writer.attach(nodeid, "log.txt", f"header\\nvalue={token}\\n")
    assert False, f"the page printed {token}"
"""


def test_a_canary_in_an_unlisted_token_variable_reaches_no_artifact(tmp_path):
    project = tmp_path / "project"
    run_dir = run_project(project, {"test_leak.py": _LEAKY_TEST}, {}, {"SYNTH_API_TOKEN": CANARY})
    assert "<redacted>" in (run_dir / "run.jsonl").read_text(encoding="utf-8")
    export_run(run_dir, "allure", tmp_path / "allure")
    export_run(run_dir, "ctrf", tmp_path / "ctrf")
    export_run(run_dir, "junit", tmp_path / "junit")
    render_report(run_dir, tmp_path / "report.html")
    assert CANARY not in inspect_via_mcp(project, run_dir)
    assert CANARY not in tree_text(tmp_path)


def test_with_auto_env_off_the_same_run_keeps_the_variable_visible(tmp_path):
    """The switch is real: it is the only way back to the old behaviour."""
    settings = {"evidence": {"redact": {"auto_env": False}}}
    run_dir = run_project(
        tmp_path / "project", {"test_leak.py": _LEAKY_TEST}, settings, {"SYNTH_API_TOKEN": CANARY}
    )
    assert CANARY in (run_dir / "run.jsonl").read_text(encoding="utf-8")
