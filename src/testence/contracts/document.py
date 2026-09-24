"""Strict bounded JSON and packaged JSON Schema validation."""

from __future__ import annotations

import functools
import json
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from jsonschema import Draft202012Validator


class DocumentError(ValueError):
    """A versioned Testence document is malformed or violates its schema."""


DEFAULT_MAX_BYTES = 1024 * 1024


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DocumentError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise DocumentError(f"non-finite JSON number is not supported: {value}")


def loads_document(raw: bytes, *, max_bytes: int = DEFAULT_MAX_BYTES) -> Any:
    if len(raw) > max_bytes:
        raise DocumentError(f"JSON document exceeds {max_bytes} bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DocumentError(f"JSON document is not UTF-8: {exc}") from exc
    try:
        return json.loads(text, object_pairs_hook=_object, parse_constant=_constant)
    except json.JSONDecodeError as exc:
        raise DocumentError(f"invalid JSON: {exc}") from exc


def load_document(path: Path | str, *, max_bytes: int = DEFAULT_MAX_BYTES) -> Any:
    source = Path(path)
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise DocumentError(f"cannot read JSON document {source}: {exc}") from exc
    return loads_document(raw, max_bytes=max_bytes)


def packaged_schema(filename: str) -> dict[str, Any]:
    resource = files("testence.contracts").joinpath("schemas", filename)
    document = loads_document(resource.read_bytes())
    if not isinstance(document, dict):
        raise DocumentError(f"packaged schema {filename!r} must be an object")
    # Imported here: jsonschema is 64 ms of start-up, and a plain pytest run that
    # loads the plugin never validates a document.
    from jsonschema import Draft202012Validator

    Draft202012Validator.check_schema(document)
    return document


@functools.lru_cache(maxsize=None)
def _validator(schema_filename: str) -> Draft202012Validator:
    """One checked validator per packaged schema; the schemas ship read-only."""
    from jsonschema import Draft202012Validator

    return Draft202012Validator(packaged_schema(schema_filename))


def validate_document(document: Any, schema_filename: str) -> None:
    errors = sorted(
        _validator(schema_filename).iter_errors(document),
        key=lambda item: tuple(str(part) for part in item.absolute_path),
    )
    if errors:
        error = errors[0]
        pointer = "/" + "/".join(str(part) for part in error.absolute_path)
        raise DocumentError(f"schema validation failed at {pointer or '/'}: {error.message}")


__all__ = [
    "DEFAULT_MAX_BYTES",
    "DocumentError",
    "load_document",
    "loads_document",
    "packaged_schema",
    "validate_document",
]
