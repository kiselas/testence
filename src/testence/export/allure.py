"""Allure results exporter — the directory format, not the SDK (ADR-0013).

Allure's *results* format is a documented directory of JSON files, and ``allurectl``
uploads such a directory without caring what produced it. That decoupling is the
whole point of this module: a team keeps its TestOps launches, custom-field filters
and scheduled runs while the suite underneath is replaced. The migration touches the
test command, never the pipeline.

What is deliberately *not* reproduced: Allure's push model. There are no
``allure.step`` calls anywhere in Testence — steps come from the DSL's intent
sentences, so the step tree in TestOps is a projection of the ledger and cannot
drift from it.

Determinism is a requirement, not a nicety: identifiers derive from the run id and
the test nodeid by hashing, so exporting the same ledger twice produces byte-identical
files and a golden test can pin the mapping.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from pathlib import Path
from typing import Any

from ._model import PACK_FILES, LoadedRun, Step, Test, epoch_ms

name = "allure"

# Fixed namespace so uuids are a pure function of (run, test) — see module docstring.
_NAMESPACE = uuid.UUID("6f2f2a5e-6c1a-4b3e-9a1e-2b6f6f9c1d21")

# Allure statuses: "passed" | "failed" | "broken" | "skipped". The ledger records
# pass/fail only; failed-vs-broken is a distinction the runner does not make, and
# inventing one here would be a second source of truth.
_STATUS = {"pass": "passed", "passed": "passed", "fail": "failed", "failed": "failed"}

_MIME = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".json": "application/json",
    # .jsonl has no registered type TestOps renders; text/plain keeps it readable
    # in the browser, which is the point of attaching it at all.
    ".jsonl": "text/plain",
    ".png": "image/png",
}


def export(run: LoadedRun, out_dir: Path) -> list[Path]:
    written: list[Path] = []
    for test in run.tests:
        test_uuid = _uuid_for(run.run_id, test.nodeid)
        attachments, files = _attachments(run, test, test_uuid, out_dir)
        written.extend(files)
        result = _result(run, test, test_uuid, attachments)
        written.append(_write_json(out_dir / f"{test_uuid}-result.json", result))
    written.append(_write_environment(run, out_dir))
    return written


def _result(run: LoadedRun, test: Test, test_uuid: str, attachments: list[dict]) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "uuid": test_uuid,
        # Stable across runs on purpose: this is what makes TestOps history a
        # history of one test rather than of one execution.
        "historyId": hashlib.sha256(test.nodeid.encode("utf-8")).hexdigest(),
        "name": test.name,
        "fullName": test.nodeid,
        "status": _STATUS.get(test.status, "broken"),
        "stage": "finished",
        "labels": _labels(test),
        "steps": [_step(step) for step in test.steps],
    }
    _put_window(doc, test.start, test.stop)
    message = test.error or _first_step_error(test.steps)
    if test.failed and message:
        doc["statusDetails"] = {"message": message, "trace": message}
    if attachments:
        doc["attachments"] = attachments
    return doc


def _labels(test: Test) -> list[dict[str, str]]:
    """Markers become tags verbatim.

    Verbatim matters: the incumbent suite's marker taxonomy is what dashboards,
    filters and scheduled runs key on, so renaming would silently empty someone's
    saved filter.
    """
    labels = [{"name": "framework", "value": "testence"}]
    if test.file:
        labels.append({"name": "suite", "value": Path(test.file).stem})
    labels.extend({"name": "tag", "value": marker} for marker in test.markers)
    return labels


def _step(step: Step) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "name": step.intent or step.step,
        "status": "failed" if step.failed else "passed",
        "stage": "finished",
    }
    if step.target:
        doc["parameters"] = [{"name": "target", "value": step.target}]
    _put_window(doc, step.start, step.stop)
    if step.error:
        doc["statusDetails"] = {"message": step.error}
    if step.substeps:
        doc["steps"] = [_step(child) for child in step.substeps]
    return doc


def _attachments(
    run: LoadedRun, test: Test, test_uuid: str, out_dir: Path
) -> tuple[list[dict[str, str]], list[Path]]:
    """Copy the evidence pack in as attachments.

    Budgets were already applied when the pack was assembled, so nothing is
    truncated twice; ``full-*`` originals stay in the run directory for an agent
    that wants them, because a reporting tool is not the place to ship 8 000 tokens
    of ARIA to a human.
    """
    attachments: list[dict[str, str]] = []
    written: list[Path] = []
    for filename in PACK_FILES:
        source = run.pack_path(test, filename)
        if source is None:
            continue
        suffix = source.suffix or ".txt"
        target_name = f"{_uuid_for(test_uuid, filename)}-attachment{suffix}"
        target = out_dir / target_name
        shutil.copyfile(source, target)
        written.append(target)
        attachments.append(
            {
                "name": filename,
                "source": target_name,
                "type": _MIME.get(suffix, "text/plain"),
            }
        )
    if test.oracles:
        target_name = f"{_uuid_for(test_uuid, 'oracles')}-attachment.json"
        written.append(_write_json(out_dir / target_name, test.oracles))
        attachments.append(
            {"name": "oracles.json", "source": target_name, "type": "application/json"}
        )
    return attachments, written


def _write_environment(run: LoadedRun, out_dir: Path) -> Path:
    """The run fingerprint as Allure sees the environment.

    Includes the product-side stamp when the ledger carries one: "which build was
    this red against" is the question that separates a real bug from a stale environment,
    and answering it from the report costs one line here.
    """
    values: dict[str, str] = {
        "testence.version": run.testence_version,
        "testence.run": run.run_id,
    }
    for key, value in (run.fingerprint or {}).items():
        values[f"environment.{key}"] = "" if value is None else str(value)
    lines = [f"{key}={_escape(value)}" for key, value in sorted(values.items()) if value != ""]
    target = out_dir / "environment.properties"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return target


def _first_step_error(steps: list[Step]) -> str | None:
    for step in steps:
        if step.error:
            return step.error
        nested = _first_step_error(step.substeps)
        if nested:
            return nested
    return None


def _put_window(doc: dict[str, Any], start: Any, stop: Any) -> None:
    start_ms, stop_ms = epoch_ms(start), epoch_ms(stop)
    if start_ms is not None:
        doc["start"] = start_ms
    if stop_ms is not None:
        doc["stop"] = stop_ms


def _uuid_for(*parts: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, "|".join(parts)))


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", " ").replace("\r", " ")


def _write_json(target: Path, doc: Any) -> Path:
    # Trailing newline on purpose: goldens are reviewed as diffs, and a missing one
    # adds "\ No newline at end of file" noise to every single change.
    target.write_text(
        json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return target
