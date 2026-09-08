"""Deterministic redaction and size limits applied before evidence is persisted."""

from __future__ import annotations

import json
import re
from typing import Any, Iterable

REDACTED = "<redacted>"
LEDGER_STRING_LIMIT = 16_384
FULL_SECTION_CHAR_LIMIT = 262_144

_SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "proxyauthorization",
        "cookie",
        "cookies",
        "setcookie",
        "password",
        "passwd",
        "secret",
        "clientsecret",
        "token",
        "accesstoken",
        "refreshtoken",
        "idtoken",
        "apikey",
        "privatekey",
        "storage",
    }
)
_AUTH_VALUE = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]+")
_COOKIE_HEADER = re.compile(r"(?im)(\b(?:cookie|set-cookie)\s*:\s*)[^\r\n]+")
_ASSIGNMENT = re.compile(
    r"(?i)(\b(?:password|passwd|secret|client_secret|access_token|refresh_token|"
    r"id_token|api_key|apikey|authorization)\b[\"']?\s*[:=]\s*[\"']?)"
    r"([^\s\"'&,;}]+)"
)
_QUERY_SECRET = re.compile(
    r"(?i)([?&](?:token|access_token|refresh_token|id_token|api_key|apikey|"
    r"password|secret)=)([^&#\s]+)"
)


def _normalized_key(key: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).casefold())


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"<truncated:{len(text) - limit} chars>"


def sanitize_text(
    text: str, *, secrets: Iterable[str] = (), limit: int = LEDGER_STRING_LIMIT
) -> str:
    """Redact common credential forms and caller-known values from free text."""
    safe = text
    for secret in sorted({value for value in secrets if len(value) >= 4}, key=len, reverse=True):
        safe = safe.replace(secret, REDACTED)
    safe = _AUTH_VALUE.sub(lambda match: f"{match.group(1)} {REDACTED}", safe)
    safe = _COOKIE_HEADER.sub(lambda match: f"{match.group(1)}{REDACTED}", safe)
    safe = _ASSIGNMENT.sub(lambda match: f"{match.group(1)}{REDACTED}", safe)
    safe = _QUERY_SECRET.sub(lambda match: f"{match.group(1)}{REDACTED}", safe)
    return _clip(safe, limit)


def sanitize(
    value: Any,
    *,
    secrets: Iterable[str] = (),
    key: object = "",
    limit: int = LEDGER_STRING_LIMIT,
) -> Any:
    """Return a JSON-safe copy with secrets removed and strings bounded."""
    normalized = _normalized_key(key)
    if normalized in _SENSITIVE_KEYS:
        return REDACTED
    if isinstance(value, dict):
        return {
            str(child_key): sanitize(
                child,
                secrets=secrets,
                key=child_key,
                limit=limit,
            )
            for child_key, child in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [sanitize(child, secrets=secrets, key=key, limit=limit) for child in value]
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("{", "[")):
            try:
                document = json.loads(value)
            except (json.JSONDecodeError, RecursionError):
                pass
            else:
                return _clip(
                    json.dumps(
                        sanitize(document, secrets=secrets, limit=limit),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    limit,
                )
        return sanitize_text(value, secrets=secrets, limit=limit)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return sanitize_text(str(value), secrets=secrets, limit=limit)
