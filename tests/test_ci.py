from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from testence.ci import (
    DELIVERY_FAILURE_EXIT,
    QUALITY_FAILURE_EXIT,
    CIError,
    evaluate_ci,
    run_delivery,
)
from testence.cli import main
from testence.evidence import EvidenceWriter
from testence.export import export_run


def _run(tmp_path: Path, *, status="passed") -> Path:
    writer = EvidenceWriter(tmp_path, run_id="r-ci-1", worker="", project_id="shop")
    writer.emit("run.start", testence="test")
    writer.emit("test.start", test="tests/test_ci.py::test_case")
    writer.emit("test.end", test="tests/test_ci.py::test_case", status=status, duration_ms=1)
    writer.emit(
        "run.end",
        run_status="passed" if status == "passed" else "failed",
        exit_code=0 if status == "passed" else 1,
        duration_ms=2,
    )
    writer.close()
    return writer.run_dir


def _artifacts(run_dir: Path, target: Path) -> Path:
    export_run(run_dir, "allure", target)
    return target


def test_ci_keeps_test_quality_and_delivery_outcomes_separate(tmp_path):
    run_dir = _run(tmp_path / "runs")

    failed_test = evaluate_ci(
        run_dir=run_dir,
        run_id="r-ci-1",
        test_exit=1,
        quality_mode="execution",
    )
    failed_proof = evaluate_ci(
        run_dir=run_dir,
        run_id="r-ci-1",
        test_exit=0,
        quality_mode="assurance",
    )

    assert failed_test["test"]["exit_code"] == failed_test["final_exit"] == 1
    assert failed_test["quality"]["exit_code"] == 0
    assert failed_proof["test"]["exit_code"] == 0
    assert failed_proof["quality"]["exit_code"] == QUALITY_FAILURE_EXIT
    assert failed_proof["final_exit"] == QUALITY_FAILURE_EXIT


def test_ci_checks_ctrf_and_junit_against_same_inventory(tmp_path):
    run_dir = _run(tmp_path / "runs")
    ctrf = export_run(run_dir, "ctrf", tmp_path / "ctrf")[0]
    junit = tmp_path / "junit.xml"
    junit.write_text('<testsuite tests="1" failures="0" errors="0" skipped="0"/>')

    receipt = evaluate_ci(
        run_dir=run_dir,
        run_id="r-ci-1",
        test_exit=0,
        quality_mode="execution",
        ctrf_path=ctrf,
        junit_path=junit,
    )

    assert receipt["quality"]["exit_code"] == 0
    junit.write_text('<testsuite tests="2" failures="0" errors="0" skipped="0"/>')
    mismatch = evaluate_ci(
        run_dir=run_dir,
        run_id="r-ci-1",
        test_exit=0,
        quality_mode="execution",
        ctrf_path=ctrf,
        junit_path=junit,
    )
    assert mismatch["quality"]["exit_code"] == QUALITY_FAILURE_EXIT
    assert "JUnit inventory mismatch" in mismatch["quality"]["errors"][0]


def test_delivery_retries_once_and_reuses_successful_receipt(tmp_path):
    run_dir = _run(tmp_path / "runs")
    artifacts = _artifacts(run_dir, tmp_path / "allure-results")
    counter = tmp_path / "counter.txt"
    script = tmp_path / "deliver.py"
    script.write_text(
        "from pathlib import Path\n"
        f"p=Path({str(counter)!r})\n"
        "n=int(p.read_text())+1 if p.exists() else 1\n"
        "p.write_text(str(n))\n"
        "raise SystemExit(0 if n >= 2 else 7)\n",
        encoding="utf-8",
    )
    receipt = tmp_path / "delivery.json"

    first = run_delivery(
        run_dir=run_dir,
        run_id="r-ci-1",
        project_id="shop",
        launch_id="launch-7",
        job_run_id="job-9",
        artifact_dir=artifacts,
        receipt_path=receipt,
        command=[sys.executable, str(script)],
        retries=2,
        timeout_s=5,
    )
    second = run_delivery(
        run_dir=run_dir,
        run_id="r-ci-1",
        project_id="shop",
        launch_id="launch-7",
        job_run_id="job-9",
        artifact_dir=artifacts,
        receipt_path=receipt,
        command=[sys.executable, str(script)],
        retries=2,
        timeout_s=5,
    )

    assert first.exit_code == second.exit_code == 0
    assert [item["exit_code"] for item in first.receipt["attempts"]] == [7, 0]
    assert counter.read_text() == "2"
    assert second.receipt == first.receipt


def test_delivery_timeout_and_preflight_fail_closed(tmp_path):
    run_dir = _run(tmp_path / "runs")
    artifacts = _artifacts(run_dir, tmp_path / "allure-results")
    result = run_delivery(
        run_dir=run_dir,
        run_id="r-ci-1",
        project_id="shop",
        launch_id="launch-7",
        job_run_id="job-9",
        artifact_dir=artifacts,
        receipt_path=tmp_path / "timeout.json",
        command=[sys.executable, "-c", "import time; time.sleep(1)"],
        retries=1,
        timeout_s=0.05,
    )
    assert result.exit_code == DELIVERY_FAILURE_EXIT
    assert [item["outcome"] for item in result.receipt["attempts"]] == [
        "timeout",
        "timeout",
    ]

    with pytest.raises(CIError, match="project mismatch"):
        run_delivery(
            run_dir=run_dir,
            run_id="r-ci-1",
            project_id="other",
            launch_id="launch-7",
            job_run_id="job-9",
            artifact_dir=artifacts,
            receipt_path=tmp_path / "wrong.json",
            command=[sys.executable, "-c", "pass"],
        )

    result_file = next(artifacts.glob("*-result.json"))
    document = json.loads(result_file.read_text(encoding="utf-8"))
    document["attachments"] = [{"name": "missing", "source": "missing.txt", "type": "text/plain"}]
    result_file.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(CIError, match="missing attachment"):
        run_delivery(
            run_dir=run_dir,
            run_id="r-ci-1",
            project_id="shop",
            launch_id="launch-7",
            job_run_id="job-9",
            artifact_dir=artifacts,
            receipt_path=tmp_path / "missing.json",
            command=[sys.executable, "-c", "pass"],
        )


def test_ci_cli_writes_receipt_and_returns_final_exit(tmp_path, capsys):
    run_dir = _run(tmp_path / "runs")
    receipt = tmp_path / "ci.json"

    exit_code = main(
        [
            "ci",
            "evaluate",
            str(run_dir),
            "--run-id",
            "r-ci-1",
            "--test-exit",
            "0",
            "--quality-mode",
            "execution",
            "-o",
            str(receipt),
            "--json",
        ]
    )

    assert exit_code == 0
    assert json.loads(receipt.read_text(encoding="utf-8"))["final_exit"] == 0
    assert json.loads(capsys.readouterr().out)["schema"] == "testence/ci-receipt/1"
