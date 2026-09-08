"""Fail-closed Allure TestOps test-plan selection."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

ALLURE_TESTPLAN_ENV = "ALLURE_TESTPLAN_PATH"
TESTPLAN_VERSION = "1.0"


class TestPlanError(ValueError):
    pass


@dataclass(frozen=True)
class TestPlanEntry:
    id: str | None = None
    selector: str | None = None


@dataclass(frozen=True)
class TestPlan:
    version: str
    tests: tuple[TestPlanEntry, ...]


@dataclass(frozen=True)
class SelectionCandidate:
    nodeid: str
    project_id: str
    case_id: str
    variant_id: str
    allure_id: str | None = None

    @property
    def namespaced_selector(self) -> str:
        return f"testence://{self.project_id}/{self.case_id}/{self.variant_id}"


def load_testplan(path: Path | str) -> TestPlan:
    source = Path(path)
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise TestPlanError(f"cannot read Allure test plan {source}: {exc}") from exc
    if len(raw) > 1_048_576:
        raise TestPlanError("Allure test plan exceeds 1 MiB")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TestPlanError(f"invalid Allure test plan JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise TestPlanError("Allure test plan must be an object")
    unknown = sorted(set(value) - {"version", "tests"})
    if unknown:
        raise TestPlanError("unknown Allure test plan field(s): " + ", ".join(unknown))
    if value.get("version") != TESTPLAN_VERSION:
        raise TestPlanError(f"Allure test plan version must be {TESTPLAN_VERSION!r}")
    raw_tests = value.get("tests")
    if not isinstance(raw_tests, list):
        raise TestPlanError("Allure test plan tests must be an array")
    entries: list[TestPlanEntry] = []
    seen: set[tuple[str | None, str | None]] = set()
    for index, raw_entry in enumerate(raw_tests):
        path_label = f"Allure test plan tests[{index}]"
        if not isinstance(raw_entry, dict):
            raise TestPlanError(f"{path_label} must be an object")
        extra = sorted(set(raw_entry) - {"id", "selector"})
        if extra:
            raise TestPlanError(f"{path_label} has unknown field(s): {', '.join(extra)}")
        raw_id = raw_entry.get("id")
        if isinstance(raw_id, bool) or (raw_id is not None and not isinstance(raw_id, (str, int))):
            raise TestPlanError(f"{path_label}.id must be a string or integer")
        entry_id = str(raw_id).strip() if raw_id is not None else None
        selector_value = raw_entry.get("selector")
        if selector_value is not None and not isinstance(selector_value, str):
            raise TestPlanError(f"{path_label}.selector must be a string")
        selector = selector_value.strip().replace("\\", "/") if selector_value else None
        if not entry_id and not selector:
            raise TestPlanError(f"{path_label} requires id or selector")
        entry = TestPlanEntry(entry_id or None, selector)
        key = (entry.id, entry.selector)
        if key in seen:
            raise TestPlanError(f"{path_label} duplicates an earlier entry")
        seen.add(key)
        entries.append(entry)
    return TestPlan(TESTPLAN_VERSION, tuple(entries))


def select_candidates(plan: TestPlan, candidates: list[SelectionCandidate]) -> set[int]:
    selected: set[int] = set()
    for entry_index, entry in enumerate(plan.tests):
        matches = [
            index
            for index, candidate in enumerate(candidates)
            if (entry.id is not None and candidate.allure_id == entry.id)
            or (
                entry.selector is not None
                and entry.selector
                in {candidate.nodeid.replace("\\", "/"), candidate.namespaced_selector}
            )
        ]
        if not matches:
            raise TestPlanError(
                f"Allure test plan entry {entry_index} did not resolve: "
                f"id={entry.id!r}, selector={entry.selector!r}"
            )
        if len(matches) != 1:
            raise TestPlanError(f"Allure test plan entry {entry_index} is ambiguous")
        if matches[0] in selected:
            raise TestPlanError(
                f"Allure test plan entry {entry_index} overlaps an earlier selection"
            )
        selected.add(matches[0])
    return selected
