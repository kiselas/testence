"""``testence plan skeleton``: a Markdown case file becomes a valid plan and test stubs."""

from __future__ import annotations

import ast
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from testence.cli import main
from testence.contracts import load_plan
from testence.skeleton import SkeletonError, parse_cases

FIXTURES = Path(__file__).parent / "fixtures" / "skeleton"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    for name in ("cases_table.md", "cases_sections.md"):
        shutil.copy(FIXTURES / name, tmp_path / name)
    return tmp_path


def _run(project: Path, *args: str, capsys: pytest.CaptureFixture[str]) -> dict:
    code = main(["plan", "skeleton", *args, "--root", str(project), "--json"])
    assert code == 0
    return json.loads(capsys.readouterr().out)


def test_table_format_with_cyrillic_becomes_a_valid_plan_and_a_file_per_case(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = _run(
        project,
        str(project / "cases_table.md"),
        "--plan",
        str(project / "specs" / "login.json"),
        "--tests",
        str(project / "tests_e2e"),
        capsys=capsys,
    )

    assert result["format"] == "table"
    assert result["plan"]["valid"] is True
    plan = load_plan(project / "specs" / "login.json")
    assert plan.title == "Вход в демо-приложение"
    assert [scenario.id for scenario in plan.scenarios] == ["case-1", "case-2"]
    # Every expected value is the source text, verbatim, never a paraphrase.
    assert [assertion.expected for assertion in plan.assertions] == [
        "Отображается приветствие «signed in as demo@example.test»",
        "Кнопка «Sign in» неактивна",
        "Под полем пароля текст «Password is required»",
    ]
    assert all(assertion.required for assertion in plan.assertions)
    # A case without an expected result is a question, not a scenario.
    assert [question["case"] for question in result["open_questions"]] == [3]

    names = sorted(path.name for path in (project / "tests_e2e").iterdir())
    assert names == ["test_01_uspeshnyy_vhod.py", "test_02_pustoy_parol.py"]
    source = (project / "tests_e2e" / "test_02_pustoy_parol.py").read_text(encoding="utf-8")
    assert source.startswith("# testence:skeleton sha256=")
    assert 'PLAN = "specs/login.json"' in source
    assert 'case_id="case-2"' in source
    assert 'intent="кейс 2 ш.2: Ввести email «demo@example.test»"' in source
    assert 'ex.goto("/login"' in source
    # A quoted value of the step is the fill value; the address is never guessed.
    assert '"demo@example.test",' in source
    assert 'claim_id="cases-table.case-2.expected-2"' in source
    ast.parse(source)


def test_sections_format_attaches_expectations_and_writes_one_module(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = _run(
        project,
        str(project / "cases_sections.md"),
        "--plan",
        str(project / "specs" / "widgets.md"),
        "--tests",
        str(project / "tests_e2e"),
        "--module",
        "test_widgets",
        capsys=capsys,
    )

    assert result["format"] == "sections"
    assert [case["claims"] for case in result["cases"]] == [
        ["cases-sections.case-1.expected-1", "cases-sections.case-1.expected-2"],
        ["cases-sections.case-2.expected-1", "cases-sections.case-2.expected-2"],
    ]
    plan = load_plan(project / "specs" / "widgets.md")
    assert [assertion.expected for assertion in plan.assertions] == [
        'The form "New widget" opens',
        'the catalogue lists "W-1" with status "draft"',
        'The "Save" button stays on the form',
        'The message "Name is required" is shown',
    ]
    module = project / "tests_e2e" / "test_widgets.py"
    tree = ast.parse(module.read_text(encoding="utf-8"))
    functions = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
    assert functions == [
        "TODO",
        "TODO_VALUE",
        "test_01_create_a_widget",
        "test_02_validation_of_an_empty_name",
    ]
    text = module.read_text(encoding="utf-8")
    # The step-level expectation follows its step, the case-level one comes last.
    assert text.index('The form "New widget" opens') < text.index('Type "W-1"')
    assert 'ex.press("Control+S"' in text or "ex.press('Control+S'" in text
    assert "Precondition: the catalogue is empty." in text


def _generate_sections(project: Path, capsys: pytest.CaptureFixture[str]) -> Path:
    _run(
        project,
        str(project / "cases_sections.md"),
        "--plan",
        str(project / "specs" / "widgets.json"),
        "--tests",
        str(project / "tests_e2e"),
        capsys=capsys,
    )
    return project / "tests_e2e"


def test_generated_code_fails_fast_on_a_missing_address(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tests = _generate_sections(project, capsys)
    namespace: dict[str, object] = {}
    module = next(tests.glob("test_01_*.py"))
    exec(compile(module.read_text(encoding="utf-8"), str(module), "exec"), namespace)  # noqa: S102
    with pytest.raises(NotImplementedError, match="no Target yet"):
        namespace["TODO"]("button")  # type: ignore[operator]


def test_generated_code_passes_ruff(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # The dependency-floor environment installs no dev tools; the lint check needs ruff.
    pytest.importorskip("ruff", reason="ruff is a dev dependency, absent from the floor venv")
    tests = _generate_sections(project, capsys)
    for args in (["check", "--no-cache"], ["format", "--check", "--no-cache"]):
        completed = subprocess.run(
            [sys.executable, "-m", "ruff", *args, "--isolated", "--line-length", "100", str(tests)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr


def test_rerun_is_idempotent_and_keeps_edited_files(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = [
        str(project / "cases_table.md"),
        "--plan",
        str(project / "specs" / "login.json"),
        "--tests",
        str(project / "tests_e2e"),
    ]
    _run(project, *args, capsys=capsys)
    again = _run(project, *args, capsys=capsys)
    assert {entry["status"] for entry in again["files"]} == {"unchanged"}

    edited = project / "tests_e2e" / "test_01_uspeshnyy_vhod.py"
    authored = edited.read_text(encoding="utf-8").replace(
        'TODO("Нажать «Sign in»")', 'Target("role", "button", name="Sign in")'
    )
    edited.write_text(authored, encoding="utf-8")
    source = project / "cases_table.md"
    source.write_text(
        source.read_text(encoding="utf-8").replace("Пустой пароль", "Пароль не введён"),
        encoding="utf-8",
    )

    third = _run(project, *args, capsys=capsys)
    statuses = {Path(entry["path"]).name: entry["status"] for entry in third["files"]}
    assert statuses["test_01_uspeshnyy_vhod.py"] == "kept"
    assert statuses["login.json"] == "updated"
    assert statuses["test_02_parol_ne_vveden.py"] == "created"
    assert edited.read_text(encoding="utf-8") == authored

    plan_file = project / "specs" / "login.json"
    document = json.loads(plan_file.read_text(encoding="utf-8"))
    document["claims"][0]["oracles"] = ["ui", "api"]
    plan_file.write_text(json.dumps(document), encoding="utf-8")
    fourth = _run(project, *args, capsys=capsys)
    assert {Path(e["path"]).name: e["status"] for e in fourth["files"]}["login.json"] == "kept"


def test_duplicate_case_numbers_and_files_without_cases_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(SkeletonError, match="appears twice"):
        parse_cases("## Case 1 — a\n1. Click\nExpected: x\n\n## Case 1 — b\n1. Click\n")
    with pytest.raises(SkeletonError, match="no cases found"):
        parse_cases("# Notes\n\n1. just a list\n")
    empty = tmp_path / "empty.md"
    empty.write_text("## Case 1 — nothing to observe\n1. Click it\n", encoding="utf-8")
    code = main(
        [
            "plan",
            "skeleton",
            str(empty),
            "--plan",
            str(tmp_path / "p.json"),
            "--tests",
            str(tmp_path / "t"),
        ]
    )
    assert code == 2
    assert not (tmp_path / "p.json").exists()


def test_russian_sections_with_inline_expectation() -> None:
    kind, cases = parse_cases(
        "### Кейс 4 — Удаление\n"
        "1. Нажать «Удалить». Ожидается: открыт диалог «Удалить виджет?»\n"
        "2. Нажать «Да».\n"
        "   - → Тост «Виджет удалён»\n"
    )
    assert kind == "sections"
    [case] = cases
    assert (case.number, case.title) == (4, "Удаление")
    assert [step.text for step in case.steps] == ["Нажать «Удалить».", "Нажать «Да»."]
    assert case.all_expected == ["открыт диалог «Удалить виджет?»", "Тост «Виджет удалён»"]


def test_numbered_sections_without_an_outcome_are_not_cases() -> None:
    kind, cases = parse_cases(
        "## 1. Overview\n\n1. Background item\n\n"
        "## 2026-11 release notes\n\nText.\n\n"
        "## Case 1 — Save\n\n1. Click Save\n\nExpected: saved\n\n"
        "### 2. Unlabelled but with an outcome\n\n1. Click Delete\n   - → gone\n"
    )
    assert kind == "sections"
    assert [(case.number, case.title) for case in cases] == [
        (1, "Save"),
        (2, "Unlabelled but with an outcome"),
    ]


def test_bullet_steps_are_steps_and_a_case_without_steps_is_warned(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, cases = parse_cases(
        "## Case 1 — Bullets\n\n- Priority: High\n- Open the page\n- Click Save\n"
        "  - the button is at the bottom\n\nExpected: saved\n"
    )
    assert [step.text for step in cases[0].steps] == [
        "Open the page",
        "Click Save - the button is at the bottom",
    ]
    source = tmp_path / "cases.md"
    source.write_text("## Case 1 — Only an outcome\n\nExpected: the list is empty\n", "utf-8")
    result = _run(
        tmp_path,
        str(source),
        "--plan",
        str(tmp_path / "p.json"),
        "--tests",
        str(tmp_path / "t"),
        capsys=capsys,
    )
    assert [warning["case"] for warning in result["warnings"]] == [1]


def test_keys_are_pressed_and_unquoted_values_fail_until_written(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = project / "keys.md"
    source.write_text(
        "## Case 1 — Keys\n\n1. Press Enter\n2. Type the name and press Enter\n"
        "3. Enter the name\n\nExpected: saved\n",
        encoding="utf-8",
    )
    _run(
        project,
        str(source),
        "--plan",
        str(project / "k.json"),
        "--tests",
        str(project / "t"),
        capsys=capsys,
    )
    text = next((project / "t").glob("test_01_*.py")).read_text(encoding="utf-8")
    body = text[text.index("def test_01") :]
    assert 'ex.press("Enter", intent="case 1 step 1: Press Enter")' in body
    assert body.count("ex.press(") == 2  # step 2 fills, then presses
    assert body.count("ex.fill(") == 2
    assert '"TODO"' not in body
    assert 'TODO_VALUE("Enter the name")' in body


def test_a_retitled_case_removes_its_untouched_old_file_and_flags_an_edited_one(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = project / "cases_table.md"
    args = [str(source), "--plan", str(project / "s.json"), "--tests", str(project / "t")]
    _run(project, *args, capsys=capsys)
    edited = project / "t" / "test_02_pustoy_parol.py"
    edited.write_text(edited.read_text(encoding="utf-8") + "\n# authored\n", encoding="utf-8")
    text = source.read_text(encoding="utf-8")
    source.write_text(
        text.replace("Успешный вход", "Вход").replace("Пустой пароль", "Без пароля"),
        encoding="utf-8",
    )

    result = _run(project, *args, capsys=capsys)

    statuses = {Path(entry["path"]).name: entry["status"] for entry in result["files"]}
    assert statuses["test_01_uspeshnyy_vhod.py"] == "removed"
    assert not (project / "t" / "test_01_uspeshnyy_vhod.py").exists()
    assert statuses["test_02_pustoy_parol.py"] == "stale"
    assert edited.exists()
    assert statuses["test_01_vhod.py"] == "created"


def test_a_case_file_that_is_not_utf8_is_an_input_error(tmp_path: Path) -> None:
    source = tmp_path / "cp1251.md"
    source.write_bytes("## Кейс 1 — Вход\n1. Нажать «Войти»\nОжидается: открыт\n".encode("cp1251"))
    code = main(
        ["plan", "skeleton", str(source), "--plan", str(tmp_path / "p.json")]
        + ["--tests", str(tmp_path / "t")]
    )
    assert code == 2
