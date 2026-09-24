"""Start-up work the plugin must not do, and the evidence it must still produce.

Stage 4 L18: on a fresh process one six-step test ran 15 % slower than
pytest-playwright. Most of the difference was start-up — a WMI query behind
``platform.release()``, jsonschema imported by a run that validates nothing, and the
run manifest rereading the ledger it had just written. Each fix below keeps the
recorded value identical; these tests hold both halves.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys

from testence import host
from testence.contracts import validate_document
from testence.contracts.document import DocumentError
from testence.evidence import EvidenceWriter


def _manifest_ledger(writer: EvidenceWriter) -> dict:
    manifest = json.loads((writer.run_dir / "manifest.json").read_text(encoding="utf-8"))
    return {entry["path"]: entry for entry in manifest["ledgers"]}["run.jsonl"]


def test_manifest_digests_the_ledger_it_did_not_reread(tmp_path):
    writer = EvidenceWriter(tmp_path, run_id="r-startup")
    writer.emit("run.start", config={"password": "hunter2"})
    writer.emit("note", test="t.py::x", text="é — non-ASCII must hash as written bytes")
    writer.emit("collection.end", selected=1, cases=[{"nodeid": "t.py::x"}])
    writer.close()

    content = writer.path.read_bytes()
    entry = _manifest_ledger(writer)
    assert entry["bytes"] == len(content)
    assert entry["sha256"] == hashlib.sha256(content).hexdigest()


def test_a_reused_run_id_digests_the_whole_appended_ledger(tmp_path):
    """A later session in the same process appends to the ledger it inherits."""
    first = EvidenceWriter(tmp_path, run_id="r-reused")
    first.emit("run.start")
    first.emit("collection.end", selected=2, cases=["a", "b"])
    first.close()

    second = EvidenceWriter(tmp_path, run_id="r-reused")
    second.emit("run.end", run_status="passed", exit_code=0)
    second.close()

    content = second.path.read_bytes()
    manifest = json.loads((second.run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert _manifest_ledger(second)["sha256"] == hashlib.sha256(content).hexdigest()
    # The selection recorded by the first session survives the second's checkpoint.
    assert manifest["selected"] == ["a", "b"]
    assert manifest["status"] == "complete"


def test_worker_ledgers_are_still_read_from_disk(tmp_path):
    controller = EvidenceWriter(tmp_path, run_id="r-workers")
    worker = EvidenceWriter(tmp_path, run_id="r-workers", worker="gw0")
    controller.emit("run.start")
    worker.emit("note", text="worker event")
    worker.close()
    controller.emit("run.end", run_status="passed", exit_code=0)
    controller.close()

    manifest = json.loads((controller.run_dir / "manifest.json").read_text(encoding="utf-8"))
    ledgers = {entry["path"]: entry for entry in manifest["ledgers"]}
    shard = worker.path.read_bytes()
    assert ledgers["run-gw0.jsonl"]["sha256"] == hashlib.sha256(shard).hexdigest()


def test_host_values_are_exactly_what_platform_reports():
    assert host.system() == platform.system()
    assert host.os_name() == f"{platform.system()} {platform.release()}"


def test_loading_the_plugin_does_not_import_jsonschema():
    probe = (
        "import sys, testence.pytest_plugin; "
        "print(sorted(m for m in sys.modules if m.split('.')[0] == 'jsonschema'))"
    )
    loaded = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert loaded == "[]"


def test_validation_still_rejects_a_document_after_the_validator_is_cached():
    receipt = {"schema": "testence/readiness-report/1"}
    for _ in range(2):
        try:
            validate_document(receipt, "readiness-report.schema.json")
        except DocumentError as exc:
            assert "schema validation failed" in str(exc)
        else:  # pragma: no cover - the partial document is invalid by construction
            raise AssertionError("an incomplete readiness report passed validation")
