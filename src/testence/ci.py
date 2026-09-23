"""CI outcome and idempotent delivery receipts."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from testence.contracts.versions import CI_RECEIPT_SCHEMA, DELIVERY_RECEIPT_SCHEMA
from testence.export import LoadedRun
from testence.managed_paths import is_shell_metadata
from testence.metrics import load_run

QUALITY_FAILURE_EXIT = 10
DELIVERY_FAILURE_EXIT = 11


class CIError(ValueError):
    pass


@dataclass(frozen=True)
class DeliveryResult:
    exit_code: int
    receipt: dict[str, Any]


def _load_run(run_dir: Path | str, *, run_id: str) -> LoadedRun:
    root = Path(run_dir)
    try:
        run = LoadedRun.from_events(load_run(root), root)
    except (OSError, ValueError) as exc:
        raise CIError(f"cannot read run {root}: {exc}") from exc
    if run.run_id != run_id:
        raise CIError(f"run identity mismatch: expected {run_id!r}, observed {run.run_id!r}")
    return run


def _atomic_json(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def _artifact_digest(artifact_dir: Path) -> str:
    if not artifact_dir.is_dir():
        raise CIError(f"delivery artifact directory does not exist: {artifact_dir}")
    # A file manager's .DS_Store/Thumbs.db is not delivered content. Counting it would
    # change the idempotency identity after someone merely opened the folder.
    files = sorted(
        path for path in artifact_dir.iterdir() if path.is_file() and not is_shell_metadata(path)
    )
    result_files = [path for path in files if path.name.endswith("-result.json")]
    if not result_files:
        raise CIError("delivery artifact directory has no Allure result files")
    for result_path in result_files:
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CIError(f"invalid Allure result {result_path.name}: {exc}") from exc
        for attachment in result.get("attachments") or ():
            source = attachment.get("source") if isinstance(attachment, dict) else None
            if not isinstance(source, str) or not (artifact_dir / source).is_file():
                raise CIError(f"Allure result {result_path.name} has a missing attachment")
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return "sha256:" + digest.hexdigest()


def run_delivery(
    *,
    run_dir: Path | str,
    run_id: str,
    project_id: str,
    launch_id: str,
    job_run_id: str,
    artifact_dir: Path | str,
    receipt_path: Path | str,
    command: list[str],
    retries: int = 2,
    timeout_s: float = 60.0,
) -> DeliveryResult:
    run = _load_run(run_dir, run_id=run_id)
    if run.project_id != project_id:
        raise CIError(
            f"delivery project mismatch: expected {project_id!r}, observed {run.project_id!r}"
        )
    if run.run_status == "incomplete" or run.integrity_errors:
        raise CIError("incomplete or damaged run cannot be delivered")
    for name, value in (("launch_id", launch_id), ("job_run_id", job_run_id)):
        if not value.strip():
            raise CIError(f"delivery {name} must not be empty")
    if not command:
        raise CIError("delivery command must not be empty")
    if retries < 0 or retries > 5:
        raise CIError("delivery retries must be between 0 and 5")
    if timeout_s <= 0:
        raise CIError("delivery timeout must be positive")

    artifacts_digest = _artifact_digest(Path(artifact_dir))
    identity = {
        "run_id": run_id,
        "project_id": project_id,
        "launch_id": launch_id,
        "job_run_id": job_run_id,
        "artifacts_digest": artifacts_digest,
    }
    idempotency_key = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
    )
    receipt_path = Path(receipt_path)
    if receipt_path.is_file():
        try:
            previous = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CIError(f"invalid existing delivery receipt: {exc}") from exc
        if previous.get("idempotency_key") != idempotency_key:
            raise CIError("existing delivery receipt belongs to a different delivery identity")
        if previous.get("outcome") == "delivered":
            return DeliveryResult(0, previous)

    attempts: list[dict[str, Any]] = []
    environment = dict(os.environ)
    environment.update(
        TESTENCE_RUN_ID=run_id,
        TESTENCE_PROJECT_ID=project_id,
        ALLURE_LAUNCH_ID=launch_id,
        ALLURE_JOB_RUN_ID=job_run_id,
        ALLURE_RESULTS=str(Path(artifact_dir).resolve()),
    )
    for number in range(1, retries + 2):
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                command,
                env=environment,
                capture_output=True,
                check=False,
                timeout=timeout_s,
            )
            outcome = "delivered" if completed.returncode == 0 else "failed"
            exit_code: int | None = int(completed.returncode)
        except subprocess.TimeoutExpired:
            outcome = "timeout"
            exit_code = None
        except OSError:
            outcome = "error"
            exit_code = None
        attempts.append(
            {
                "number": number,
                "outcome": outcome,
                "exit_code": exit_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            }
        )
        if outcome == "delivered":
            break

    delivered = attempts[-1]["outcome"] == "delivered"
    receipt: dict[str, Any] = {
        "schema": DELIVERY_RECEIPT_SCHEMA,
        **identity,
        "idempotency_key": idempotency_key,
        "outcome": "delivered" if delivered else "failed",
        "attempts": attempts,
    }
    _atomic_json(receipt_path, receipt)
    return DeliveryResult(0 if delivered else DELIVERY_FAILURE_EXIT, receipt)


def _artifact_checks(
    run: LoadedRun, *, ctrf_path: Path | None, junit_path: Path | None
) -> list[str]:
    errors: list[str] = []
    if ctrf_path is not None:
        try:
            ctrf = json.loads(ctrf_path.read_text(encoding="utf-8"))["results"]["summary"]
            expected = {
                "tests": len(run.tests),
                "passed": run.passed,
                "failed": run.failed,
                "pending": run.pending,
                "skipped": run.skipped,
                "other": run.other,
            }
            observed = {key: int(ctrf[key]) for key in expected}
            if observed != expected:
                errors.append(f"CTRF inventory mismatch: expected {expected}, observed {observed}")
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            errors.append(f"cannot validate CTRF: {exc}")
    if junit_path is not None:
        try:
            root = ET.parse(junit_path).getroot()
            suite = root if root.tag == "testsuite" else root.find("testsuite")
            if suite is None:
                raise ValueError("no testsuite element")
            if int(suite.attrib["tests"]) != len(run.tests):
                errors.append(
                    f"JUnit inventory mismatch: expected {len(run.tests)}, "
                    f"observed {suite.attrib['tests']}"
                )
        except (OSError, ValueError, KeyError, ET.ParseError) as exc:
            errors.append(f"cannot validate JUnit: {exc}")
    return errors


def evaluate_ci(
    *,
    run_dir: Path | str,
    run_id: str,
    test_exit: int,
    quality_mode: str = "assurance",
    delivery_receipt: Path | str | None = None,
    ctrf_path: Path | str | None = None,
    junit_path: Path | str | None = None,
    allow_empty: bool = False,
) -> dict[str, Any]:
    run = _load_run(run_dir, run_id=run_id)
    if quality_mode not in {"execution", "assurance"}:
        raise CIError("quality mode must be execution or assurance")
    quality_errors: list[str] = []
    if run.run_status != "passed":
        quality_errors.append(f"run status is {run.run_status!r}")
    if run.integrity_errors:
        quality_errors.append("run has integrity errors")
    if not run.tests and not allow_empty:
        quality_errors.append("run contains no tests")
    disallowed = [test.nodeid for test in run.tests if test.status not in {"passed", "skipped"}]
    if disallowed:
        quality_errors.append("non-passing execution: " + ", ".join(disallowed))
    if quality_mode == "assurance":
        unverified = [test.nodeid for test in run.tests if test.assurance != "verified"]
        if unverified:
            quality_errors.append("unverified proof: " + ", ".join(unverified))
    quality_errors.extend(
        _artifact_checks(
            run,
            ctrf_path=Path(ctrf_path) if ctrf_path is not None else None,
            junit_path=Path(junit_path) if junit_path is not None else None,
        )
    )
    quality_exit = QUALITY_FAILURE_EXIT if quality_errors else 0

    delivery: dict[str, Any] = {"outcome": "not_requested", "exit_code": 0}
    if delivery_receipt is not None:
        try:
            delivery_doc = json.loads(Path(delivery_receipt).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CIError(f"cannot read delivery receipt: {exc}") from exc
        if delivery_doc.get("schema") != DELIVERY_RECEIPT_SCHEMA:
            raise CIError("unsupported delivery receipt schema")
        if delivery_doc.get("run_id") != run_id:
            raise CIError("delivery receipt run_id mismatch")
        delivered = delivery_doc.get("outcome") == "delivered"
        delivery = {
            "outcome": str(delivery_doc.get("outcome") or "unknown"),
            "exit_code": 0 if delivered else DELIVERY_FAILURE_EXIT,
            "receipt": str(delivery_receipt),
        }

    test_result_exit = int(test_exit)
    final_exit = (
        test_result_exit
        if test_result_exit != 0
        else quality_exit
        if quality_exit != 0
        else int(delivery["exit_code"])
    )
    return {
        "schema": CI_RECEIPT_SCHEMA,
        "run_id": run.run_id,
        "project_id": run.project_id,
        "run_status": run.run_status,
        "test": {"exit_code": test_result_exit},
        "quality": {
            "mode": quality_mode,
            "exit_code": quality_exit,
            "errors": quality_errors,
        },
        "delivery": delivery,
        "final_exit": final_exit,
    }


def write_ci_receipt(path: Path | str, document: dict[str, Any]) -> None:
    _atomic_json(Path(path), document)
