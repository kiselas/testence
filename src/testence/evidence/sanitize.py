"""Deterministic redaction and size limits applied before evidence is persisted.

Keys are matched by their parts, not only by an exact spelling: ``authToken``,
``session_token`` and ``X-Api-Key`` are the same secret to a reader and must be the
same secret to the redactor. Values that are secrets by their shape — a JWT, a
provider token prefix, a payment card number — are removed wherever they appear.

What is redacted beyond the built-in rules is a project decision recorded in
``RedactionPolicy``. The policy carries names, never values, so it can be written
into the ledger and applied again when a run is exported (ADR-0024).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

REDACTED = "<redacted>"
LEDGER_STRING_LIMIT = 16_384
FULL_SECTION_CHAR_LIMIT = 262_144
REDACTION_POLICY_SCHEMA = "testence/redaction-policy/1"

# Exact normalized names that are secrets on their own.
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
# A normalized name containing one of these is a secret: ``authtoken``,
# ``sessionid``, ``xcsrftoken``, ``dbpassword`` are all spelled without separators.
# ``cookie`` is deliberately exact-only (``_SENSITIVE_KEYS``): a field such as a raw
# header line keeps its text-rule redaction (``Cookie: <redacted>``) as evidence.
_SENSITIVE_FRAGMENTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "credential",
    "authorization",
    "apikey",
    "privatekey",
    "accesskey",
    "sessionid",
    "csrf",
    "xsrf",
    "jwt",
    "bearer",
)
# Short words that are secrets only as a whole part of a name: ``pwd`` and ``pin``
# but not ``pinned``; ``pass`` but not ``passage``.
_SENSITIVE_PARTS = frozenset(
    {"pass", "pwd", "passcode", "session", "sid", "otp", "pin", "sig", "signature", "creds"}
)
# ``<qualifier> key`` pairs: ``api_key``, ``accessKey``, ``private-key``.
_KEY_QUALIFIERS = frozenset(
    {"api", "access", "private", "secret", "client", "signing", "encryption", "auth"}
)
# Evidence field names Testence writes itself whose values are counts or timings, not
# credentials. They would otherwise match a rule (``sections_est_tokens``, ``session_ms``).
_INTERNAL_KEYS = frozenset({"sectionsesttokens", "esttokens", "sessionms"})
# Query parameters that carry a credential only in a URL: an OAuth authorization
# ``code`` or a bare ``key``.
_URL_ONLY_PARAMS = frozenset({"code", "key", "xamzsignature", "xamzcredential"})
_PII_KINDS = frozenset({"email", "phone"})
# A record that names its field in data rather than in its key: an oracle diff
# ``{"field": "authToken", "ui": ...}`` or a HAR header ``{"name": "Authorization",
# "value": ...}``. Only these value slots are redacted; an element fingerprint keeps
# its role and selector even when its accessible name is "Password".
_NAME_SLOTS = frozenset({"name", "field", "key", "header", "param", "parameter"})
_VALUE_SLOTS = frozenset({"value", "ui", "api", "expected", "actual", "old", "new"})

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_AUTH_VALUE = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]+")
_COOKIE_HEADER = re.compile(r"(?im)(\b(?:cookie|set-cookie)\s*:\s*)[^\r\n]+")
_QUERY_PARAM = re.compile(r"(?P<prefix>[?&;])(?P<name>[^=&#\s?;]{1,64})=(?P<value>[^&#\s\"']*)")
# Only ``name`` and ``sep`` are consumed; the value is a lookahead. ``console: token=x``
# must still see ``token`` as the next name instead of swallowing it as a value.
_ASSIGNMENT = re.compile(
    r"(?P<name>(?<![\w.-])[A-Za-z_][A-Za-z0-9_.-]{0,63})"
    r"(?P<sep>[\"']?\s*[:=]\s*[\"']?)"
    r"(?=(?P<value>[^\s\"'&,;}]+))"
)
_JWT = re.compile(r"(?<![\w-])eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*")
_TOKEN_PREFIX = re.compile(
    r"(?<![\w-])(?:"
    r"gh[pousr]_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|glpat-[A-Za-z0-9_-]{20,}"
    r"|xox[abprs]-[A-Za-z0-9-]{10,}"
    r"|sk-[A-Za-z0-9_-]{20,}"
    r"|AKIA[0-9A-Z]{16}"
    r")"
)
_CARD = re.compile(r"(?<![\w-])[2-6]\d{3}(?:[ -]?\d){9,15}(?![\w-])")
_EMAIL = re.compile(
    r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"
)
_PHONE = re.compile(r"(?<![\w+])\+?\d[\d ()-]{8,18}\d(?![\w])")


def _normalized_key(key: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).casefold())


def _key_parts(key: object) -> list[str]:
    spaced = _CAMEL_BOUNDARY.sub(" ", str(key))
    return [part for part in re.split(r"[^A-Za-z0-9]+", spaced.casefold()) if part]


def _names(values: Iterable[object], field_name: str) -> frozenset[str]:
    names = set()
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"evidence.redact.{field_name} must contain non-empty strings")
        names.add(_normalized_key(value))
    return frozenset(names)


@dataclass(frozen=True)
class RedactionPolicy:
    """Project additions to the built-in redaction rules. Names only, never values."""

    keys: frozenset[str] = field(default_factory=frozenset)
    allow_keys: frozenset[str] = field(default_factory=frozenset)
    url_params: frozenset[str] = field(default_factory=frozenset)
    pii: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def from_config(cls, value: object) -> RedactionPolicy:
        """Build from the ``evidence.redact`` object of ``testence.json``.

        ``env`` (names of variables whose values are redacted) is resolved by the
        caller, because values must never enter a policy that is written to evidence.
        """
        if value is None:
            return cls()
        if not isinstance(value, Mapping):
            raise ValueError("evidence.redact must be an object")
        unknown = sorted(set(value) - {"keys", "allow_keys", "url_params", "pii", "env"})
        if unknown:
            raise ValueError("unknown evidence.redact field(s): " + ", ".join(unknown))
        lists: dict[str, list[object]] = {}
        for name in ("keys", "allow_keys", "url_params", "pii"):
            raw = value.get(name, [])
            if not isinstance(raw, list):
                raise ValueError(f"evidence.redact.{name} must be a list of strings")
            lists[name] = raw
        pii = _names(lists["pii"], "pii")
        unsupported = sorted(pii - _PII_KINDS)
        if unsupported:
            raise ValueError(
                "evidence.redact.pii supports "
                + ", ".join(sorted(_PII_KINDS))
                + f"; got {', '.join(unsupported)}"
            )
        return cls(
            keys=_names(lists["keys"], "keys"),
            allow_keys=_names(lists["allow_keys"], "allow_keys"),
            url_params=_names(lists["url_params"], "url_params"),
            pii=pii,
        )

    @classmethod
    def from_json(cls, value: object) -> RedactionPolicy:
        """Read the policy a run recorded in its ``run.start`` event."""
        if not isinstance(value, Mapping) or value.get("schema") != REDACTION_POLICY_SCHEMA:
            return cls()
        try:
            return cls.from_config({key: value.get(key, []) for key in _POLICY_LISTS})
        except ValueError:
            return cls()

    def to_json(self) -> dict[str, Any]:
        return {
            "schema": REDACTION_POLICY_SCHEMA,
            **{name: sorted(getattr(self, name)) for name in _POLICY_LISTS},
        }


_POLICY_LISTS = ("keys", "allow_keys", "url_params", "pii")
DEFAULT_POLICY = RedactionPolicy()


def is_sensitive_key(key: object, policy: RedactionPolicy = DEFAULT_POLICY) -> bool:
    """Whether a field or parameter name holds a credential."""
    normalized = _normalized_key(key)
    if not normalized or normalized in policy.allow_keys or normalized in _INTERNAL_KEYS:
        return False
    if normalized in _SENSITIVE_KEYS or normalized in policy.keys:
        return True
    if any(fragment in normalized for fragment in _SENSITIVE_FRAGMENTS):
        return True
    parts = _key_parts(key)
    if any(part in _SENSITIVE_PARTS or part in policy.keys for part in parts):
        return True
    return any(
        second == "key" and first in _KEY_QUALIFIERS for first, second in zip(parts, parts[1:])
    )


def _is_sensitive_param(name: str, policy: RedactionPolicy) -> bool:
    normalized = _normalized_key(name)
    return (
        normalized in _URL_ONLY_PARAMS
        or normalized in policy.url_params
        or is_sensitive_key(name, policy)
    )


def _luhn(digits: str) -> bool:
    total = 0
    for index, char in enumerate(reversed(digits)):
        number = int(char)
        if index % 2:
            number *= 2
            if number > 9:
                number -= 9
        total += number
    return total % 10 == 0


def _card(match: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", match.group(0))
    return REDACTED if 13 <= len(digits) <= 19 and _luhn(digits) else match.group(0)


def _phone(match: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", match.group(0))
    return REDACTED if 10 <= len(digits) <= 15 else match.group(0)


def _redact_assignments(text: str, policy: RedactionPolicy) -> str:
    """Replace the value of every ``name: value`` / ``name=value`` with a secret name."""
    pieces: list[str] = []
    cursor = 0
    for match in _ASSIGNMENT.finditer(text):
        if match.start() < cursor or not is_sensitive_key(match.group("name"), policy):
            continue
        value_end = match.end() + len(match.group("value"))
        pieces.append(text[cursor : match.end()])
        pieces.append(REDACTED)
        cursor = value_end
    if not pieces:
        return text
    pieces.append(text[cursor:])
    return "".join(pieces)


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"<truncated:{len(text) - limit} chars>"


def sanitize_text(
    text: str,
    *,
    secrets: Iterable[str] = (),
    limit: int = LEDGER_STRING_LIMIT,
    policy: RedactionPolicy = DEFAULT_POLICY,
) -> str:
    """Redact credential forms, caller-known values and opted-in PII from free text."""
    safe = text
    for secret in sorted({value for value in secrets if len(value) >= 4}, key=len, reverse=True):
        safe = safe.replace(secret, REDACTED)
    safe = _JWT.sub(REDACTED, safe)
    safe = _TOKEN_PREFIX.sub(REDACTED, safe)
    safe = _AUTH_VALUE.sub(lambda match: f"{match.group(1)} {REDACTED}", safe)
    safe = _COOKIE_HEADER.sub(lambda match: f"{match.group(1)}{REDACTED}", safe)
    safe = _QUERY_PARAM.sub(
        lambda match: (
            f"{match.group('prefix')}{match.group('name')}={REDACTED}"
            if match.group("value") and _is_sensitive_param(match.group("name"), policy)
            else match.group(0)
        ),
        safe,
    )
    safe = _redact_assignments(safe, policy)
    safe = _CARD.sub(_card, safe)
    if "email" in policy.pii:
        safe = _EMAIL.sub(REDACTED, safe)
    if "phone" in policy.pii:
        safe = _PHONE.sub(_phone, safe)
    return _clip(safe, limit)


def _sanitize_json_lines(
    value: str, *, secrets: Iterable[str], limit: int, policy: RedactionPolicy
) -> str | None:
    """Redact JSON Lines record by record, or return ``None`` when this is not JSONL.

    Network evidence is one JSON object per line (``dump_net``), so a capture with
    more than one request is not a single JSON document. Without this path the whole
    blob fell back to regex-only text redaction, where a body field already escaped
    once as ``\\"password\\":\\"...\\"`` no longer matches the assignment pattern and
    the value reached ``network.jsonl`` in clear text. Key-based redaction must apply
    to every record, not only to a capture that happens to hold exactly one.
    """

    lines = value.splitlines()
    if len(lines) < 2:
        return None
    documents: list[str] = []
    parsed_any = False
    for line in lines:
        if not line.strip():
            documents.append(line)
            continue
        try:
            document = json.loads(line)
        except (json.JSONDecodeError, RecursionError):
            # A truncated or interleaved line still gets the text policy; one
            # unparsable record must not disable structural redaction for the rest.
            documents.append(sanitize_text(line, secrets=secrets, limit=limit, policy=policy))
            continue
        parsed_any = True
        documents.append(
            json.dumps(
                sanitize(document, secrets=secrets, limit=limit, policy=policy),
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
    if not parsed_any:
        return None
    return _clip("\n".join(documents), limit)


def sanitize(
    value: Any,
    *,
    secrets: Iterable[str] = (),
    key: object = "",
    limit: int = LEDGER_STRING_LIMIT,
    policy: RedactionPolicy = DEFAULT_POLICY,
) -> Any:
    """Return a JSON-safe copy with secrets removed and strings bounded."""
    secrets = tuple(secrets)
    if is_sensitive_key(key, policy):
        return REDACTED
    if isinstance(value, dict):
        named_secret = any(
            str(slot).casefold() in _NAME_SLOTS
            and isinstance(name, str)
            and is_sensitive_key(name, policy)
            for slot, name in value.items()
        )
        return {
            str(child_key): REDACTED
            if named_secret and str(child_key).casefold() in _VALUE_SLOTS and child is not None
            else sanitize(
                child,
                secrets=secrets,
                key=child_key,
                limit=limit,
                policy=policy,
            )
            for child_key, child in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [
            sanitize(child, secrets=secrets, key=key, limit=limit, policy=policy) for child in value
        ]
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("{", "[")):
            try:
                document = json.loads(value)
            except (json.JSONDecodeError, RecursionError):
                as_lines = _sanitize_json_lines(value, secrets=secrets, limit=limit, policy=policy)
                if as_lines is not None:
                    return as_lines
            else:
                return _clip(
                    json.dumps(
                        sanitize(document, secrets=secrets, limit=limit, policy=policy),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    limit,
                )
        return sanitize_text(value, secrets=secrets, limit=limit, policy=policy)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return sanitize_text(str(value), secrets=secrets, limit=limit, policy=policy)


def recorded_policy(events: Iterable[Mapping[str, Any]]) -> RedactionPolicy:
    """The policy a run recorded in ``run.start``; defaults for older ledgers."""
    for event in events:
        if event.get("kind") == "run.start" and event.get("redaction"):
            return RedactionPolicy.from_json(event.get("redaction"))
    return DEFAULT_POLICY


def redact_events(
    events: list[dict[str, Any]], policy: RedactionPolicy | None = None
) -> list[dict[str, Any]]:
    """Apply the current rules again to a loaded ledger.

    A ledger is redacted when it is written, but a rule added later (or a ledger from
    an older release) must not reach an export or a report in clear text.
    """
    active = policy if policy is not None else recorded_policy(events)
    return [sanitize(event, policy=active) for event in events]


def redact_document_text(
    text: str,
    *,
    suffix: str,
    policy: RedactionPolicy = DEFAULT_POLICY,
    limit: int = FULL_SECTION_CHAR_LIMIT,
) -> str:
    """Redact one evidence file for export, keeping its bytes when nothing changes."""
    if suffix == ".json":
        try:
            document = json.loads(text)
        except (json.JSONDecodeError, RecursionError):
            return sanitize_text(text, limit=limit, policy=policy)
        cleaned = sanitize(document, limit=limit, policy=policy)
        if cleaned == document:
            return text
        return json.dumps(cleaned, ensure_ascii=False, indent=1) + "\n"
    if suffix == ".jsonl":
        lines: list[str] = []
        for line in text.splitlines():
            try:
                record = json.loads(line) if line.strip() else None
            except (json.JSONDecodeError, RecursionError):
                lines.append(sanitize_text(line, limit=limit, policy=policy))
                continue
            if record is None:
                lines.append(line)
                continue
            cleaned = sanitize(record, limit=limit, policy=policy)
            lines.append(line if cleaned == record else json.dumps(cleaned, ensure_ascii=False))
        rebuilt = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
        return text if rebuilt == text else rebuilt
    return sanitize_text(text, limit=limit, policy=policy)
