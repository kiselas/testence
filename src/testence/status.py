"""Canonical execution statuses shared by every ledger consumer.

Schema ``testence/1`` historically wrote ``pass``/``fail``.  The pytest lifecycle
hooks use the clearer ``passed``/``failed`` spellings.  Readers must treat those as
aliases or a framework upgrade looks like a product regression or a flake.
"""

from __future__ import annotations

from typing import Any

EXECUTION_STATUSES = frozenset({"passed", "failed", "broken", "skipped", "aborted", "not_run"})

_ALIASES = {
    "pass": "passed",
    "passed": "passed",
    "fail": "failed",
    "failed": "failed",
    "broken": "broken",
    "skipped": "skipped",
    "aborted": "aborted",
    "not_run": "not_run",
}


def normalize_execution_status(value: Any, *, default: str = "not_run") -> str:
    """Return the canonical spelling, failing closed for unknown values."""
    if value is None or value == "":
        return default
    return _ALIASES.get(str(value), "broken")


def execution_passed(value: Any) -> bool:
    return normalize_execution_status(value) == "passed"


def execution_failed(value: Any) -> bool:
    return normalize_execution_status(value) in {"failed", "broken", "aborted"}
