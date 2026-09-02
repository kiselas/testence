"""Small strict-validation helpers shared by repository-owned contracts."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

IDENTIFIER_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?$")


class ContractError(ValueError):
    """A contract document is well-formed data but violates its public schema."""


def mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{path} must be an object")
    return value


def known_fields(doc: Mapping[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(set(doc) - allowed)
    if unknown:
        raise ContractError(f"{path} has unknown field(s): {', '.join(unknown)}")


def text(doc: Mapping[str, Any], key: str, path: str, *, max_length: int = 500) -> str:
    value = doc.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{path}.{key} must be a non-empty string")
    value = value.strip()
    if len(value) > max_length:
        raise ContractError(f"{path}.{key} must be at most {max_length} characters")
    return value


def optional_text(
    doc: Mapping[str, Any], key: str, path: str, *, max_length: int = 500
) -> str | None:
    value = doc.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{path}.{key} must be a non-empty string when present")
    value = value.strip()
    if len(value) > max_length:
        raise ContractError(f"{path}.{key} must be at most {max_length} characters")
    return value


def identifier(doc: Mapping[str, Any], key: str, path: str) -> str:
    value = text(doc, key, path, max_length=128)
    if not IDENTIFIER_RE.fullmatch(value):
        raise ContractError(f"{path}.{key} must use lowercase letters, numbers, '.', '_' or '-'")
    return value


def string_list(
    value: Any,
    path: str,
    *,
    non_empty: bool = False,
    identifiers: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ContractError(f"{path} must be an array of strings")
    if non_empty and not value:
        raise ContractError(f"{path} must not be empty")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ContractError(f"{path}[{index}] must be a non-empty string")
        item = item.strip()
        if identifiers and not IDENTIFIER_RE.fullmatch(item):
            raise ContractError(f"{path}[{index}] is not a valid identifier: {item!r}")
        result.append(item)
    if len(set(result)) != len(result):
        raise ContractError(f"{path} must not contain duplicates")
    return tuple(result)
