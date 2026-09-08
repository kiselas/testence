"""Project/test data namespaces and verified seed-adapter lifecycle."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from testence.adapters import SeedAdapter


def _slug(value: str, *, limit: int = 32) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:limit] or "case"


@dataclass(frozen=True)
class TestNamespace:
    """A collision-resistant marker for one project/run/worker/test/role attempt."""

    project_id: str
    run_id: str
    worker_id: str
    case_id: str
    role: str
    attempt_id: str = "attempt-1"

    @property
    def marker(self) -> str:
        material = "\0".join(
            (
                self.project_id,
                self.run_id,
                self.worker_id,
                self.case_id,
                self.role,
                self.attempt_id,
            )
        )
        suffix = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
        return f"testence-{_slug(self.project_id)}-{_slug(self.case_id)}-{suffix}"


@dataclass
class SeedLifecycle:
    """Own one adapter marker and make cleanup a mandatory visible operation."""

    adapter: SeedAdapter
    namespace: TestNamespace
    owner: str
    values: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.owner.strip():
            raise ValueError("seed lifecycle owner is required")

    def seed(self, **kwargs: Any) -> dict[str, Any]:
        if self.values is not None:
            raise RuntimeError("seed lifecycle can only seed once")
        self.values = self.adapter.seed(self.namespace.marker, **kwargs)
        return self.values

    def cleanup(self) -> None:
        if self.values is None:
            raise RuntimeError("cannot clean a lifecycle that was not seeded")
        self.adapter.cleanup(self.namespace.marker)
        self.values = None

    def __enter__(self) -> "SeedLifecycle":
        return self

    def __exit__(self, *_exc: object) -> None:
        if self.values is not None:
            self.cleanup()
