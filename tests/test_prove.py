"""``testence prove``: the strict mode of ADR-0033 in one command."""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path

import jsonschema
import pytest

from testence.ci import QUALITY_FAILURE_EXIT
from testence.cli import main

CONTROL = {
    "description": "The API answers the save but stores nothing",
    "claims": ["widgets.create.persisted"],
}


def _plan(claims: list[str]) -> str:
    document = {
        "schema": "testence/planspec/2",
        "project_id": "prove-demo",
        "id": "widgets.create",
        "title": "Create widget",
        "claims": [
            {
                "id": f"widgets.create.{claim}",
                "statement": f"The widget is {claim}.",
                "oracles": ["api"],
                "required": True,
            }
            for claim in claims
        ],
        "assertions": [
            {
                "id": f"assert.widget.{claim}",
                "claim_id": f"widgets.create.{claim}",
                "oracle": "api",
                "required": True,
            }
            for claim in claims
        ],
        "scenarios": [
            {
                "id": "create-widget",
                "title": "Create one widget",
                "claims": [f"widgets.create.{claim}" for claim in claims],
            }
        ],
    }
    return f"# Widget creation\n\n```testence-planspec\n{json.dumps(document, indent=1)}\n```\n"


HEADER = """
import pytest

from testence.oracle import verify


def product_read(testence_control):
    broken = testence_control is not None and testence_control.name == "drop-save"
    return {"id": None} if broken else {"id": 42}
"""

# Expected value from the plan: the widget the test created has id 42.
HONEST = """

@pytest.mark.testence(plan="plan.md", case_id="create-widget", claims=["widgets.create.{c}"])
def test_{c}(testence_writer, request, testence_control):
    verify(testence_writer, request.node.nodeid, "{c} widget", {{"id": 42}},
           product_read(testence_control),
           assertion_id="assert.widget.{c}", claim_id="widgets.create.{c}")
"""

# The defect the strict mode exists for: the product is compared with itself.
VACUOUS = """

@pytest.mark.testence(plan="plan.md", case_id="create-widget", claims=["widgets.create.{c}"])
def test_{c}(testence_writer, request, testence_control):
    observed = product_read(testence_control)
    verify(testence_writer, request.node.nodeid, "{c} widget", observed, observed,
           assertion_id="assert.widget.{c}", claim_id="widgets.create.{c}")
"""

# Red without any control: the green run must stop the command.
BROKEN = """

@pytest.mark.testence(plan="plan.md", case_id="create-widget", claims=["widgets.create.{c}"])
def test_{c}(testence_writer, request, testence_control):
    verify(testence_writer, request.node.nodeid, "{c} widget", {{"id": 42}}, {{"id": 7}},
           assertion_id="assert.widget.{c}", claim_id="widgets.create.{c}")
"""


def _project(
    root: Path,
    tests: dict[str, str],
    controls: dict[str, dict] | None = None,
) -> Path:
    """``tests`` maps a claim suffix to HONEST, VACUOUS or BROKEN."""
    (root / "testence.json").write_text(
        json.dumps(
            {
                "project_id": "prove-demo",
                "controls": {"drop-save": CONTROL} if controls is None else controls,
            }
        ),
        encoding="utf-8",
    )
    (root / "plan.md").write_text(_plan(list(tests)), encoding="utf-8")
    body = HEADER + "".join(kind.format(c=claim) for claim, kind in tests.items())
    (root / "test_widgets.py").write_text(body, encoding="utf-8")
    return root


def _prove(
    project: Path, *args: str, tail: tuple[str, ...] = ("--", "-q", "-p", "no:cacheprovider")
):
    # The runs are subprocesses, so the pytest temp directory is the child's own; a
    # fresh one per call keeps a clean-up of the previous run from racing this one.
    basetemp = project / ".pytest-tmp"
    return main(["prove", "--project", str(project), *args, *tail, f"--basetemp={basetemp}"])


def _receipt(project: Path, run_id: str) -> dict:
    path = project / "runs" / f"{run_id}.receipt.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_prove_runs_the_green_run_and_every_control_and_writes_one_receipt(tmp_path, capsys):
    project = _project(tmp_path, {"persisted": HONEST})

    code = _prove(project, "--run-id", "ci-1")

    assert code == 0, capsys.readouterr()
    assert sorted(path.name for path in (project / "runs").iterdir()) == [
        "ci-1",
        "ci-1-drop-save",
        "ci-1.receipt.json",
    ]
    receipt = _receipt(project, "ci-1")
    assert receipt["run_id"] == "ci-1"
    assert receipt["quality"]["mode"] == "proven"
    assert receipt["quality"]["exit_code"] == 0
    proof = receipt["quality"]["negative_proof"]
    assert proof["claims"]["widgets.create.persisted"]["outcome"] == "proven"
    assert [item["run_id"] for item in proof["runs"]] == ["ci-1-drop-save"]
    schema = json.loads(
        files("testence.contracts")
        .joinpath("schemas", "ci-receipt.schema.json")
        .read_text(encoding="utf-8")
    )
    jsonschema.validate(receipt, schema)
    output = capsys.readouterr().out
    assert "1 of 1 required claims proven" in output
    assert f"prove -> {project / 'runs' / 'ci-1.receipt.json'}" in output


def test_a_vacuous_test_fails_proven_with_the_ci_evaluate_exit_code(tmp_path, capsys):
    project = _project(
        tmp_path,
        {"persisted": HONEST, "listed": VACUOUS},
        {"drop-save": {**CONTROL, "claims": ["widgets.create.persisted", "widgets.create.listed"]}},
    )

    code = _prove(project, "--run-id", "ci-2")

    # The same code `ci evaluate --quality-mode proven` gives: a quality failure.
    assert code == QUALITY_FAILURE_EXIT, capsys.readouterr()
    claims = _receipt(project, "ci-2")["quality"]["negative_proof"]["claims"]
    assert claims["widgets.create.persisted"]["outcome"] == "proven"
    assert claims["widgets.create.listed"]["outcome"] == "stayed_green"
    output = capsys.readouterr().out
    assert "widgets.create.listed: stayed_green" in output
    assert "not satisfied: no negative proof: widgets.create.listed (stayed_green)" in output


def test_a_red_green_run_stops_before_any_negative_run(tmp_path, capsys):
    project = _project(tmp_path, {"persisted": BROKEN})

    code = _prove(project, "--run-id", "ci-3")

    assert code == 1
    assert sorted(path.name for path in (project / "runs").iterdir()) == ["ci-3"]
    output = capsys.readouterr().out
    assert "the green run exited 1; the negative runs were not executed" in output
    assert "testence inspect" in output


def test_control_names_pick_the_runs_and_the_receipt_lists_only_those(tmp_path, capsys):
    controls = {
        "drop-save": CONTROL,
        "slow-save": {
            "description": "The save answers late",
            "claims": ["widgets.create.persisted"],
        },
    }
    project = _project(tmp_path, {"persisted": HONEST}, controls)

    # `slow-save` does nothing in the product stand-in, so it proves nothing; it is
    # the control that was not asked for, and it must not run.
    code = _prove(project, "--run-id", "ci-4", "--control", "drop-save")

    assert code == 0, capsys.readouterr()
    names = sorted(path.name for path in (project / "runs").iterdir())
    assert "ci-4-slow-save" not in names
    assert "ci-4-drop-save" in names

    # Without --control every declared control runs.
    code = _prove(project, "--run-id", "ci-5")
    # `proven` wins over the `stayed_green` of the control that does nothing.
    assert code == 0, capsys.readouterr()
    names = sorted(path.name for path in (project / "runs").iterdir())
    assert {"ci-5-drop-save", "ci-5-slow-save"} <= set(names)


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["--control", "no-such"], "unknown control 'no-such'; declared: drop-save"),
        (["--run-id", "bad id"], "run id must contain only"),
        (["--run-id", "ci-6", "--", "-q", "--testence-reruns", "1"], "cannot be combined"),
    ],
)
def test_prove_refuses_before_running_anything(tmp_path, capsys, arguments, message):
    project = _project(tmp_path, {"persisted": HONEST})

    code = main(["prove", "--project", str(project), *arguments])

    assert code == 2
    assert message in capsys.readouterr().err
    assert not (project / "runs").exists()


def test_prove_needs_a_declared_control(tmp_path, capsys):
    project = _project(tmp_path, {"persisted": HONEST}, {})

    assert main(["prove", "--project", str(project)]) == 2
    assert "no negative control is declared" in capsys.readouterr().err
    assert not (project / "runs").exists()


def test_prove_does_not_reuse_a_run_directory(tmp_path, capsys):
    project = _project(tmp_path, {"persisted": HONEST})
    (project / "runs" / "ci-7-drop-save").mkdir(parents=True)

    assert main(["prove", "--project", str(project), "--run-id", "ci-7"]) == 2
    assert "run directory already exists" in capsys.readouterr().err
    assert not (project / "runs" / "ci-7").exists()


def test_json_output_is_one_document_on_stdout(tmp_path, capsys):
    project = _project(tmp_path, {"persisted": HONEST})

    code = _prove(project, "--run-id", "ci-8", "--json")

    assert code == 0
    document = json.loads(capsys.readouterr().out)
    assert document["run_id"] == "ci-8"
    assert document["final_exit"] == 0
    assert document["claims"] == {"widgets.create.persisted": "proven"}
    assert [item["run_id"] for item in document["runs"]] == ["ci-8", "ci-8-drop-save"]
    assert [item["exit_code"] for item in document["runs"]] == [0, 1]


def test_a_blunt_control_is_a_warning_in_prove_the_receipt_and_the_summary(tmp_path, capsys):
    # The control breaks every read, so two of the three failed claims are collateral.
    project = _project(tmp_path, {"persisted": HONEST, "listed": HONEST, "audited": HONEST})

    code = _prove(project, "--run-id", "ci-9")

    # The gate is unchanged: the claims the control does not list have no proof.
    assert code == QUALITY_FAILURE_EXIT
    receipt = _receipt(project, "ci-9")
    proof = receipt["quality"]["negative_proof"]
    assert proof["claims"]["widgets.create.persisted"]["outcome"] == "proven"
    (negative,) = proof["controls"]
    assert negative["run_id"] == "ci-9-drop-save"
    assert negative["failed_claims"] == 3
    assert negative["collateral_claims"] == ["widgets.create.audited", "widgets.create.listed"]
    assert negative["collateral_share"] == pytest.approx(0.667)
    assert negative["blunt"] is True
    assert "too blunt for proven" in capsys.readouterr().out

    assert (
        main(
            [
                "ci",
                "summary",
                str(project / "runs" / "ci-9"),
                "--negative-run",
                str(project / "runs" / "ci-9-drop-save"),
            ]
        )
        == 0
    )
    assert "too blunt for proven" in capsys.readouterr().out
    # The negative run's own summary says it too.
    assert main(["ci", "summary", str(project / "runs" / "ci-9-drop-save")]) == 0
    assert "too blunt for proven" in capsys.readouterr().out


def test_a_precise_control_has_no_warning(tmp_path, capsys):
    project = _project(tmp_path, {"persisted": HONEST})

    assert _prove(project, "--run-id", "ci-10") == 0

    (negative,) = _receipt(project, "ci-10")["quality"]["negative_proof"]["controls"]
    assert negative["blunt"] is False
    assert "collateral_claims" not in negative
    assert "warning" not in capsys.readouterr().out


def test_negative_runs_never_repeat_even_when_the_environment_asks(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TESTENCE_RERUNS", "2")
    project = _project(tmp_path, {"persisted": HONEST})

    # Without the reset the negative run would be a usage error (exit 4).
    assert _prove(project, "--run-id", "ci-11") == 0, capsys.readouterr()


def test_prove_on_a_fresh_scaffold_proves_the_onboarding_claim(tmp_path, monkeypatch, capsys):
    """The acceptance run: the project ``testence init`` writes, no test named, real browser."""
    from testence.application import init_project

    # Two browsers on one host must not fight for the default CDP port.
    monkeypatch.setenv("TESTENCE_DEBUG_PORT", "0")
    init_project(tmp_path)

    code = main(["prove", "--project", str(tmp_path), "--run-id", "demo-1"])

    assert code == 0, capsys.readouterr()
    receipt = _receipt(tmp_path, "demo-1")
    claims = receipt["quality"]["negative_proof"]["claims"]
    assert {claim: entry["outcome"] for claim, entry in claims.items()} == {
        "onboarding.proof.recorded": "proven"
    }
    assert (tmp_path / "runs" / "demo-1-drop-save").is_dir()
