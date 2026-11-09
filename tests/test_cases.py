"""Manual cases against tests and a run (stage 7, T05).

A team that keeps its cases in Markdown files counts by hand which cases are
automated and copies outcomes into its test report. With case ids on the markers,
``testence cases`` reads both sides: every case with its tests and outcome, the
automated count per file, and the markers that point at a case no file has.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from testence.cases import (
    CasesConfig,
    CasesError,
    load_cases,
    parse_config,
    render_markdown,
    report,
)
from testence.cli import main
from testence.evidence import RUN_ID_ENV
from tests.owned_pytest import run_pytest

ROOT = Path(__file__).parents[1]

CHECKOUT = """# SHOP-12 — Checkout

### 1. Pay with a saved card

- Priority: High

1. Open the cart.
   - → The total is shown
2. Press Pay.
   - → The order is confirmed

### 2. Decline an expired card

- Priority: Medium

1. Pay with an expired card.
   - → "Card expired" is shown

### 3. Pay by invoice

- Priority: Low

1. Choose invoice.
   - → The invoice is sent
"""

CART = """# SHOP-13 cart

### 1. Add an item

1. Press Add.
   - → The cart holds one item

### 2. Old wishlist

- Removed by: SHOP-40 — the wishlist is gone

1. Open the wishlist.
   - → It is empty
"""

SUITE = """
import pytest


@pytest.mark.testence(tms={"cases": ["SHOP-12/1"]})
def test_saved_card():
    assert True


@pytest.mark.testence(tms={"cases": ["SHOP-12/2", "SHOP-13/1"]})
def test_declines_and_adds():
    assert False, "deliberate"


@pytest.mark.testence(tms={"cases": "SHOP-99/1"})
def test_points_nowhere():
    assert True


def test_without_a_case():
    assert True
"""


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "cases").mkdir()
    (tmp_path / "cases" / "SHOP-12-checkout.md").write_text(CHECKOUT, encoding="utf-8")
    (tmp_path / "cases" / "SHOP-13-cart.md").write_text(CART, encoding="utf-8")
    (tmp_path / "test_shop.py").write_text(SUITE.lstrip(), encoding="utf-8")
    (tmp_path / "testence.json").write_text(
        json.dumps({"cases": {"paths": ["cases/*.md"]}}), encoding="utf-8"
    )
    return tmp_path


def _run(project: Path) -> Path:
    env = os.environ.copy()
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env.pop(RUN_ID_ENV, None)
    env.pop("PYTEST_XDIST_WORKER", None)
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
            "--basetemp",
            str(project / ".pytest-tmp"),
            "--testence-headless",
            "-q",
        ],
        cwd=project,
        env=env,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    (run_dir,) = (project / "runs").iterdir()
    return run_dir


def test_cases_of_a_run_with_their_tests_and_outcomes(project: Path, capsys) -> None:
    run_dir = _run(project)
    code = main(["cases", "--project", str(project), "--run", str(run_dir), "--json"])
    result = json.loads(capsys.readouterr().out)
    assert code == 3  # SHOP-99/1 points nowhere
    outcome = {case["id"]: case["outcome"] for case in result["cases"]}
    assert outcome == {
        "SHOP-12/1": "passed",
        "SHOP-12/2": "failed",
        "SHOP-12/3": "not_automated",
        "SHOP-13/1": "failed",
        "SHOP-13/2": "not_automated",
    }
    assert result["files"] == {
        "SHOP-12-checkout.md": {"cases": 3, "automated": 2},
        "SHOP-13-cart.md": {"cases": 1, "automated": 1},
    }
    assert [item["case"] for item in result["unknown"]] == ["SHOP-99/1"]
    priorities = {case["id"]: case["priority"] for case in result["cases"]}
    assert priorities["SHOP-12/1"] == "High" and priorities["SHOP-13/1"] is None
    removed = next(case for case in result["cases"] if case["id"] == "SHOP-13/2")
    assert removed["removed"] is True


def test_markdown_tables_skip_removed_cases(project: Path, capsys) -> None:
    run_dir = _run(project)
    main(["cases", "--project", str(project), "--run", str(run_dir), "--markdown"])
    text = capsys.readouterr().out
    assert "#### SHOP-12-checkout.md: 2 of 3 automated" in text
    assert (
        "| SHOP-12/2 | Decline an expired card | Medium | `test_shop.py::test_declines_and_adds` | failed |"
        in text
    )
    assert "Old wishlist" not in text
    assert "`SHOP-99/1` in `test_shop.py::test_points_nowhere`" in text


def test_a_collection_reports_without_running_anything(project: Path, capsys) -> None:
    project.joinpath("test_shop.py").write_text(
        SUITE.replace('tms={"cases": "SHOP-99/1"}', 'tms={"cases": "SHOP-12/3"}').lstrip(),
        encoding="utf-8",
    )
    code = main(["cases", "--project", str(project), "--json"])
    result = json.loads(capsys.readouterr().out)
    assert code == 0, result
    assert {case["id"]: case["outcome"] for case in result["cases"]}["SHOP-12/3"] == "collected"
    assert not (project / "runs").exists() or not any((project / "runs").iterdir())


def test_configuration_errors_are_named() -> None:
    assert parse_config(None) is None
    assert parse_config("cases/*.md") == CasesConfig(paths=("cases/*.md",))
    for wrong in ({"paths": []}, {"paths": ["x"], "key": "("}, {"paths": ["x"], "other": 1}, 7):
        with pytest.raises(CasesError):
            parse_config(wrong)


def test_no_matching_file_and_a_duplicate_id_are_problems(tmp_path: Path) -> None:
    (tmp_path / "SHOP-12-a.md").write_text(CHECKOUT, encoding="utf-8")
    (tmp_path / "SHOP-12-b.md").write_text(CHECKOUT, encoding="utf-8")
    cases, problems = load_cases(CasesConfig(paths=("*.md",)), tmp_path)
    assert len(cases) == 3 and any("also in" in problem for problem in problems)
    _, missing = load_cases(CasesConfig(paths=("nothing/*.md",)), tmp_path)
    assert missing and "no case file matches" in missing[0]
    text = render_markdown(report(cases, [], problems=problems))
    assert "could not be read" in text
