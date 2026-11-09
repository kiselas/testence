"""The one-page reference matches the code, the GitLab template is shown verbatim, and
``testence timing`` says where a run's time went (stage 7, T07)."""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest

from testence import timing
from testence.cli import main
from testence.dsl.steps import Actions
from testence.evidence import EvidenceWriter

ROOT = Path(__file__).parents[1]
PLUGIN = (ROOT / "src" / "testence" / "pytest_plugin.py").read_text(encoding="utf-8")
CLI = (ROOT / "src" / "testence" / "cli.py").read_text(encoding="utf-8")


def _public_steps() -> set[str]:
    return {
        name
        for name, value in inspect.getmembers(Actions)
        if not name.startswith("_") and (callable(value) or isinstance(value, property))
    }


@pytest.mark.parametrize("language", ["en", "ru"])
def test_the_reference_lists_every_step_option_and_command(language: str) -> None:
    page = (ROOT / "docs" / language / "reference.md").read_text(encoding="utf-8")
    missing = sorted(name for name in _public_steps() if f"ex.{name}" not in page)
    assert not missing, f"{language}/reference.md lacks ex steps: {missing}"
    options = set(re.findall(r'"(--testence-[a-z-]+)"', PLUGIN))
    assert not sorted(o for o in options if o not in page), f"{language}: pytest options"
    commands = set(re.findall(r'\bsub\.add_parser\(\s*"([a-z-]+)"', CLI))
    assert commands, "no command found in cli.py"
    absent = sorted(command for command in commands if f"testence {command}" not in page)
    assert not absent, f"{language}/reference.md lacks commands: {absent}"


def test_the_ci_page_shows_the_gitlab_template_verbatim() -> None:
    template = (ROOT / "docs" / "examples" / "gitlab-ci.yml").read_text(encoding="utf-8")
    yaml = pytest.importorskip("yaml")
    document = yaml.safe_load(template)
    assert {"collect", "e2e"} <= set(document)
    assert document["e2e"]["resource_group"] == "target-$TESTENCE_PROFILE"
    for language in ("en", "ru"):
        page = (ROOT / "docs" / language / "ci.md").read_text(encoding="utf-8")
        assert f"```yaml\n{template}```" in page, language


def _run(root: Path, name: str, call_ms: float) -> Path:
    test = "tests/test_shop.py::test_checkout"
    other = "tests/test_shop.py::test_cart"
    writer = EvidenceWriter(root, run_id=name, worker="")
    writer.emit("run.start")
    writer.emit("test.start", test=test)
    writer.emit("test.phase", test=test, nodeid=test, phase="setup", duration_ms=900.0)
    writer.emit("api.request", test=test, method="GET", url="/api/x", duration_ms=120.0)
    writer.emit("api.request", test=test, method="POST", url="/api/x", duration_ms=80.0)
    writer.emit("test.phase", test=test, nodeid=test, phase="call", duration_ms=call_ms)
    writer.emit("test.waits", test=test, waited_ms=400.0)
    writer.emit("test.phase", test=test, nodeid=test, phase="teardown", duration_ms=300.0)
    writer.emit("test.end", test=test, nodeid=test, status="passed")
    writer.emit("test.start", test=other)
    writer.emit("test.phase", test=other, nodeid=other, phase="call", duration_ms=100.0)
    writer.emit("test.end", test=other, nodeid=other, status="failed")
    writer.emit("run.end", duration_ms=5_000.0)
    writer.close()
    return writer.run_dir


def test_timing_splits_the_phases_and_counts_api_calls_and_waits(tmp_path: Path) -> None:
    document = timing.load(_run(tmp_path, "r-one", 2_000.0))
    assert document["wall_ms"] == 5_000.0
    assert document["phases_ms"] == {"setup": 900.0, "call": 2_100.0, "teardown": 300.0}
    assert document["api"] == {"calls": 2, "ms": 200.0}
    first = document["by_test"][0]
    assert (first["test"], first["ms"], first["api_calls"], first["waited_ms"]) == (
        "tests/test_shop.py::test_checkout",
        3_200.0,
        2,
        400.0,
    )
    assert "setup 0.9 s, call 2.1 s, teardown 0.3 s" in timing.render(document)


def test_timing_compares_two_runs_test_by_test(tmp_path: Path, capsys) -> None:
    before = _run(tmp_path, "r-before", 5_000.0)
    after = _run(tmp_path, "r-after", 1_000.0)
    assert main(["timing", str(before), str(after), "--json"]) == 0
    document = json.loads(capsys.readouterr().out)
    assert document["by_test"][0] == {
        "test": "tests/test_shop.py::test_checkout",
        "before_ms": 6_200.0,
        "after_ms": 2_200.0,
        "delta_ms": -4_000.0,
    }
    assert main(["timing", str(before), str(after)]) == 0
    assert "-4.0 s" in capsys.readouterr().out
    assert main(["timing", str(tmp_path / "missing")]) == 2
