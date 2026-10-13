"""Bounded, source-bound execution history for a single failed proof.

Read only the owning writer's flushed prefix. Never merge worker sequence numbers
or promote a successful generic intent-step into proof of a native interaction.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from testence.contracts.document import loads_document
from testence.contracts.versions import PACK_EVENTS_SCHEMA
from testence.evidence import EvidenceWriter, budgets_for, estimate_tokens

MAX_SOURCE_BYTES = 1024 * 1024
MAX_EVENTS = 64
_IDENTITY = ("project_id", "case_id", "variant_id", "attempt_id", "run_id", "proof_id")
_DIGESTS = ("plan_digest", "test_digest", "policy_digest")
_KINDS = {"step.start", "step.end", "assertion", "oracle", "native.used", "network.mocked"}
_FIELDS = {
    "v",
    "kind",
    "worker",
    "event_id",
    "seq",
    "ts",
    "test",
    *_IDENTITY,
    *_DIGESTS,
    "step",
    "intent",
    "target",
    "status",
    "duration_ms",
    "depth",
    "children",
    "weakenings",
    "soft",
    "fingerprint",
    "error",
    "assertion_id",
    "claim_id",
    "oracle_kind",
    "outcome",
    "expected",
    "actual",
    "source",
    "name",
    "ok",
    "diff",
    "observation",
    "operation",
    "pattern",
    "content_type",
    "size",
}


def _encode(document: dict[str, Any]) -> str:
    return json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n"


def execution_history(writer: EvidenceWriter, test_id: str, context: dict[str, Any]) -> str:
    """Return valid JSON within the section budget, with explicit omissions.

    The source digest binds a prefix, not the final ledger; byte offsets and line
    hashes locate each projection. Reading the tail bounds failure-path I/O even
    for very large runs. Absence here is never proof that an action did not run.
    """
    checkpoint = writer.ledger_checkpoint()
    binding = writer.sanitized({key: context[key] for key in _IDENTITY})
    expected = writer.sanitized({key: context[key] for key in _DIGESTS if context.get(key)})
    safe_test = writer.sanitized(test_id, limit=500)
    document: dict[str, Any] = {
        "schema": PACK_EVENTS_SCHEMA,
        "binding": binding,
        "source": checkpoint,
        "status": "complete",
        "omitted": {"source_prefix_bytes": 0, "events": 0, "invalid_records": 0},
        "events": [],
    }
    omitted = document["omitted"]
    end = checkpoint["bytes"]
    start = max(0, end - MAX_SOURCE_BYTES)
    try:
        with writer.path.open("rb") as stream:
            stream.seek(start)
            raw = stream.read(end - start)
        if len(raw) != end - start:
            raise ValueError("ledger prefix shortened")
        if start == 0 and hashlib.sha256(raw).hexdigest() != checkpoint["sha256"]:
            raise ValueError("ledger prefix digest mismatch")
    except (OSError, ValueError) as exc:
        document.update(status="unavailable", error=type(exc).__name__)
        return _encode(document)

    if start:
        # The first byte may be in the middle of a record. Skip that record even
        # if it happens to parse; its event envelope was not read from the start.
        cut = raw.find(b"\n") + 1
        if cut == 0:
            cut = len(raw)
        raw, start = raw[cut:], start + cut
        omitted["source_prefix_bytes"] = start
    offset = start
    for line in raw.splitlines(keepends=True):
        source_offset = offset
        offset += len(line)
        try:
            if not line.endswith(b"\n"):
                raise ValueError("unterminated record")
            event = loads_document(line, max_bytes=MAX_SOURCE_BYTES)
            if not isinstance(event, dict) or event.get("v") != "testence/2":
                raise ValueError("unsupported event envelope")
        except (ValueError, UnicodeDecodeError, RecursionError):
            omitted["invalid_records"] += 1
            continue
        if (
            event.get("test") != safe_test
            or event.get("kind") not in _KINDS
            or any(event.get(key) != value for key, value in {**binding, **expected}.items())
        ):
            continue
        projection = writer.sanitized(
            {key: value for key, value in event.items() if key in _FIELDS}
        )
        document["events"].append(
            {
                "offset": source_offset,
                "bytes": len(line),
                "sha256": hashlib.sha256(line).hexdigest(),
                "event": projection,
            }
        )
        if len(document["events"]) > MAX_EVENTS:
            document["events"].pop(0)
            omitted["events"] += 1
    if any(omitted.values()):
        document["status"] = "partial"
    while estimate_tokens(_encode(document)) > budgets_for("events") and document["events"]:
        document["events"].pop(0)
        omitted["events"] += 1
        document["status"] = "partial"
    return _encode(document)
