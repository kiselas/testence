"""The target's own account of what it is running, read at the start and end of a run.

A red test on a shared environment is first a question about the build: which
version did it run against, and was that version replaced while the suite ran? A
project names a read-only endpoint that answers it (a version or info route) in
``testence.json``:

```json
"target_info": {"path": "/api/info", "fields": {"backend": "/backend/commit"}}
```

``fields`` maps a name to a JSON Pointer into the response; without it the response
itself is kept, clipped. The endpoint is read without logging in, once when the run
starts and once when it ends. An endpoint that cannot be read is recorded as such and
never fails the run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

#: What a field value, the whole body or an error may take in the ledger.
FIELD_LIMIT = 200
BODY_LIMIT = 4_000
DEFAULT_TIMEOUT_MS = 5_000


@dataclass(frozen=True)
class TargetInfoSpec:
    path: str
    fields: dict[str, str] = field(default_factory=dict)
    timeout_ms: int = DEFAULT_TIMEOUT_MS


def parse_spec(value: Any) -> TargetInfoSpec | None:
    """``target_info`` from the settings: a path, or ``{path, fields, timeout_ms}``."""
    if value is None or value == "" or value is False:
        return None
    if isinstance(value, str):
        value = {"path": value}
    if not isinstance(value, dict):
        raise ValueError("target_info must be a path or an object with a path")
    unknown = sorted(set(value) - {"path", "fields", "timeout_ms"})
    if unknown:
        raise ValueError(f"target_info has unknown key {unknown[0]!r}")
    path = value.get("path")
    if not isinstance(path, str) or not path.strip():
        raise ValueError("target_info.path must be a non-empty string")
    fields = value.get("fields", {}) or {}
    if not isinstance(fields, dict) or not all(
        isinstance(name, str) and name and isinstance(pointer, str)
        for name, pointer in fields.items()
    ):
        raise ValueError("target_info.fields must map names to JSON Pointers")
    for name, pointer in fields.items():
        if pointer and not pointer.startswith("/"):
            raise ValueError(f"target_info.fields.{name} must be a JSON Pointer starting with /")
    timeout = value.get("timeout_ms", DEFAULT_TIMEOUT_MS)
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 100 <= timeout <= 60_000:
        raise ValueError("target_info.timeout_ms must be an integer from 100 to 60000")
    return TargetInfoSpec(path=path.strip(), fields=dict(fields), timeout_ms=timeout)


def _pointer(document: Any, pointer: str) -> Any:
    if pointer == "":
        return document
    current = document
    for raw in pointer.lstrip("/").split("/"):
        part = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            if not part.isdigit() or int(part) >= len(current):
                return None
            current = current[int(part)]
        elif isinstance(current, dict):
            if part not in current:
                return None
            current = current[part]
        else:
            return None
    return current


def _shown(value: Any) -> str | None:
    if value is None:
        return None
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text[:FIELD_LIMIT]


def read(spec: TargetInfoSpec, settings: Any) -> dict[str, Any]:
    """One read of the endpoint as a ``target.info`` payload; never raises."""
    from testence.api import ApiClient

    record: dict[str, Any] = {"path": spec.path}
    try:
        client = ApiClient(
            settings.base_url,
            verify_tls=settings.verify_tls,
            ca_bundle=settings.ca_bundle,
            timeout_s=spec.timeout_ms / 1000,
        )
        response = client.get(spec.path)
    except Exception as exc:  # noqa: BLE001 - the build is evidence, never a verdict
        record["error"] = f"{type(exc).__name__}: {exc}"[:FIELD_LIMIT]
        return record
    record["status"] = response.status
    if not response.ok:
        record["error"] = f"HTTP {response.status}"
        return record
    document = response.json
    if spec.fields:
        if document is None:
            record["error"] = "the response is not JSON"
            return record
        record["fields"] = {name: _shown(_pointer(document, p)) for name, p in spec.fields.items()}
    elif document is not None:
        record["body"] = json.dumps(document, ensure_ascii=False, separators=(",", ":"))[
            :BODY_LIMIT
        ]
    else:
        record["body"] = response.body[:BODY_LIMIT]
    return record


def identity(record: dict[str, Any] | None) -> Any:
    """What two reads are compared by: the fields, or the body."""
    if not record or "error" in record:
        return None
    return record.get("fields", record.get("body"))


def changed(start: dict[str, Any] | None, end: dict[str, Any] | None) -> bool:
    """Whether the target answered differently at the end than at the start."""
    first, last = identity(start), identity(end)
    return first is not None and last is not None and first != last


def describe(record: dict[str, Any] | None) -> str:
    """One line for a terminal or a summary: ``backend=abc, frontend=def``."""
    if not record:
        return ""
    if "error" in record:
        return f"{record.get('path', '')} could not be read ({record['error']})"
    fields = record.get("fields")
    if isinstance(fields, dict):
        return ", ".join(
            f"{name}={value if value is not None else '-'}" for name, value in fields.items()
        )
    body = str(record.get("body", ""))
    return body if len(body) <= 160 else body[:157] + "..."
