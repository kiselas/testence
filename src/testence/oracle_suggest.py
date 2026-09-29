"""Oracle discovery: what the app sent, turned into an API check to write.

A test that only looks at the screen cannot catch a UI that says "saved" over a lost
write; the API oracle can. Writing one needs the mutation's endpoint, the read that
proves it and the fields worth comparing. The browser already saw all of that while the
test ran. ``net_digest`` keeps a compact record of the API traffic (a ``net`` event per
test); ``suggest`` reads a finished run and proposes, per mutation, the
``save_and_verify_state`` call that would prove it.

The digest keeps names and shapes, not data: paths with identifiers templated, and the
top-level keys of a body when the project opted into body capture. The one value it
reads is the identifier that templates a path, and that never leaves this module.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from pathlib import Path
from typing import Any

from testence.engine import NetRecord

#: Mutations and reads kept per test; a page that polls must not grow the ledger.
_MAX_MUTATIONS = 40
_MAX_READS = 30
_MAX_KEYS = 30

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_ID_KEYS = ("id", "uuid", "pk", "key", "slug")
_ENVELOPE_KEYS = ("data", "result", "item", "payload", "record", "resource")
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def _segment_is_identifier(segment: str) -> bool:
    return bool(
        segment.isdigit()
        or _UUID.match(segment)
        or (len(segment) >= 16 and re.fullmatch(r"[0-9a-fA-F]+", segment))
    )


def _template(path: str, known_ids: set[str]) -> str:
    parts = path.split("/")
    return "/".join(
        "{id}" if part and (part in known_ids or _segment_is_identifier(part)) else part
        for part in parts
    )


def _json(text: str | None) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def _keys(document: Any) -> list[str]:
    if isinstance(document, dict):
        return sorted(str(key) for key in document)[:_MAX_KEYS]
    return []


def _entity(document: Any) -> tuple[str | None, str | None]:
    """The dotted path of the identifier a response carries, and its value."""
    if not isinstance(document, dict):
        return None, None
    for key in _ID_KEYS:
        value = document.get(key)
        if isinstance(value, (str, int)) and not isinstance(value, bool) and str(value):
            return key, str(value)
    for wrapper in _ENVELOPE_KEYS:
        inner = document.get(wrapper)
        if isinstance(inner, dict):
            path, value = _entity(inner)
            if path is not None:
                return f"{wrapper}.{path}", value
    return None, None


def net_digest(records: list[NetRecord], *, bodies: bool) -> dict[str, Any] | None:
    """The ``net`` event payload for one test's traffic, or ``None`` when it saw none."""
    if not records:
        return None
    known_ids: set[str] = set()
    for record in records:
        if record.method.upper() not in _SAFE_METHODS:
            _path, value = _entity(_json(record.response_body))
            if value is not None:
                known_ids.add(value)
    mutations: list[dict[str, Any]] = []
    reads: dict[tuple[str, str], dict[str, Any]] = {}
    current: dict[str, Any] | None = None
    for record in records:
        parts = urllib.parse.urlsplit(record.url)
        path = _template(parts.path, known_ids)
        method = record.method.upper()
        if method in _SAFE_METHODS:
            if (method, path) in reads or len(reads) < _MAX_READS:
                entry = reads.setdefault((method, path), {"method": method, "path": path, "n": 0})
                entry["n"] += 1
                if record.status is not None:
                    entry["status"] = record.status
            if (
                current is not None
                and method == "GET"
                and path not in current["reads_after"]
                and len(current["reads_after"]) < 5
            ):
                current["reads_after"].append(path)
            continue
        if len(mutations) >= _MAX_MUTATIONS:
            continue
        response = _json(record.response_body)
        id_path, _value = _entity(response)
        current = {
            "method": method,
            "origin": f"{parts.scheme}://{parts.netloc}",
            "path": path,
            "status": record.status,
            "request_keys": _keys(_json(record.request_body)),
            "response_keys": _keys(response),
            "reads_after": [],
        }
        if record.failure:
            current["failure"] = record.failure
        if id_path is not None:
            current["id_path"] = id_path
        mutations.append(current)
    return {
        "mutations": mutations,
        "reads": sorted(reads.values(), key=lambda entry: (entry["path"], entry["method"])),
        "bodies": bodies,
    }


def _server_owned(key: str) -> bool:
    """A response field the client did not send: identity, timestamps, versions."""
    lowered = key.lower()
    return (
        lowered in _ID_KEYS
        or lowered in {"revision", "version", "etag"}
        or lowered.endswith(("_id", "_at"))
        or bool(re.search(r"[a-z](Id|At)$", key))
    )


def _collection(path: str) -> str:
    return path[: -len("/{id}")] if path.endswith("/{id}") else path


def _identifier(text: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", text)
    return "_".join(word.lower() for word in words) or "value"


def _candidate(test: str, mutation: dict[str, Any], reads: set[str]) -> dict[str, Any] | None:
    status = mutation.get("status")
    if not isinstance(status, int) or not 200 <= status < 300:
        return None
    method, path = str(mutation["method"]), str(mutation["path"])
    collection = _collection(path)
    item = f"{collection}/{{id}}"
    on_item = path.endswith("/{id}")
    notes: list[str] = []
    if method == "DELETE" and on_item:
        read, source, expectation = item, "mutation path", "absent"
    elif on_item:
        read, source, expectation = item, "mutation path", "fields"
    elif mutation.get("id_path"):
        read = item
        source = "traffic" if item in reads else "response id"
        expectation = "fields"
        notes.append(
            f"the response carries the new id at {mutation['id_path']!r}: use it as the "
            "entity id, or read the collection and match a value you sent"
        )
    else:
        read = collection
        source = "traffic" if collection in reads else "mutation path"
        expectation = "fields"
        notes.append("the response has no id: read the collection and match a value you sent")
    if mutation["request_keys"]:
        compared = sorted(set(mutation["request_keys"]) & set(mutation["response_keys"]))
    else:
        # Browsers rarely declare a request's size, and a body of unknown size is never
        # materialized (capture policy). The response still names what the server stored.
        compared = [key for key in mutation["response_keys"] if not _server_owned(key)]
        if expectation == "fields":
            notes.append(
                "the request body was not captured: the fields are the response's, keep "
                "the ones you typed into the form"
            )
    strength = "strong" if read == item and source != "response id" else "weak"
    return {
        "test": test,
        "mutation": f"{method} {path}",
        "read": f"GET {read}",
        "read_source": source,
        "expect": expectation,
        "fields": compared,
        "strength": strength,
        "notes": notes,
        "snippet": _snippet(mutation, read, expectation, compared),
    }


def _literal(path: str) -> str:
    """A Python string for a request path; a templated identifier becomes an f-string hole."""
    if "{id}" not in path:
        return f'"{path}"'
    return 'f"' + path.replace("{id}", "{entity_id}") + '"'


def _snippet(mutation: dict[str, Any], read: str, expectation: str, fields: list[str]) -> str:
    method, path, origin = mutation["method"], mutation["path"], mutation["origin"]
    resource = _collection(path).rsplit("/", 1)[-1] or "resource"
    verb = {"POST": "create", "PUT": "update", "PATCH": "update", "DELETE": "delete"}.get(
        method, method.lower()
    )
    name = f"{_identifier(resource)} {verb}"
    read_path = read.replace("{id}", "{entity_id}")
    if expectation == "absent":
        expected = f'ExpectedState.absent("{name} is gone", entity_id=entity_id)'
    else:
        checks = " and ".join(f'body["{field}"] == sent["{field}"]' for field in fields)
        expected = (
            f'ExpectedState(\n        "{name} is persisted",\n'
            f"        lambda body: {checks or 'True  # TODO: compare the fields the UI claims'},\n"
            "        entity_id=entity_id,\n    )"
        )
    return (
        "save_and_verify_state(\n"
        f"    ex,\n    SAVE_TARGET,  # the control that sends {method} {path}\n"
        f'    name="{name}",\n'
        f'    request=RequestExpectation({_literal(path)}, "{method}", origin="{origin}"),\n'
        f'    read=lambda: testence_api.get_fresh(f"{read_path}"),\n'
        f"    expected={expected},\n)"
    )


def suggest(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Oracle candidates for every successful mutation the ledger's ``net`` events hold."""
    candidates: list[dict[str, Any]] = []
    warnings: list[str] = []
    digests = [event for event in events if event.get("kind") == "net"]
    if not digests:
        warnings.append(
            "this run recorded no API traffic: nothing under api_prefix was requested, or the "
            "run predates the net event"
        )
    seen: set[tuple[str, str]] = set()
    bodiless = 0
    for event in digests:
        test = str(event.get("test") or "")
        reads = {str(entry["path"]) for entry in event.get("reads", []) if entry.get("status")}
        if not event.get("bodies"):
            bodiless += 1
        for mutation in event.get("mutations", []):
            candidate = _candidate(test, mutation, reads)
            if candidate is None or (candidate["test"], candidate["mutation"]) in seen:
                continue
            seen.add((candidate["test"], candidate["mutation"]))
            candidates.append(candidate)
    if digests and bodiless == len(digests):
        warnings.append(
            "bodies were not captured, so field names and ids are missing: set "
            '"capture_policy": {"network_bodies": true} in testence.json for an app with '
            "synthetic data and record the run again"
        )
    if digests and not candidates:
        warnings.append("the run made no successful mutation request, so there is nothing to prove")
    return {"candidates": candidates, "warnings": warnings}


def render(result: dict[str, Any]) -> str:
    """The readable form: one block per candidate, ASCII so any console prints it."""
    lines = [f"warning: {warning}" for warning in result["warnings"]]
    for candidate in result["candidates"]:
        lines.append(
            f"{candidate['test']}: {candidate['mutation']} -> {candidate['read']} "
            f"({candidate['strength']}, read from {candidate['read_source']})"
        )
        lines.extend(f"  note: {note}" for note in candidate["notes"])
        lines.extend("  " + line for line in candidate["snippet"].splitlines())
    return "\n".join(lines) or "no candidates"


def suggest_run(run_dir: Path | str) -> dict[str, Any]:
    from testence.metrics import load_run

    return suggest(load_run(Path(run_dir)))
