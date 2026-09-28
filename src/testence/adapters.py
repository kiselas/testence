"""Project adapter contracts — the entire per-project integration surface.

A project plugs in by implementing these three things (target: ≤ ~500 LOC total,
metric ``adapter_loc``):
- AuthAdapter: authenticate the engine and return the ``AuthContext`` the API
  client shares (``testence.auth``; re-exported here, ADR-0010).
- SeedAdapter: create deterministic test data and clean it up (marker discipline:
  every created entity carries the marker so a crashed run can be swept).
- an ActionMap class built on ``testence.dsl.Actions`` (plain code, no contract here).

Kept as Protocols on purpose: adapters live in the project's repo and depend on
testence, never the other way around.
"""

from __future__ import annotations

from typing import Any, Protocol

from testence.auth.base import AuthAdapter

__all__ = ["AuthAdapter", "SeedAdapter"]


class SeedAdapter(Protocol):
    def seed(self, marker: str, **kwargs: Any) -> dict[str, Any]:
        """Create prerequisites via API/DB; return ids for the test. Deterministic:
        same inputs → same shape of data (fixed faker seed or explicit values)."""
        ...

    def cleanup(self, marker: str) -> None:
        """Remove everything carrying the marker; verify removal (e.g. GET → 404)."""
        ...
