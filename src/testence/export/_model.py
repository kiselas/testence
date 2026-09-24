"""Parsed view of a ledger, shared by every exporter (ADR-0013).

Exporters receive this, never raw files: grouping, the step tree and timestamp
arithmetic happen once here, so writing a new exporter is a formatting exercise.

Every field is tolerant of absence. The input adapter maps legacy ``testence/1``
events into the ``testence/2`` reader model and marks missing proof unverified.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from testence.evidence.reconcile import reconcile_events
from testence.evidence.sanitize import DEFAULT_POLICY, RedactionPolicy, redact_document_text
from testence.status import execution_failed, normalize_execution_status

# Files an evidence pack may contain, in the order a reader should meet them:
# the machine index first, then the triage contract, then the raw sections.
PACK_FILES = (
    "pack.json",
    "manifest.json",
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

#: Which pack files an export may ship. ``minimal`` drops the sections most likely
#: to carry application data: raw traffic, the visible page text and pixels.
ATTACHMENT_POLICIES = ("full", "minimal", "none")
_MINIMAL_EXCLUDED = frozenset({"network.jsonl", "aria.txt", "screenshot.png"})
_TEXT_SUFFIXES = frozenset({".json", ".jsonl", ".txt", ".md"})

#: Media types for shipped pack files. ``.jsonl`` has no registered type a report
#: viewer renders; text/plain keeps it readable in the browser.
MIME_TYPES = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".json": "application/json",
    ".jsonl": "text/plain",
    ".png": "image/png",
    ".zip": "application/zip",
    ".webm": "video/webm",
}


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
class FixturePhase:
    name: str
    status: str
    duration_ms: float = 0.0
    start: datetime | None = None
    stop: datetime | None = None
    error: str | None = None


@dataclass
class Test:
    """One test case as the ledger saw it."""

    name: str
    project_id: str = ""
    case_id: str = ""
    variant_id: str = "default"
    attempt_id: str = ""
    proof_id: str = ""
    parameters: dict[str, str] = field(default_factory=dict)
    nodeid: str = ""
    file: str = ""
    markers: tuple[str, ...] = ()
    allure_id: str = ""
    owner: str = ""
    risk: str = ""
    requirements: tuple[dict[str, str], ...] = ()
    issues: tuple[dict[str, str], ...] = ()
    plan_id: str = ""
    plan_path: str = ""
    claim_ids: tuple[str, ...] = ()
    status: str = "not_run"
    assurance: str = "unverified"
    assurance_reasons: tuple[str, ...] = ()
    phase: str = ""
    duration_ms: float = 0.0
    start: datetime | None = None
    stop: datetime | None = None
    error: str | None = None
    steps: list[Step] = field(default_factory=list)
    fixtures: list[FixturePhase] = field(default_factory=list)
    oracles: list[dict[str, Any]] = field(default_factory=list)
    pack_dir: str | None = None
    pack_sections: dict[str, int] = field(default_factory=dict)
    #: allure-pytest-compatible identity and declared metadata (``test.start.allure``).
    allure: dict[str, Any] = field(default_factory=dict)
    #: ``assertion``/``oracle`` (the product disagreed) or ``infrastructure``/``test_code``.
    error_kind: str = ""
    #: Bounded, redacted pytest failure representation.
    error_trace: str = ""
    #: Run-relative screenshot of a passing test (``evidence.screenshots: always``).
    screenshot: str = ""
    #: Test-management case ids by system (``testrail``, ``xray``, ...), as declared.
    tms: dict[str, tuple[str, ...]] = field(default_factory=dict)
    #: Playwright trace and video files (``evidence.trace``/``video``), stored raw.
    recordings: list[dict[str, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.nodeid:
            self.nodeid = self.name

    @property
    def failed(self) -> bool:
        return execution_failed(self.status)


@dataclass
class LoadedRun:
    """A whole run: what the exporters format.

    ``events`` stays available as an escape hatch, but an exporter reaching for it
    is a signal that this model is missing a view the format genuinely needs.
    """

    run_id: str = ""
    project_id: str = ""
    schema: str = ""
    testence_version: str = ""
    fingerprint: dict[str, Any] = field(default_factory=dict)
    start: datetime | None = None
    stop: datetime | None = None
    duration_ms: float = 0.0
    run_status: str = "unknown"
    #: ``allure-pytest`` (default) or ``nodeid``, as the run recorded it.
    allure_naming: str = "allure-pytest"
    #: ``values`` (redacted display values, default) or ``digest``.
    allure_parameters: str = "values"
    integrity_errors: list[dict[str, str]] = field(default_factory=list)
    #: Allure test plan entries that matched no collected test (``testplan.unresolved``).
    testplan_unresolved: list[dict[str, str]] = field(default_factory=list)
    tests: list[Test] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    run_dir: Path = Path()
    redaction_policy: RedactionPolicy = DEFAULT_POLICY
    attachments: str = "full"

    @property
    def passed(self) -> int:
        return sum(1 for test in self.tests if test.status == "passed")

    @property
    def failed(self) -> int:
        return sum(1 for test in self.tests if execution_failed(test.status))

    @property
    def skipped(self) -> int:
        return sum(1 for test in self.tests if test.status == "skipped")

    @property
    def pending(self) -> int:
        return sum(1 for test in self.tests if test.status == "not_run")

    @property
    def other(self) -> int:
        known = {
            "passed",
            "failed",
            "broken",
            "aborted",
            "skipped",
            "not_run",
        }
        return sum(1 for test in self.tests if test.status not in known)

    def pack_path(self, test: Test, filename: str) -> Path | None:
        """Resolved in-run pack file, or None for missing, escaping or excluded paths."""
        if not test.pack_dir or not self.ships(filename):
            return None
        try:
            run_root = self.run_dir.resolve()
            pack_root = (self.run_dir / test.pack_dir).resolve()
            candidate = (pack_root / filename).resolve()
            pack_root.relative_to(run_root)
            candidate.relative_to(pack_root)
        except (OSError, RuntimeError, ValueError):
            return None
        return candidate if candidate.is_file() else None

    def run_file(self, relative: str) -> Path | None:
        """A file inside the run directory, or None for missing or escaping paths."""
        if not relative:
            return None
        try:
            run_root = self.run_dir.resolve()
            candidate = (self.run_dir / relative).resolve()
            candidate.relative_to(run_root)
        except (OSError, RuntimeError, ValueError):
            return None
        return candidate if candidate.is_file() else None

    def ships(self, filename: str) -> bool:
        """Whether the attachment policy lets an export carry this pack file."""
        if self.attachments == "none":
            return False
        return not (self.attachments == "minimal" and filename in _MINIMAL_EXCLUDED)

    def attachment_bytes(self, test: Test, filename: str) -> bytes | None:
        """A pack file as an export should ship it: redacted again with the run's
        policy (text files) or verbatim (images), or None when not shipped."""
        source = self.pack_path(test, filename)
        if source is None:
            return None
        raw = source.read_bytes()
        if source.suffix not in _TEXT_SUFFIXES:
            return raw
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None
        cleaned = redact_document_text(text, suffix=source.suffix, policy=self.redaction_policy)
        return raw if cleaned == text else cleaned.encode("utf-8")

    @classmethod
    def from_events(cls, events: list[dict[str, Any]], run_dir: Path | str = "") -> LoadedRun:
        events = reconcile_events(events)
        run = cls(events=events, run_dir=Path(run_dir))
        tests: dict[str, Test] = {}
        # One open-step stack per test: under -n the ledgers of several workers are
        # merged by timestamp, so events of different tests legitimately interleave.
        stacks: dict[str, list[Step]] = {}
        aliases: dict[str, str] = {}

        for doc in events:
            kind = doc.get("kind")
            if kind == "run.start":
                run.run_id = doc.get("run_id") or doc.get("run", run.run_id)
                run.project_id = doc.get("project_id", run.project_id)
                run.schema = doc.get("v", run.schema)
                run.testence_version = doc.get("testence", "")
                run.fingerprint = doc.get("fingerprint") or {}
                if doc.get("allure_naming") in ("allure-pytest", "nodeid"):
                    run.allure_naming = str(doc["allure_naming"])
                if doc.get("allure_parameters") in ("values", "digest"):
                    run.allure_parameters = str(doc["allure_parameters"])
                run.start = run.start or parse_ts(doc.get("ts"))
                continue
            if kind == "run.end":
                run.stop = parse_ts(doc.get("ts"))
                run.duration_ms = float(doc.get("duration_ms") or 0.0)
                run.run_status = str(doc.get("run_status") or "unknown")
                run.integrity_errors = [
                    {str(key): str(value) for key, value in item.items()}
                    for item in doc.get("integrity_errors") or ()
                    if isinstance(item, dict)
                ]
                continue

            if kind == "testplan.unresolved":
                run.testplan_unresolved.extend(
                    {str(key): str(value) for key, value in entry.items()}
                    for entry in doc.get("entries") or ()
                    if isinstance(entry, dict)
                )
                continue

            raw_test_id = doc.get("test")
            if not raw_test_id:
                continue
            identity_parts = (
                doc.get("project_id"),
                doc.get("case_id"),
                doc.get("variant_id"),
                doc.get("attempt_id"),
            )
            identity_key = (
                "|".join(str(part) for part in identity_parts) if all(identity_parts) else ""
            )
            if kind == "test.start":
                test_id = identity_key or str(doc.get("nodeid") or raw_test_id)
                aliases[str(raw_test_id)] = test_id
            else:
                test_id = identity_key or str(
                    doc.get("nodeid") or aliases.get(str(raw_test_id)) or raw_test_id
                )
            if test_id not in tests:
                tests[test_id] = Test(name=str(doc.get("display_name") or raw_test_id))
                stacks[test_id] = []
            test = tests[test_id]
            stack = stacks[test_id]
            test.project_id = str(doc.get("project_id") or test.project_id)
            test.case_id = str(doc.get("case_id") or test.case_id)
            test.variant_id = str(doc.get("variant_id") or test.variant_id)
            test.attempt_id = str(doc.get("attempt_id") or test.attempt_id)
            test.proof_id = str(doc.get("proof_id") or test.proof_id)
            if isinstance(doc.get("parameters"), dict):
                test.parameters = {str(key): str(value) for key, value in doc["parameters"].items()}

            if kind == "test.start":
                test.name = str(doc.get("display_name") or test.name)
                test.file = doc.get("file") or ""
                test.nodeid = doc.get("nodeid") or test_id
                test.markers = tuple(doc.get("markers") or ())
                test.allure_id = str(doc.get("allure_id") or "")
                if isinstance(doc.get("allure"), dict):
                    test.allure = dict(doc["allure"])
                if isinstance(doc.get("tms"), dict):
                    test.tms = {
                        str(system): tuple(str(value) for value in values)
                        for system, values in doc["tms"].items()
                        if isinstance(values, list)
                    }
                test.owner = str(doc.get("owner") or "")
                test.risk = str(doc.get("risk") or "")
                test.requirements = _links(doc.get("requirements"))
                test.issues = _links(doc.get("issues"))
                plan = doc.get("plan") or {}
                test.plan_id = plan.get("id") or ""
                test.plan_path = plan.get("path") or ""
                test.claim_ids = tuple(doc.get("claims") or ())
                test.start = parse_ts(doc.get("ts"))
            elif kind == "test.phase":
                phase = str(doc.get("phase") or "")
                if phase in {"setup", "teardown"}:
                    stop = parse_ts(doc.get("ts"))
                    duration_ms = float(doc.get("duration_ms") or 0.0)
                    start = stop - timedelta(milliseconds=duration_ms) if stop else None
                    test.fixtures.append(
                        FixturePhase(
                            name=f"pytest {phase}",
                            status=normalize_execution_status(doc.get("status")),
                            duration_ms=duration_ms,
                            start=start,
                            stop=stop,
                            error=str(doc.get("error") or "") or None,
                        )
                    )
            elif kind == "test.end":
                test.name = str(doc.get("display_name") or test.name)
                test.nodeid = str(doc.get("nodeid") or test.nodeid or test_id)
                test.status = normalize_execution_status(doc.get("status"))
                test.assurance = str(doc.get("assurance") or "unverified")
                test.assurance_reasons = tuple(
                    str(reason) for reason in doc.get("assurance_reasons") or ()
                )
                test.phase = doc.get("phase") or ""
                test.duration_ms = float(doc.get("duration_ms") or 0.0)
                test.stop = parse_ts(doc.get("ts"))
                test.error = doc.get("error") or test.error
                test.error_kind = str(doc.get("error_kind") or test.error_kind)
                test.error_trace = str(doc.get("error_trace") or test.error_trace)
                if isinstance(doc.get("recordings"), list):
                    test.recordings = [
                        {str(key): str(value) for key, value in entry.items()}
                        for entry in doc["recordings"]
                        if isinstance(entry, dict) and entry.get("path")
                    ]
                test.screenshot = str(doc.get("screenshot") or test.screenshot)
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


@dataclass(frozen=True)
class ExportedFile:
    """A pack file an exporter copied next to its report."""

    name: str
    #: Path relative to the exporter's output directory.
    path: str
    media_type: str


def copy_attachments(run: LoadedRun, test: Test, out_dir: Path) -> list[ExportedFile]:
    """Copy a test's shippable evidence under ``out_dir/attachments/<test>/``.

    For exporters that reference files by path (JUnit, CTRF). Everything goes
    through :meth:`LoadedRun.attachment_bytes`, so the attachment policy and the
    export-time redaction apply exactly as they do for Allure — a report must never
    point at the raw pack of a run recorded before a redaction rule existed.
    """
    key = test.proof_id or test.nodeid or test.name
    folder = Path("attachments") / hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    shipped: list[tuple[str, bytes]] = []
    for filename in PACK_FILES:
        content = run.attachment_bytes(test, filename)
        if content is not None:
            shipped.append((filename, content))
    final = run.run_file(test.screenshot) if run.ships("screenshot.png") else None
    if final is not None:
        shipped.append(("final-screenshot.png", final.read_bytes()))
    # Trace and video are raw (redaction: none); only a full export ships them.
    if run.attachments == "full":
        for recording in test.recordings:
            source = run.run_file(recording.get("path", ""))
            if source is not None:
                shipped.append((source.name, source.read_bytes()))
    if test.oracles and run.attachments != "none":
        oracles = json.dumps(test.oracles, ensure_ascii=False, indent=1) + "\n"
        shipped.append(("oracles.json", oracles.encode("utf-8")))
    exported: list[ExportedFile] = []
    for filename, content in shipped:
        target = out_dir / folder / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        exported.append(
            ExportedFile(
                name=filename,
                path=(folder / filename).as_posix(),
                media_type=MIME_TYPES.get(Path(filename).suffix, "text/plain"),
            )
        )
    return exported


def _links(value: Any) -> tuple[dict[str, str], ...]:
    if not isinstance(value, list):
        return ()
    return tuple(
        {str(key): str(raw) for key, raw in item.items() if key in {"id", "url"}}
        for item in value
        if isinstance(item, dict) and item.get("id")
    )


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
