"""Parsed view of a ledger, shared by every exporter (ADR-0013).

Exporters receive this, never raw files: grouping, the step tree and timestamp
arithmetic happen once here, so writing a new exporter is a formatting exercise.

Every field is tolerant of absence. Schema ``testence/1`` grows by appending fields,
never retroactively, so a ledger written by an older version of the framework must
keep exporting — with less detail, not with a crash.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Files an evidence pack may contain, in the order a reader should meet them:
# the machine index first, then the triage contract, then the raw sections.
PACK_FILES = (
    "pack.json",
    "TRIAGE.md",
    "verdict.json",
    "verdict.template.json",
    "aria.txt",
    "network.jsonl",
    "console.txt",
    "oracle.json",
    "heal.json",
    "browser.json",
    "screenshot.png",
)


def parse_ts(ts: str | None) -> datetime | None:
    """Parse an envelope timestamp. Returns None rather than raising: a malformed
    ``ts`` must not cost an entire export."""
    if not ts:
        return None
    text = ts[:-1] + "+00:00" if ts.endswith("Z") else ts
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def epoch_ms(moment: datetime | None) -> int | None:
    return None if moment is None else int(moment.timestamp() * 1000)


@dataclass
class Step:
    """One step, with its children — nesting is real, not implied by ``depth``.

    A composite ActionMap method contains its primitives, and its duration already
    includes theirs (see ``children`` in docs/en/evidence-schema.md). Exporters that
    sum durations must therefore walk leaves only.
    """

    step: str
    intent: str = ""
    target: str | None = None
    status: str = "ok"
    duration_ms: float = 0.0
    error: str | None = None
    start: datetime | None = None
    stop: datetime | None = None
    substeps: list[Step] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return self.status not in ("ok", "pass", "passed")


@dataclass
class Test:
    """One test case as the ledger saw it."""

    name: str
    nodeid: str = ""
    file: str = ""
    markers: tuple[str, ...] = ()
    plan_id: str = ""
    plan_path: str = ""
    claim_ids: tuple[str, ...] = ()
    status: str = "pass"
    duration_ms: float = 0.0
    start: datetime | None = None
    stop: datetime | None = None
    error: str | None = None
    steps: list[Step] = field(default_factory=list)
    oracles: list[dict[str, Any]] = field(default_factory=list)
    pack_dir: str | None = None
    pack_sections: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.nodeid:
            self.nodeid = self.name

    @property
    def failed(self) -> bool:
        return self.status not in ("pass", "passed")


@dataclass
class LoadedRun:
    """A whole run: what the exporters format.

    ``events`` stays available as an escape hatch, but an exporter reaching for it
    is a signal that this model is missing a view the format genuinely needs.
    """

    run_id: str = ""
    testence_version: str = ""
    fingerprint: dict[str, Any] = field(default_factory=dict)
    start: datetime | None = None
    stop: datetime | None = None
    duration_ms: float = 0.0
    tests: list[Test] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    run_dir: Path = Path()

    @property
    def passed(self) -> int:
        return sum(1 for test in self.tests if not test.failed)

    @property
    def failed(self) -> int:
        return sum(1 for test in self.tests if test.failed)

    def pack_path(self, test: Test, filename: str) -> Path | None:
        """Absolute path of one pack file, or None when it was not captured."""
        if not test.pack_dir:
            return None
        candidate = self.run_dir / test.pack_dir / filename
        return candidate if candidate.is_file() else None

    @classmethod
    def from_events(cls, events: list[dict[str, Any]], run_dir: Path | str = "") -> LoadedRun:
        run = cls(events=events, run_dir=Path(run_dir))
        tests: dict[str, Test] = {}
        # One open-step stack per test: under -n the ledgers of several workers are
        # merged by timestamp, so events of different tests legitimately interleave.
        stacks: dict[str, list[Step]] = {}

        for doc in events:
            kind = doc.get("kind")
            if kind == "run.start":
                run.run_id = doc.get("run", run.run_id)
                run.testence_version = doc.get("testence", "")
                run.fingerprint = doc.get("fingerprint") or {}
                run.start = run.start or parse_ts(doc.get("ts"))
                continue
            if kind == "run.end":
                run.stop = parse_ts(doc.get("ts"))
                run.duration_ms = float(doc.get("duration_ms") or 0.0)
                continue

            test_id = doc.get("test")
            if not test_id:
                continue
            if test_id not in tests:
                tests[test_id] = Test(name=test_id)
                stacks[test_id] = []
            test = tests[test_id]
            stack = stacks[test_id]

            if kind == "test.start":
                test.file = doc.get("file") or ""
                test.nodeid = doc.get("nodeid") or test_id
                test.markers = tuple(doc.get("markers") or ())
                plan = doc.get("plan") or {}
                test.plan_id = plan.get("id") or ""
                test.plan_path = plan.get("path") or ""
                test.claim_ids = tuple(doc.get("claims") or ())
                test.start = parse_ts(doc.get("ts"))
            elif kind == "test.end":
                test.status = doc.get("status") or "pass"
                test.duration_ms = float(doc.get("duration_ms") or 0.0)
                test.stop = parse_ts(doc.get("ts"))
                if doc.get("pack"):
                    test.pack_dir = doc["pack"]
            elif kind == "step.start":
                stack.append(
                    Step(
                        step=str(doc.get("step") or ""),
                        intent=doc.get("intent") or "",
                        target=doc.get("target"),
                        start=parse_ts(doc.get("ts")),
                    )
                )
            elif kind == "step.end":
                step = _pop_step(stack, str(doc.get("step") or ""))
                step.status = doc.get("status") or "ok"
                step.duration_ms = float(doc.get("duration_ms") or 0.0)
                step.error = doc.get("error")
                step.stop = parse_ts(doc.get("ts"))
                (stack[-1].substeps if stack else test.steps).append(step)
            elif kind == "oracle":
                run_oracle = {k: v for k, v in doc.items() if k not in ("v", "run", "seq", "kind")}
                test.oracles.append(run_oracle)
            elif kind == "pack":
                test.pack_dir = doc.get("dir") or test.pack_dir
                test.pack_sections = doc.get("sections_est_tokens") or {}
                test.error = doc.get("error") or test.error

        run.tests = list(tests.values())
        return run


def _pop_step(stack: list[Step], step_id: str) -> Step:
    """Take the open step this ``step.end`` closes.

    Normally the innermost one. A ledger truncated by a killed process can carry an
    end whose start is missing or out of order — in that case synthesise a step
    instead of dropping the event, because a partial ledger is exactly the situation
    evidence exists for.
    """
    for index in range(len(stack) - 1, -1, -1):
        if stack[index].step == step_id:
            step = stack.pop(index)
            # Anything left open above the closed step is orphaned; attach it as
            # children so no measured work disappears from the report.
            while len(stack) > index:
                step.substeps.insert(0, stack.pop())
            return step
    return Step(step=step_id)
