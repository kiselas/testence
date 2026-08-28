"""Exporter seam and the in-tree exporters (ADR-0013).

The contract test is parametrised over every *registered* exporter, so a
third-party exporter installed into the environment inherits this harness for free —
that is what "nothing is nailed down" has to mean in practice.
"""

from __future__ import annotations

import ast
import json
import os
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

import testence
from testence.cli import main
from testence.evidence import EvidenceWriter
from testence.export import (
    BUILTIN_EXPORTERS,
    ExporterError,
    available,
    export_run,
    load,
)

# Reporting libraries the framework must never import: capture is ambient, and a
# push-model SDK in here would recreate the second source of truth ADR-0013 removes.
FORBIDDEN_IMPORTS = {
    "allure",
    "allure_commons",
    "allure_pytest",
    "pytest_html",
    "reportportal_client",
    "junit_xml",
    "xmlrunner",
}


def build_ledger(tmp_path: Path, run_id: str = "r-export-1") -> Path:
    """A ledger with the two shapes that matter: a green nested test and a red one
    carrying an evidence pack and a disagreeing oracle."""
    writer = EvidenceWriter(tmp_path, run_id=run_id, worker="")
    writer.emit(
        "run.start",
        testence="0.1.0.dev0",
        fingerprint={"os": "test", "python": "3.12", "base_url": "https://app.example"},
    )

    writer.emit(
        "test.start",
        test="test_login",
        file="tests/test_login.py",
        nodeid="tests/test_login.py::test_login",
        markers=["Login", "Smoke"],
    )
    writer.emit("step.start", test="test_login", step="s1", intent="log in as admin", depth=0)
    writer.emit(
        "step.start", test="test_login", step="s2", intent="fill the password field",
        target="textbox 'Password'", depth=1,
    )
    writer.emit(
        "step.end", test="test_login", step="s2", status="ok", duration_ms=12.0,
        depth=1, children=0,
    )
    writer.emit(
        "step.end", test="test_login", step="s1", status="ok", duration_ms=40.0,
        depth=0, children=1,
    )
    writer.emit("test.end", test="test_login", status="pass", duration_ms=120.0)

    pack_dir = writer.run_dir / "test_hosts" / "pack"
    pack_dir.mkdir(parents=True)
    (pack_dir / "aria.txt").write_text("dialog 'Create host'\n", encoding="utf-8")
    (pack_dir / "network.jsonl").write_text('{"url":"/api/hosts","status":500}\n', encoding="utf-8")
    (pack_dir / "pack.json").write_text('{"error":"boom"}\n', encoding="utf-8")

    writer.emit(
        "test.start",
        test="test_hosts",
        file="tests/test_hosts.py",
        nodeid="tests/test_hosts.py::test_hosts",
        markers=["Regression"],
    )
    writer.emit("step.start", test="test_hosts", step="s1", intent="create a host", depth=0)
    writer.emit(
        "step.end", test="test_hosts", step="s1", status="fail", duration_ms=900.0,
        depth=0, children=0, error="locator resolved to 0 elements",
    )
    writer.emit(
        "oracle", test="test_hosts", name="host count", ok=False,
        diff=[{"field": "count", "ui": 3, "api": 4}],
    )
    writer.emit(
        "pack", test="test_hosts", dir="test_hosts/pack",
        sections_est_tokens={"aria": 10, "network": 8}, error="AssertionError: boom",
    )
    writer.emit(
        "test.end", test="test_hosts", status="fail", duration_ms=1500.0, pack="test_hosts/pack",
    )
    writer.emit("run.end", duration_ms=1700.0, passed=1, failed=1)
    writer.close()
    return writer.run_dir


# ── the seam ──────────────────────────────────────────────────────────────────


def test_builtins_are_registered():
    registry = available()
    assert registry["allure"] == "built-in"
    assert registry["ctrf"] == "built-in"


def test_unknown_exporter_names_the_alternatives():
    with pytest.raises(ExporterError) as excinfo:
        load("testops")
    message = str(excinfo.value)
    assert "testops" in message and "allure" in message


def test_every_exporter_satisfies_the_two_symbol_contract():
    for name in available():
        module = load(name)
        assert module.name == name
        assert callable(module.export)


@pytest.mark.parametrize("name", sorted(available()))
def test_exporter_writes_what_it_returns(tmp_path, name):
    """Contract every exporter obeys: files land, and the returned list is the truth
    about what landed (a caller archives exactly these paths)."""
    run_dir = build_ledger(tmp_path)
    out = tmp_path / f"out-{name}"
    files = export_run(run_dir, name, out)

    assert files, f"{name} exported nothing"
    for path in files:
        assert path.is_file(), f"{name} returned a path it did not write: {path}"
        assert path.stat().st_size > 0
        assert out in path.parents


@pytest.mark.parametrize("name", sorted(available()))
def test_export_is_deterministic(tmp_path, name):
    """Same ledger in, byte-identical files out — the property that lets goldens pin
    a mapping and makes an upstream format change visible as a diff."""
    run_dir = build_ledger(tmp_path)
    first = {p.name: p.read_bytes() for p in export_run(run_dir, name, tmp_path / "a")}
    second = {p.name: p.read_bytes() for p in export_run(run_dir, name, tmp_path / "b")}
    assert first == second


@pytest.mark.parametrize("name", sorted(available()))
def test_exports_a_ledger_without_the_newer_fields(tmp_path, name):
    """An older ledger (no nodeid, no markers) must still export: schema fields are
    appended, never retroactive."""
    writer = EvidenceWriter(tmp_path, run_id="r-old", worker="")
    writer.emit("run.start", testence="0.0.1")
    writer.emit("test.start", test="test_legacy", file="tests/test_legacy.py")
    writer.emit("test.end", test="test_legacy", status="pass", duration_ms=5.0)
    writer.emit("run.end", duration_ms=6.0, passed=1, failed=0)
    writer.close()

    files = export_run(writer.run_dir, name, tmp_path / f"legacy-{name}")
    assert files
    blob = "\n".join(p.read_text(encoding="utf-8") for p in files if p.suffix == ".json")
    assert "test_legacy" in blob


# ── allure ────────────────────────────────────────────────────────────────────


def _allure_results(out: Path) -> dict[str, dict]:
    results = {}
    for path in out.glob("*-result.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        results[doc["fullName"]] = doc
    return results


def test_allure_maps_status_steps_and_tags(tmp_path):
    run_dir = build_ledger(tmp_path)
    out = tmp_path / "allure-results"
    export_run(run_dir, "allure", out)
    results = _allure_results(out)

    green = results["tests/test_login.py::test_login"]
    assert green["status"] == "passed"
    # markers verbatim: a saved TestOps filter keeps working after the swap
    assert {label["value"] for label in green["labels"] if label["name"] == "tag"} == {
        "Login",
        "Smoke",
    }
    # the step tree is nested, not flattened
    assert green["steps"][0]["name"] == "log in as admin"
    assert green["steps"][0]["steps"][0]["name"] == "fill the password field"
    assert green["stop"] >= green["start"]

    red = results["tests/test_hosts.py::test_hosts"]
    assert red["status"] == "failed"
    assert "boom" in red["statusDetails"]["message"]
    attachments = {a["name"]: a for a in red["attachments"]}
    assert {"aria.txt", "network.jsonl", "pack.json", "oracles.json"} <= set(attachments)
    for attachment in attachments.values():
        assert (out / attachment["source"]).is_file()
    assert json.loads((out / attachments["oracles.json"]["source"]).read_text("utf-8"))


def test_allure_environment_carries_the_fingerprint(tmp_path):
    run_dir = build_ledger(tmp_path)
    out = tmp_path / "allure-results"
    export_run(run_dir, "allure", out)
    text = (out / "environment.properties").read_text(encoding="utf-8")
    assert "environment.base_url=https://app.example" in text
    assert "testence.run=r-export-1" in text


def test_allure_history_id_is_stable_across_runs(tmp_path):
    """History must follow the test, not the execution — otherwise TestOps trends
    are a list of unrelated one-shot results."""
    first = build_ledger(tmp_path / "one", run_id="r-1")
    second = build_ledger(tmp_path / "two", run_id="r-2")
    a = _allure_results(Path(export_run(first, "allure", tmp_path / "oa")[0].parent))
    b = _allure_results(Path(export_run(second, "allure", tmp_path / "ob")[0].parent))

    key = "tests/test_login.py::test_login"
    assert a[key]["historyId"] == b[key]["historyId"]
    assert a[key]["uuid"] != b[key]["uuid"]


# ── ctrf ──────────────────────────────────────────────────────────────────────


def test_ctrf_summary_and_tests(tmp_path):
    run_dir = build_ledger(tmp_path)
    files = export_run(run_dir, "ctrf", tmp_path / "ctrf-results")
    assert len(files) == 1

    doc = json.loads(files[0].read_text(encoding="utf-8"))
    assert doc["reportFormat"] == "CTRF"
    summary = doc["results"]["summary"]
    assert (summary["tests"], summary["passed"], summary["failed"]) == (2, 1, 1)
    assert summary["stop"] >= summary["start"]

    tests = {test["name"]: test for test in doc["results"]["tests"]}
    green = tests["tests/test_login.py::test_login"]
    assert green["status"] == "passed"
    assert green["tags"] == ["Login", "Smoke"]
    # nesting a flat format cannot express, kept readable via indentation
    assert green["extra"]["steps"] == ["log in as admin", "  fill the password field"]

    red = tests["tests/test_hosts.py::test_hosts"]
    assert red["status"] == "failed"
    assert "boom" in red["message"]
    assert red["extra"]["evidence_pack"] == "test_hosts/pack"
    assert "[FAILED]" in red["extra"]["steps"][0]


# ── CLI ───────────────────────────────────────────────────────────────────────


def test_cli_exports_and_lists(tmp_path, capsys):
    run_dir = build_ledger(tmp_path)
    assert main(["export", str(run_dir), "--to", "ctrf", "-o", str(tmp_path / "cli-out")]) == 0
    assert (tmp_path / "cli-out" / "ctrf-report.json").is_file()

    assert main(["export", "--list"]) == 0
    listed = capsys.readouterr().out
    assert "allure" in listed and "ctrf" in listed


def test_cli_reports_an_unknown_exporter_without_a_traceback(tmp_path, capsys):
    run_dir = build_ledger(tmp_path)
    assert main(["export", str(run_dir), "--to", "nope"]) == 2
    assert "unknown exporter" in capsys.readouterr().err


def test_cli_default_out_dir(tmp_path):
    run_dir = build_ledger(tmp_path)
    assert main(["export", str(run_dir), "--to", "ctrf"]) == 0
    assert (run_dir / "ctrf-results" / "ctrf-report.json").is_file()


# ── goldens ───────────────────────────────────────────────────────────────────

GOLDEN_LEDGER = Path(__file__).parent / "fixtures" / "golden-run"
GOLDEN_DIR = Path(__file__).parent / "goldens"


@pytest.mark.parametrize("name", sorted(BUILTIN_EXPORTERS))
def test_output_matches_its_golden(tmp_path, name):
    """Pin each mapping byte-for-byte against a checked-in ledger.

    The fixture ledger carries fixed timestamps on purpose: one produced by
    ``EvidenceWriter`` is stamped with the current time, which can prove determinism
    inside a single run but never across commits. This is the test that turns an
    upstream format change — or an accidental mapping edit — into a reviewable diff.

    Regenerate deliberately with ``TESTENCE_UPDATE_GOLDENS=1``, then read the diff;
    that diff *is* the review.
    """
    produced_paths = export_run(GOLDEN_LEDGER, name, tmp_path / name)
    golden = GOLDEN_DIR / name

    if os.environ.get("TESTENCE_UPDATE_GOLDENS"):
        shutil.rmtree(golden, ignore_errors=True)
        golden.mkdir(parents=True)
        for path in produced_paths:
            shutil.copyfile(path, golden / path.name)

    if not golden.is_dir():
        pytest.fail(f"no goldens for {name!r}; generate them with TESTENCE_UPDATE_GOLDENS=1")

    produced = {path.name: path.read_bytes() for path in produced_paths}
    expected = {p.name: p.read_bytes() for p in sorted(golden.iterdir()) if p.is_file()}
    assert sorted(produced) == sorted(expected), f"{name}: the set of exported files drifted"
    for filename in sorted(expected):
        assert produced[filename] == expected[filename], (
            f"{name}/{filename} drifted from its golden — re-run with "
            "TESTENCE_UPDATE_GOLDENS=1 if the change is intended"
        )


# ── third-party exporters (the entry-point path) ──────────────────────────────


class _FakeEntry:
    """Substitute for an ``importlib.metadata`` entry point."""

    def __init__(self, name: str, module: object, dist: str = "acme-testence-testops") -> None:
        self.name = name
        self.dist = SimpleNamespace(name=dist)
        self._module = module

    def load(self) -> object:
        if isinstance(self._module, Exception):
            raise self._module
        return self._module


def _fake_exporter(filename: str = "report.txt") -> SimpleNamespace:
    """An exporter written the way a third party would write one: two symbols."""

    def export(run, out_dir: Path) -> list[Path]:
        target = Path(out_dir) / filename
        target.write_text(f"{len(run.tests)} tests\n", encoding="utf-8")
        return [target]

    return SimpleNamespace(name="testops", export=export)


def test_third_party_exporter_is_discovered_and_usable(tmp_path, monkeypatch):
    """The claim "nothing is nailed down", as a test: an out-of-tree exporter needs
    an entry point and two symbols, and nothing from this tree."""
    module = _fake_exporter()
    monkeypatch.setattr(
        "testence.export._discovered", lambda: {"testops": _FakeEntry("testops", module)}
    )

    assert available()["testops"] == "entry point (acme-testence-testops)"
    assert load("testops") is module

    run_dir = build_ledger(tmp_path)
    files = export_run(run_dir, "testops", tmp_path / "third-party")
    assert [path.name for path in files] == ["report.txt"]
    assert files[0].read_text(encoding="utf-8") == "2 tests\n"


def test_builtin_wins_over_a_third_party_of_the_same_name(monkeypatch):
    """An installed package must not silently redefine what ``--to allure`` means in
    a pipeline that has been green for a year."""
    monkeypatch.setattr(
        "testence.export._discovered",
        lambda: {"allure": _FakeEntry("allure", _fake_exporter())},
    )
    assert available()["allure"] == "built-in"
    assert load("allure").__name__ == "testence.export.allure"


def test_malformed_third_party_exporter_names_what_is_missing(monkeypatch):
    monkeypatch.setattr(
        "testence.export._discovered",
        lambda: {"testops": _FakeEntry("testops", SimpleNamespace(name="testops"))},
    )
    with pytest.raises(ExporterError, match="missing export"):
        load("testops")


def test_non_callable_export_is_refused(monkeypatch):
    monkeypatch.setattr(
        "testence.export._discovered",
        lambda: {"testops": _FakeEntry("testops", SimpleNamespace(name="testops", export="no"))},
    )
    with pytest.raises(ExporterError, match="non-callable"):
        load("testops")


def test_third_party_import_error_is_reported_as_theirs(monkeypatch):
    """Their broken dependency must read as their problem, not as a framework crash."""
    monkeypatch.setattr(
        "testence.export._discovered",
        lambda: {"testops": _FakeEntry("testops", ImportError("no module named 'requests'"))},
    )
    with pytest.raises(ExporterError, match="failed to import"):
        load("testops")


def test_broken_discovery_does_not_break_builtins(monkeypatch):
    """A broken distribution in the environment must not stop a built-in export."""

    def explode(*_args, **_kwargs):
        raise RuntimeError("metadata is corrupt")

    monkeypatch.setattr("importlib.metadata.entry_points", explode)
    assert available()["allure"] == "built-in"
    assert load("ctrf").name == "ctrf"


# ── the invariant ─────────────────────────────────────────────────────────────


def test_framework_imports_no_reporting_library():
    """ADR-0013's greppable invariant, checked structurally rather than by grep so
    the word "allure" in a docstring or a module name cannot fake a pass."""
    root = Path(testence.__file__).parent
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for imported in names:
                if imported.split(".")[0] in FORBIDDEN_IMPORTS:
                    offenders.append(f"{path.relative_to(root)}:{node.lineno} imports {imported}")
    assert not offenders, "reporting libraries must stay out of the runner: " + "; ".join(offenders)
