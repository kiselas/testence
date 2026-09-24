"""Allure results exporter — the directory format, not the SDK (ADR-0013).

Allure's *results* format is a documented directory of JSON files, and ``allurectl``
uploads such a directory without caring what produced it. That decoupling is the
whole point of this module: a team keeps its TestOps launches, custom-field filters
and scheduled runs while the suite underneath moves to Testence. With the default
``allure-pytest`` naming, results land on the test cases and history allure-pytest
created, and ``@allure.*`` metadata still reads.

What is deliberately *not* reproduced: Allure's push model. There are no
``allure.step`` calls anywhere in Testence — steps come from the DSL's intent
sentences, so the step tree in TestOps is a projection of the ledger and cannot
drift from it.

Determinism is a requirement, not a nicety: identifiers derive from the ledger by
hashing, so exporting the same ledger twice produces byte-identical files and a golden
test can pin the mapping.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from contextlib import suppress
from pathlib import Path
from typing import Any

from testence.allure_compat import IGNORED_TAG_MARKS
from testence.evidence.sanitize import REDACTED

from ._model import PACK_FILES, FixturePhase, LoadedRun, Step, Test, epoch_ms

name = "allure"

# Fixed namespace so uuids are a pure function of (run, test) — see module docstring.
_NAMESPACE = uuid.UUID("6f2f2a5e-6c1a-4b3e-9a1e-2b6f6f9c1d21")

# Allure statuses: "passed" | "failed" | "broken" | "skipped". The lifecycle
# ledger owns that distinction; this table only translates legacy spellings and
# the two Testence states that Allure cannot represent directly.
_STATUS = {
    "pass": "passed",
    "passed": "passed",
    "fail": "failed",
    "failed": "failed",
    "broken": "broken",
    "skipped": "skipped",
    "aborted": "broken",
    "not_run": "skipped",
}

_MIME = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".json": "application/json",
    # .jsonl has no registered type TestOps renders; text/plain keeps it readable
    # in the browser, which is the point of attaching it at all.
    ".jsonl": "text/plain",
    ".png": "image/png",
    ".zip": "application/zip",
    ".webm": "video/webm",
}


def export(run: LoadedRun, out_dir: Path) -> list[Path]:
    written: list[Path] = []
    for test in run.tests:
        written.extend(write_test(run, test, out_dir))
    written.extend(write_run_files(run, out_dir))
    return written


def write_test(run: LoadedRun, test: Test, out_dir: Path) -> list[Path]:
    """One test's attachments, fixture container and result, in that order.

    The result comes last because it references the others: a watcher that uploads
    files as they appear must never see a result whose attachment is not there yet.
    """
    test_uuid = _uuid_for(
        run.run_id,
        test.case_id or test.nodeid,
        test.variant_id,
        test.attempt_id or "legacy",
    )
    attachments, written = _attachments(run, test, test_uuid, out_dir)
    if test.fixtures:
        container = _container(test, test_uuid)
        written.append(_write_json(out_dir / f"{container['uuid']}-container.json", container))
    result = _result(run, test, test_uuid, attachments)
    written.append(_write_json(out_dir / f"{test_uuid}-result.json", result))
    return written


def write_run_files(run: LoadedRun, out_dir: Path) -> list[Path]:
    """``environment.properties`` and ``categories.json``: known once the run ends."""
    return [
        _write_environment(run, out_dir),
        _write_json(out_dir / "categories.json", _CATEGORIES),
    ]


#: How Allure groups failures. Testence's own classes, so a product disagreement is
#: never counted together with a flaky environment.
_CATEGORIES = [
    {
        "name": "Product disagreed with the test (oracle)",
        "matchedStatuses": ["failed"],
        "messageRegex": ".*(OracleFailed|UI and API disagree).*",
    },
    {"name": "Assertion failed", "matchedStatuses": ["failed"]},
    {
        "name": "Environment or browser (infrastructure)",
        "matchedStatuses": ["broken"],
        "messageRegex": ".*(Timeout|playwright|Target .*closed|net::|ECONNREFUSED).*",
    },
    {"name": "Test code error", "matchedStatuses": ["broken"]},
]
_BROKEN_KINDS = frozenset({"infrastructure", "test_code"})


def _identity(run: LoadedRun, test: Test) -> tuple[str, str, str]:
    """``fullName``, ``testCaseId`` and ``historyId`` of one result.

    ``allure-pytest`` naming (default) reproduces allure-pytest's identities, so a suite
    moved onto Testence keeps its TestOps cases and history. An explicit PlanSpec case
    keeps its Testence identity even then: that id survives a rename, allure-pytest's
    does not (ADR-0019). ``nodeid`` naming is the 0.1.0a1 behaviour.
    """
    compat = run.allure_naming == "allure-pytest" and bool(test.allure.get("full_name"))
    full_name = str(test.allure["full_name"]) if compat else test.nodeid
    if compat and not test.plan_id:
        return full_name, str(test.allure["test_case_id"]), str(test.allure["history_id"])
    project = test.project_id or run.project_id
    case = test.case_id or test.nodeid
    test_case_id = hashlib.sha256("|".join((project, case)).encode("utf-8")).hexdigest()
    # Stable across runs on purpose: this is what makes TestOps history a history of
    # one test rather than of one execution.
    history = hashlib.sha256("|".join((project, case, test.variant_id)).encode("utf-8"))
    return full_name, test_case_id, history.hexdigest()


def _result(run: LoadedRun, test: Test, test_uuid: str, attachments: list[dict]) -> dict[str, Any]:
    full_name, test_case_id, history_id = _identity(run, test)
    doc: dict[str, Any] = {
        "uuid": test_uuid,
        "testCaseId": test_case_id,
        "historyId": history_id,
        "name": _name(test),
        "fullName": full_name,
        "status": _status(test),
        "stage": "finished",
        "labels": _labels(test, run),
        "parameters": _parameters(run, test),
        "steps": [_step(step) for step in test.steps],
        "links": _links(test),
    }
    if test.allure.get("title_path"):
        doc["titlePath"] = [str(part) for part in test.allure["title_path"]]
    description = _description(test)
    if description:
        doc["description"] = description
    if test.allure.get("description_html"):
        doc["descriptionHtml"] = str(test.allure["description_html"])
    _put_window(doc, test.start, test.stop)
    message = test.error or _first_step_error(test.steps)
    if test.failed and message:
        doc["statusDetails"] = {"message": message, "trace": test.error_trace or message}
    if attachments:
        doc["attachments"] = attachments
        screenshot = next((item for item in attachments if item["name"] == "screenshot.png"), None)
        if screenshot is not None:
            _attach_to_failed_step(doc["steps"], screenshot)
    return doc


def _status(test: Test) -> str:
    """``failed`` when the product disagreed, ``broken`` when the test could not decide."""
    status = _STATUS.get(test.status, "broken")
    if status == "failed" and test.error_kind in _BROKEN_KINDS:
        return "broken"
    return status


def _name(test: Test) -> str:
    """Explicit title, then the PlanSpec scenario, then the pytest name."""
    scenario = test.allure.get("plan_scenario") or {}
    return str(test.allure.get("title") or scenario.get("title") or test.name)


def _description(test: Test) -> str | None:
    """Explicit description, then the PlanSpec claims, then the docstring."""
    if test.allure.get("description"):
        return str(test.allure["description"])
    scenario = test.allure.get("plan_scenario") or {}
    claims = [item for item in scenario.get("claims", ()) if isinstance(item, dict)]
    if claims:
        lines = ["Claims verified by this test:", ""]
        lines.extend(f"- **{item.get('id')}**: {item.get('statement')}" for item in claims)
        if scenario.get("plan"):
            lines.extend(["", f"Plan: `{scenario['plan']}`"])
        return "\n".join(lines)
    return str(test.allure["docstring"]) if test.allure.get("docstring") else None


def _parameters(run: LoadedRun, test: Test) -> list[dict[str, str]]:
    """Readable, redacted values; ``digest`` keeps the 0.1.0a1 shape."""
    displayed = test.allure.get("parameters")
    if run.allure_parameters == "values" and isinstance(displayed, list):
        result = []
        for item in displayed:
            if not isinstance(item, dict) or "name" not in item:
                continue
            value = str(item.get("value", ""))
            entry = {"name": str(item["name"]), "value": value}
            if REDACTED in value:
                entry["mode"] = "masked"
            result.append(entry)
        return result
    return [
        {"name": "variant_id", "value": test.variant_id},
        *[
            {"name": name, "value": f"sha256:{digest}"}
            for name, digest in sorted(test.parameters.items())
        ],
    ]


def _attach_to_failed_step(steps: list[dict[str, Any]], attachment: dict[str, str]) -> bool:
    """Put the failure screenshot on the innermost failed step as well."""
    for step in steps:
        if step.get("status") != "failed":
            continue
        if not _attach_to_failed_step(step.get("steps", []), attachment):
            step["attachments"] = [attachment]
        return True
    return False


def _labels(test: Test, run: LoadedRun | None = None) -> list[dict[str, str]]:
    """Markers become tags verbatim.

    Verbatim matters: the incumbent suite's marker taxonomy is what dashboards,
    filters and scheduled runs key on, so renaming would silently empty someone's
    saved filter.
    """
    labels = [{"name": "framework", "value": "testence"}]
    for name, value in (
        ("project", test.project_id),
        ("case_id", test.case_id),
        ("attempt_id", test.attempt_id),
        ("proof_id", test.proof_id),
        ("assurance", test.assurance),
        ("ALLURE_ID", test.allure_id),
        ("owner", test.owner),
        ("risk", test.risk),
    ):
        if value:
            labels.append({"name": name, "value": value})
    suite = test.allure.get("suite") if isinstance(test.allure.get("suite"), dict) else None
    if suite is not None:
        # The allure-pytest hierarchy: TestOps and Allure build their trees from it.
        for name in ("parentSuite", "suite", "subSuite"):
            if suite.get(name):
                labels.append({"name": name, "value": str(suite[name])})
        for name, key in (("package", "package"), ("testClass", "test_class")):
            if test.allure.get(key):
                labels.append({"name": name, "value": str(test.allure[key])})
        if test.allure.get("test_method"):
            labels.append({"name": "testMethod", "value": str(test.allure["test_method"])})
        labels.append({"name": "language", "value": "python"})
    elif test.file:
        labels.append({"name": "suite", "value": Path(test.file).stem})
    if test.variant_id and test.variant_id != "default":
        labels.append({"name": "variant_id", "value": test.variant_id})
    worker = str((run.fingerprint if run is not None else {}).get("worker") or "")
    if worker:
        labels.append({"name": "thread", "value": worker})
    tags = test.allure.get("tags")
    names = (
        [str(tag) for tag in tags]
        if isinstance(tags, list)
        else [marker for marker in test.markers if marker not in IGNORED_TAG_MARKS]
    )
    labels.extend({"name": "tag", "value": name} for name in names)
    labels.extend({"name": "requirement", "value": item["id"]} for item in test.requirements)
    labels.extend({"name": "issue", "value": item["id"]} for item in test.issues)
    # Case ids in other test-management systems, one label per id (``tms=`` marker).
    labels.extend(
        {"name": system, "value": case} for system, ids in sorted(test.tms.items()) for case in ids
    )
    # @allure.feature/story/severity/id/label and the testence marker's labels.
    labels.extend(
        {"name": str(item["name"]), "value": str(item["value"])}
        for item in test.allure.get("labels", ())
        if isinstance(item, dict) and item.get("name") and item.get("value") is not None
    )
    return labels


def _links(test: Test) -> list[dict[str, str]]:
    links = [
        {"name": item["id"], "url": item["url"], "type": kind}
        for kind, values in (("tms", test.requirements), ("issue", test.issues))
        for item in values
        if item.get("url")
    ]
    links.extend(
        {
            "name": str(item.get("name") or item["url"]),
            "url": str(item["url"]),
            "type": str(item.get("type") or "link"),
        }
        for item in test.allure.get("links", ())
        if isinstance(item, dict) and item.get("url")
    )
    return links


def _container(test: Test, test_uuid: str) -> dict[str, Any]:
    before = [_fixture(item) for item in test.fixtures if item.name == "pytest setup"]
    after = [_fixture(item) for item in test.fixtures if item.name == "pytest teardown"]
    return {
        "uuid": _uuid_for(test_uuid, "fixtures"),
        "children": [test_uuid],
        "befores": before,
        "afters": after,
    }


def _fixture(fixture: FixturePhase) -> dict[str, Any]:
    document: dict[str, Any] = {
        "name": fixture.name,
        "status": _STATUS.get(fixture.status, "broken"),
        "stage": "finished",
    }
    _put_window(document, fixture.start, fixture.stop)
    if fixture.error:
        document["statusDetails"] = {"message": fixture.error, "trace": fixture.error}
    return document


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
        content = run.attachment_bytes(test, filename)
        if content is None:
            continue
        suffix = Path(filename).suffix or ".txt"
        target_name = f"{_uuid_for(test_uuid, filename)}-attachment{suffix}"
        target = _write_bytes(out_dir / target_name, content)
        written.append(target)
        attachments.append(
            {
                "name": filename,
                "source": target_name,
                "type": _MIME.get(suffix, "text/plain"),
            }
        )
    final = run.run_file(test.screenshot) if run.ships("screenshot.png") else None
    if final is not None:
        target_name = f"{_uuid_for(test_uuid, 'final-screenshot')}-attachment.png"
        target = _write_bytes(out_dir / target_name, final.read_bytes())
        written.append(target)
        attachments.append({"name": "screenshot.png", "source": target_name, "type": "image/png"})
    # Trace and video are raw by nature (DOM snapshots, network, pixels); the run
    # opted into them, and only a full export ships them.
    if run.attachments == "full":
        for recording in test.recordings:
            source = run.run_file(recording["path"])
            if source is None:
                continue
            suffix = source.suffix
            target_name = f"{_uuid_for(test_uuid, recording['path'])}-attachment{suffix}"
            written.append(_write_bytes(out_dir / target_name, source.read_bytes()))
            attachments.append(
                {
                    "name": source.name,
                    "source": target_name,
                    "type": _MIME.get(suffix, "application/octet-stream"),
                }
            )
    if test.oracles and run.attachments != "none":
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
        "testence.run_status": run.run_status,
    }
    if run.testplan_unresolved:
        values["testence.testplan_unresolved"] = str(len(run.testplan_unresolved))
    if run.integrity_errors:
        values["testence.integrity_errors"] = json.dumps(
            run.integrity_errors, ensure_ascii=False, separators=(",", ":")
        )
    for key, value in (run.fingerprint or {}).items():
        values[f"environment.{key}"] = "" if value is None else str(value)
    lines = [f"{key}={_escape(value)}" for key, value in sorted(values.items()) if value != ""]
    return _write_bytes(out_dir / "environment.properties", ("\n".join(lines) + "\n").encode())


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
    text = json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    return _write_bytes(target, text.encode("utf-8"))


def _write_bytes(target: Path, content: bytes) -> Path:
    """Write through a staging directory beside the results, then rename.

    ``allurectl watch`` uploads what appears in the results directory; a file must
    appear there complete or not at all.
    """
    # One staging directory per process and thread: parallel workers stream into the
    # same results directory, and one must never remove a directory another uses.
    owner = f"{os.getpid()}-{threading.get_ident()}"
    staging = target.parent.parent / f".{target.parent.name}.staging-{owner}"
    staging.mkdir(parents=True, exist_ok=True)
    temporary = staging / target.name
    temporary.write_bytes(content)
    os.replace(temporary, target)
    with suppress(OSError):
        staging.rmdir()
    return target
