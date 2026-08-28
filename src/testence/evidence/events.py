"""Event model for run.jsonl (schema ``testence/1``).

Design rules (see docs/en/evidence-schema.md):
- One JSON object per line, append-only, UTF-8, ``\n`` line endings on all platforms.
- Every event carries the same envelope; ``kind`` selects the payload contract.
- Green steps stay compact; failures point to an evidence-pack directory. Detail is
  asymmetric by design — the token budget of a green run is close to zero.
- Large blobs (bodies, screenshots, full snapshots) never go inline: events carry
  a relative ``ref`` path plus an inline head capped by the section budget.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from testence import SCHEMA_VERSION

# Per-section token budgets for a single evidence pack (normative; the pack
# assembler enforces them by truncating with a ref to the full file).
# Values are pre-registered defaults; experiment E4 (evidence ablation) owns them.
PACK_BUDGETS_TOKENS: dict[str, int] = {
    "aria": 8_000,
    "network": 8_000,
    "console": 2_000,
    "oracle": 2_000,
    "manifest": 500,
}

KINDS = frozenset(
    {
        "run.start",
        "run.end",
        "test.start",
        "test.end",
        "step.start",
        "step.end",
        "test.waits",
        "net",
        "console",
        "oracle",
        "pack",
        "note",
    }
)


def estimate_tokens(text: str) -> int:
    """Token estimate for budget enforcement (kernel-dispatched, see testence.kernels).

    Byte sizes are recoverable from the files themselves, so a real tokenizer can
    replace the estimate later without a schema change.
    """
    from testence import kernels

    return kernels.estimate_tokens(text)


def budgets_for(section: str) -> int:
    return PACK_BUDGETS_TOKENS[section]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass
class Event:
    """Envelope + payload. ``seq`` and ``ts`` are stamped by the writer."""

    kind: str
    run: str
    test: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    seq: int = -1
    ts: str = ""

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"unknown event kind: {self.kind!r}")

    def stamp(self, seq: int) -> None:
        self.seq = seq
        if not self.ts:
            self.ts = _utc_now_iso()

    def to_json(self) -> str:
        doc: dict[str, Any] = {
            "v": SCHEMA_VERSION,
            "run": self.run,
            "seq": self.seq,
            "ts": self.ts,
            "kind": self.kind,
        }
        if self.test is not None:
            doc["test"] = self.test
        doc.update(self.payload)
        return json.dumps(doc, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def parse(line: str) -> dict[str, Any]:
        doc = json.loads(line)
        if doc.get("v") != SCHEMA_VERSION:
            raise ValueError(f"unsupported schema version: {doc.get('v')!r}")
        return doc
