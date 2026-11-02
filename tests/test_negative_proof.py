"""Negative proof (ADR-0033): a recorded run in which the test failed for its claim."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import jsonschema
import pytest

from testence.assurance import POLICY_DIGEST
from testence.ci import QUALITY_FAILURE_EXIT, CIError, evaluate_ci
from testence.cli import main
from testence.controls import (
    ControlError,
    declared_controls,
    evaluate_negative_proof,
    resolve_control,
)
from testence.evidence import RUN_ID_ENV
from testence.export._model import LoadedRun
from testence.metrics import load_run

ROOT = Path(__file__).parents[1]

PLAN = """
# Widget creation

```testence-planspec
{
  "schema": "testence/planspec/2",
  "project_id": "negative-proof",
  "id": "widgets.create",
  "title": "Create widget",
  "claims": [
    {"id": "widgets.create.persisted", "statement": "The API returns the widget.",
     "oracles": ["api"], "required": true},
    {"id": "widgets.create.listed", "statement": "The list shows the widget.",
     "oracles": ["api"], "required": true},
    {"id": "widgets.create.audited", "statement": "The audit log has the creation.",
     "oracles": ["api"], "required": true}
  ],
  "assertions": [
    {"id": "assert.widget.persisted", "claim_id": "widgets.create.persisted",
     "oracle": "api", "required": true},
    {"id": "assert.widget.listed", "claim_id": "widgets.create.listed",
     "oracle": "api", "required": true},
    {"id": "assert.widget.audited", "claim_id": "widgets.create.audited",
     "oracle": "api", "required": true}
  ],
  "scenarios": [
    {"id": "create-widget", "title": "Create one widget",
     "claims": ["widgets.create.persisted", "widgets.create.listed", "widgets.create.audited"]}
  ]
}
```
""".lstrip()

# A stand-in for the product: the control breaks "saving" for every test that reads it.
TESTS = """
import pytest

from testence.oracle import verify


def product_read(testence_control):
    broken = testence_control is not None and testence_control.name == "drop-save"
    return {"id": None} if broken else {"id": 42}


@pytest.mark.testence(plan="plan.md", case_id="create-widget",
                      claims=["widgets.create.persisted"])
def test_persisted(testence_writer, request, testence_control):
    # Expected value from the plan: the widget the test created has id 42.
    verify(testence_writer, request.node.nodeid, "persisted widget", {"id": 42},
           product_read(testence_control),
           assertion_id="assert.widget.persisted", claim_id="widgets.create.persisted")


@pytest.mark.testence(plan="plan.md", case_id="create-widget",
                      claims=["widgets.create.listed"])
def test_listed_vacuous(testence_writer, request, testence_control):
    # The defect this suite must expose: the expected value is whatever the product
    # showed, so the assertion compares the product with itself and cannot fail.
    observed = product_read(testence_control)
    verify(testence_writer, request.node.nodeid, "listed widget", observed, observed,
           assertion_id="assert.widget.listed", claim_id="widgets.create.listed")


@pytest.mark.testence(plan="plan.md", case_id="create-widget",
                      claims=["widgets.create.audited"])
def test_audited(testence_writer, request):
    verify(testence_writer, request.node.nodeid, "audit entry", {"id": 42}, {"id": 42},
           assertion_id="assert.widget.audited", claim_id="widgets.create.audited")
""".lstrip()

CONTROLS = {
    "drop-save": {
        "description": "The API answers the save but stores nothing",
        "claims": ["widgets.create.persisted", "widgets.create.listed"],
    }
}


def _pytest(project: Path, runs: Path, *args: str) -> tuple[subprocess.CompletedProcess[str], Path]:
    runs.mkdir(parents=True, exist_ok=True)
    before = {path.name for path in runs.iterdir()}
    env = os.environ.copy()
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env.pop(RUN_ID_ENV, None)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "src"), value] if (value := env.get("PYTHONPATH")) else [str(ROOT / "src")]
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "testence.pytest_plugin",
            "--rootdir",
            str(project),
            "--testence-runs-root",
            str(runs),
            "--basetemp",
            str(project / ".pytest-tmp"),
            "-q",
            *args,
        ],
        cwd=project,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    new = [path for path in runs.iterdir() if path.is_dir() and path.name not in before]
    assert len(new) <= 1, result.stdout + result.stderr
    return result, new[0] if new else runs / "<no run>"


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("negative-proof")
    (root / "testence.json").write_text(
        json.dumps({"project_id": "negative-proof", "controls": CONTROLS}), encoding="utf-8"
    )
    (root / "plan.md").write_text(PLAN, encoding="utf-8")
    (root / "test_widgets.py").write_text(TESTS, encoding="utf-8")
    return root


@pytest.fixture(scope="module")
def runs(project: Path) -> dict[str, Path]:
    green_result, green = _pytest(project, project / "runs")
    assert green_result.returncode == 0, green_result.stdout + green_result.stderr
    negative_result, negative = _pytest(
        project, project / "runs", "--testence-control", "drop-save"
    )
    # The honest test fails with the control active: that is the point of the run.
    assert negative_result.returncode == 1, negative_result.stdout + negative_result.stderr
    return {"green": green, "negative": negative}


def _run_id(run_dir: Path) -> str:
    return LoadedRun.from_events(load_run(run_dir), run_dir).run_id


def test_a_vacuous_test_passes_assurance(runs):
    receipt = evaluate_ci(
        run_dir=runs["green"], run_id=_run_id(runs["green"]), test_exit=0, quality_mode="assurance"
    )

    # The gap ADR-0033 closes: every test is verified, including the one that cannot fail.
    assert receipt["quality"]["exit_code"] == 0, receipt["quality"]


def test_the_negative_run_records_its_control(runs):
    events = load_run(runs["negative"])
    start = next(event for event in events if event["kind"] == "run.start")

    assert start["control"] == {"name": "drop-save", **CONTROLS["drop-save"]}
    green_start = next(event for event in load_run(runs["green"]) if event["kind"] == "run.start")
    assert "control" not in green_start


def test_proven_separates_the_honest_test_from_the_vacuous_one(runs):
    receipt = evaluate_ci(
        run_dir=runs["green"],
        run_id=_run_id(runs["green"]),
        test_exit=0,
        quality_mode="proven",
        negative_runs=[runs["negative"]],
    )

    proof = receipt["quality"]["negative_proof"]
    assert proof["claims"]["widgets.create.persisted"]["outcome"] == "proven"
    assert proof["claims"]["widgets.create.listed"]["outcome"] == "stayed_green"
    assert proof["claims"]["widgets.create.audited"]["outcome"] == "no_control"
    assert proof["claims"]["widgets.create.audited"]["evidence"] == []
    assert proof["counts"]["proven"] == 1
    assert receipt["quality"]["exit_code"] == QUALITY_FAILURE_EXIT
    errors = " ".join(receipt["quality"]["errors"])
    assert "widgets.create.listed (stayed_green)" in errors
    assert "widgets.create.audited (no_control)" in errors
    evidence = proof["claims"]["widgets.create.persisted"]["evidence"][0]
    assert evidence["control"] == "drop-save"
    assert evidence["test"].endswith("test_persisted")


def test_a_run_with_a_control_never_proves_product_behaviour(runs):
    for mode in ("execution", "assurance"):
        receipt = evaluate_ci(
            run_dir=runs["negative"],
            run_id=_run_id(runs["negative"]),
            test_exit=0,
            quality_mode=mode,
        )
        assert any("control 'drop-save'" in error for error in receipt["quality"]["errors"])


def test_proven_needs_negative_runs_made_with_a_control(runs):
    green_id = _run_id(runs["green"])
    with pytest.raises(CIError, match="at least one --negative-run"):
        evaluate_ci(run_dir=runs["green"], run_id=green_id, test_exit=0, quality_mode="proven")
    with pytest.raises(CIError, match="not made with --control"):
        evaluate_ci(
            run_dir=runs["green"],
            run_id=green_id,
            test_exit=0,
            quality_mode="proven",
            negative_runs=[runs["green"]],
        )
    with pytest.raises(CIError, match="only read in quality mode proven"):
        evaluate_ci(
            run_dir=runs["green"],
            run_id=green_id,
            test_exit=0,
            quality_mode="assurance",
            negative_runs=[runs["negative"]],
        )


def test_ci_cli_writes_the_negative_proof_into_the_receipt(runs, tmp_path):
    out = tmp_path / "receipt.json"
    code = main(
        [
            "ci",
            "evaluate",
            str(runs["green"]),
            "--run-id",
            _run_id(runs["green"]),
            "--test-exit",
            "0",
            "--quality-mode",
            "proven",
            "--negative-run",
            str(runs["negative"]),
            "-o",
            str(out),
        ]
    )

    assert code == QUALITY_FAILURE_EXIT
    receipt = json.loads(out.read_text(encoding="utf-8"))
    assert receipt["quality"]["negative_proof"]["counts"]["stayed_green"] == 1
    schema = json.loads(
        (ROOT / "src/testence/contracts/schemas/ci-receipt.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.validate(receipt, schema)


def test_inspect_reports_a_negative_run_and_its_claims(runs, capsys):
    from testence.application import inspect_run

    negative = inspect_run(runs["negative"])
    assert negative["control"]["name"] == "drop-save"
    assert negative["negative_proof"] == {
        "widgets.create.persisted": "proven",
        "widgets.create.listed": "stayed_green",
    }
    green = inspect_run(runs["green"])
    assert green["control"] is None and "negative_proof" not in green

    assert main(["inspect", str(runs["negative"])]) == 0
    out = capsys.readouterr().out
    assert "negative run, control drop-save" in out
    assert "widgets.create.listed: stayed_green" in out


def test_the_report_marks_a_negative_run(runs, tmp_path):
    from testence.report.html import render_report

    page = render_report(runs["negative"], tmp_path / "report.html").read_text(encoding="utf-8")
    assert 'id="negative"' in page
    assert "NEGATIVE RUN" in page
    assert '"control":{"name":"drop-save"' in page.replace(" ", "")


def test_unknown_control_and_reruns_are_usage_errors(project):
    result, _ = _pytest(project, project / "refused", "--testence-control", "no-such")
    assert result.returncode == 4, result.stdout + result.stderr
    assert "unknown control 'no-such'" in result.stdout + result.stderr

    result, _ = _pytest(
        project,
        project / "refused",
        "--testence-control",
        "drop-save",
        "--testence-reruns",
        "1",
    )
    assert result.returncode == 4, result.stdout + result.stderr
    assert "cannot be combined with --testence-reruns" in result.stdout + result.stderr


def test_testence_run_passes_the_control_to_pytest(project, monkeypatch):
    seen: list[list[str]] = []

    def fake_run(argv, **kwargs):
        seen.append(list(argv))
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert main(["run", "--project", str(project), "--control", "drop-save", "--", "-q"]) == 0
    assert seen[0][seen[0].index("--testence-control") + 1] == "drop-save"


# ---------- declarations ----------


def test_declared_controls_are_validated():
    assert declared_controls({}) == {}
    control = resolve_control({"controls": CONTROLS}, "drop-save")
    assert control is not None and control.claims == tuple(CONTROLS["drop-save"]["claims"])
    assert resolve_control({"controls": CONTROLS}, None) is None

    bad = [
        {"controls": []},
        {"controls": {"Drop": CONTROLS["drop-save"]}},
        {"controls": {"drop": {"description": "", "claims": ["a.b"]}}},
        {"controls": {"drop": {"description": "x", "claims": []}}},
        {"controls": {"drop": {"description": "x", "claims": ["A.B"]}}},
        {"controls": {"drop": {"description": "x", "claims": ["a", "a"]}}},
        {"controls": {"drop": {"description": "x", "claims": ["a"], "how": "?"}}},
    ]
    for extra in bad:
        with pytest.raises(ControlError):
            declared_controls(extra)
    with pytest.raises(ControlError, match="declared: drop-save"):
        resolve_control({"controls": CONTROLS}, "other")


# ---------- outcomes the end-to-end run does not reach ----------

_DIGEST = "sha256:" + "a" * 64


def _ledger(
    run_id: str,
    *,
    control: dict | None,
    failed: tuple[str, ...] = (),
    status: str = "passed",
    test_digest: str = "sha256:" + "b" * 64,
    claims: tuple[str, ...] = ("shop.persisted", "shop.listed"),
) -> LoadedRun:
    base = {
        "v": "testence/2",
        "run": run_id,
        "run_id": run_id,
        "project_id": "shop",
        "worker": "controller",
        "test": "tests/test_shop.py::test_shop",
        "case_id": "shop",
        "variant_id": "default",
        "attempt_id": f"attempt-{run_id}",
        "proof_id": "proof-shop",
        "parameters": {},
    }
    declared = [
        {"id": f"assert.{claim}", "claim_id": claim, "oracle": "api", "required": True}
        for claim in claims
    ]
    documents = [
        {
            **{key: base[key] for key in ("v", "run", "run_id", "project_id", "worker")},
            "event_id": "controller:0",
            "seq": 0,
            "kind": "run.start",
            **({"control": control} if control else {}),
        },
        {
            **base,
            "event_id": "controller:1",
            "seq": 1,
            "kind": "test.start",
            "assertions": deepcopy(declared),
            "plan": {"id": "shop", "digest": _DIGEST},
            "plan_digest": _DIGEST,
            "test_digest": test_digest,
            "policy_digest": POLICY_DIGEST,
        },
    ]
    for index, claim in enumerate(claims, start=2):
        documents.append(
            {
                **base,
                "event_id": f"controller:{index}",
                "seq": index,
                "kind": "assertion",
                "assertion_id": f"assert.{claim}",
                "claim_id": claim,
                "oracle_kind": "api",
                "outcome": "failed" if claim in failed else "passed",
                "expected": 1,
                "actual": 0 if claim in failed else 1,
                "source": "tests/test_shop.py:1",
            }
        )
    documents.append(
        {
            **base,
            "event_id": "controller:9",
            "seq": 9,
            "kind": "test.end",
            "status": status,
        }
    )
    return LoadedRun.from_events(documents)


_CONTROL = {"name": "drop-save", "description": "Drops saves", "claims": ["shop.persisted"]}


def _outcome(negative: LoadedRun) -> dict:
    return evaluate_negative_proof(_ledger("green", control=None), [negative])["claims"][
        "shop.persisted"
    ]


def test_a_failure_on_another_claim_is_the_wrong_reason():
    entry = _outcome(_ledger("neg", control=_CONTROL, failed=("shop.listed",)))

    assert entry["outcome"] == "wrong_reason"
    assert entry["evidence"][0]["collateral_claims"] == ["shop.listed"]


def test_collateral_failures_do_not_cancel_the_proof():
    entry = _outcome(_ledger("neg", control=_CONTROL, failed=("shop.persisted", "shop.listed")))

    assert entry["outcome"] == "proven"
    assert entry["evidence"][0]["collateral_claims"] == ["shop.listed"]


def test_a_changed_test_is_stale_evidence():
    entry = _outcome(
        _ledger(
            "neg", control=_CONTROL, failed=("shop.persisted",), test_digest="sha256:" + "c" * 64
        )
    )

    assert entry["outcome"] == "stale"


def test_a_failure_outside_an_assertion_is_inconclusive():
    entry = _outcome(_ledger("neg", control=_CONTROL, status="broken"))

    assert entry["outcome"] == "inconclusive"


def test_proof_from_any_negative_run_wins():
    green = _ledger("green", control=None)
    stayed = _ledger("neg-1", control=_CONTROL)
    proven = _ledger("neg-2", control=_CONTROL, failed=("shop.persisted",))

    result = evaluate_negative_proof(green, [stayed, proven])

    entry = result["claims"]["shop.persisted"]
    assert entry["outcome"] == "proven"
    assert [item["outcome"] for item in entry["evidence"]] == ["stayed_green", "proven"]
    assert result["claims"]["shop.listed"]["outcome"] == "no_control"
    assert result["runs"] == [
        {"run_id": "neg-1", "control": "drop-save"},
        {"run_id": "neg-2", "control": "drop-save"},
    ]


# ---------- ci summary: proof first, the pass count last ----------


def test_summary_of_a_green_run_leads_with_proof(runs, capsys):
    assert main(["ci", "summary", str(runs["green"])]) == 0
    text = capsys.readouterr().out

    assert text.isascii()
    assert "| Required claims backed by verified assertions | 3 of 3 |" in text
    assert "| Tests whose proof is not verified | 0 |" in text
    assert "negative proof" not in text
    assert text.rstrip().endswith("a test can pass without checking anything.</sub>")
    assert "Tests passed: 3 of 3" in text


def test_summary_with_a_negative_run_names_the_unproven_claims(runs):
    from testence.summary import render_summary

    text = render_summary(runs["green"], [runs["negative"]])

    assert "| Claims with negative proof | 1 of 3 |" in text
    assert "- `widgets.create.listed (stayed_green)`" in text
    assert "- `widgets.create.audited (no_control)`" in text


def test_summary_of_a_negative_run_is_not_a_product_verdict(runs):
    from testence.summary import render_summary

    text = render_summary(runs["negative"])

    assert "**Negative run** with control `drop-save`" in text
    assert "| `widgets.create.persisted` | proven |" in text
    assert "| `widgets.create.listed` | stayed_green |" in text
    assert "Required claims backed" not in text


def test_summary_of_a_missing_run_is_an_error(tmp_path, capsys):
    assert main(["ci", "summary", str(tmp_path / "nope")]) == 2
    assert "ci summary failed" in capsys.readouterr().err


def test_summary_counts_a_claim_only_when_its_test_is_verified():
    from testence.summary import summarize

    text = summarize(_ledger("red", control=None, failed=("shop.persisted",)), [])

    assert "| Required claims backed by verified assertions | 0 of 2 |" in text
    assert "| Tests whose proof is not verified | 1 |" in text
    assert "- `tests/test_shop.py::test_shop (violated)`" in text
    assert summarize(_ledger("green", control=None), []).count("2 of 2") == 1
