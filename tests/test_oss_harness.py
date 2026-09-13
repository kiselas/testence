import importlib.util
import json
import subprocess
from pathlib import Path


def test_timeout_retains_each_attempt_and_returns_failure(tmp_path, monkeypatch):
    path = Path(__file__).parents[1] / "bench/oss/run.py"
    spec = importlib.util.spec_from_file_location("oss_runner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    (tmp_path / "bench/oss").mkdir(parents=True)
    target = tmp_path / "target"
    target.mkdir()
    (target / "index.html").write_text("<h1>Synthetic</h1>")
    (target / "LICENSE").write_text("Synthetic test fixture")
    (tmp_path / "bench/oss/targets.json").write_text(
        json.dumps(
            {
                "targets": [
                    {
                        "name": "fixture",
                        "checkout": "target",
                        "web_root": ".",
                        "license": "LICENSE",
                        "revision": "a" * 40,
                    }
                ]
            }
        )
    )
    for name in ("test_panels.py", "plan.md"):
        (tmp_path / "bench/oss" / name).write_text("synthetic")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(
        module.sys, "argv", ["run.py", "--repeats", "1", "--output", str(tmp_path / "out")]
    )
    monkeypatch.setattr(
        module.subprocess,
        "check_output",
        lambda command, **kw: "a" * 40 if "rev-parse" in command else "",
    )
    calls = []

    def time_out(command, **kwargs):
        calls.append(command)
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(module.subprocess, "run", time_out)
    monkeypatch.setattr(
        module,
        "inspect_run",
        lambda path: {"assurance": {}, "integrity_errors": ["incomplete run"]},
    )
    assert module.main() == 1
    result = json.loads((tmp_path / "out/result.json").read_text())
    assert result["passed"] is False
    assert len(calls) == len(result["records"]) == 4
    assert all(
        row["timed_out"] and row["exit_code"] == 124 and not row["passed"]
        for row in result["records"]
    )
    assert (tmp_path / "out/checkpoint.json").is_file()
    assert len(list((tmp_path / "out").glob("*.log"))) == 4
