"""Allure TestOps test-plan selection.

A TestOps launch hands the job a plan of test cases to run. Real plans drift from the
code: a case renamed or deleted last week is still in a plan built last month. One such
entry must not cost the whole launch its results, so by default an unresolved entry is
reported (terminal warning, ``testplan.unresolved`` ledger event, export and
``ci evaluate``) while every resolvable entry runs. ``unresolved="fail"`` keeps the
strict behaviour for pipelines that want it. A plan in which nothing resolves still
fails in both modes: a typo must not become a green run of zero tests.

An entry selects by ``id`` (the ``ALLURE_ID`` of every variant that carries it), or by
``selector`` in one of three forms: an allure-pytest ``fullName``
(``package.module#test`` — every variant, since allure-pytest names are
parameter-free), an exact pytest nodeid (one variant), or
``testence://<project>/<case>/<variant>``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

ALLURE_TESTPLAN_ENV = "ALLURE_TESTPLAN_PATH"
TESTPLAN_VERSION = "1.0"
UNRESOLVED_POLICIES = ("warn", "fail")


class TestPlanError(ValueError):
    pass


@dataclass(frozen=True)
class TestPlanEntry:
    id: str | None = None
    selector: str | None = None

    def describe(self) -> dict[str, str]:
        return {
            **({"id": self.id} if self.id is not None else {}),
            **({"selector": self.selector} if self.selector is not None else {}),
        }


@dataclass(frozen=True)
class TestPlan:
    version: str
    tests: tuple[TestPlanEntry, ...]
    #: Fields this reader does not know. Ignored, and reported, so that a TestOps
    #: release adding one does not break every launch.
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class SelectionCandidate:
    nodeid: str
    project_id: str
    case_id: str
    variant_id: str
    allure_id: str | None = None
    full_name: str | None = None

    @property
    def namespaced_selector(self) -> str:
        return f"testence://{self.project_id}/{self.case_id}/{self.variant_id}"


@dataclass(frozen=True)
class Selection:
    selected: frozenset[int]
    unresolved: tuple[TestPlanEntry, ...] = field(default_factory=tuple)


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
    warnings: list[str] = []
    unknown = sorted(set(value) - {"version", "tests"})
    if unknown:
        warnings.append("ignored unknown Allure test plan field(s): " + ", ".join(unknown))
    if value.get("version") != TESTPLAN_VERSION:
        raise TestPlanError(f"Allure test plan version must be {TESTPLAN_VERSION!r}")
    raw_tests = value.get("tests")
    if not isinstance(raw_tests, list):
        raise TestPlanError("Allure test plan tests must be an array")
    entries: list[TestPlanEntry] = []
    seen: set[tuple[str | None, str | None]] = set()
    ignored_entry_fields: set[str] = set()
    for index, raw_entry in enumerate(raw_tests):
        path_label = f"Allure test plan tests[{index}]"
        if not isinstance(raw_entry, dict):
            raise TestPlanError(f"{path_label} must be an object")
        ignored_entry_fields.update(set(raw_entry) - {"id", "selector"})
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
            # A repeated entry selects nothing new; it is not worth failing a launch.
            continue
        seen.add(key)
        entries.append(entry)
    if ignored_entry_fields:
        warnings.append(
            "ignored unknown Allure test plan entry field(s): "
            + ", ".join(sorted(ignored_entry_fields))
        )
    return TestPlan(TESTPLAN_VERSION, tuple(entries), tuple(warnings))


def _matches(entry: TestPlanEntry, candidate: SelectionCandidate) -> bool:
    if entry.id is not None and candidate.allure_id == entry.id:
        return True
    if entry.selector is None:
        return False
    return entry.selector in {
        candidate.nodeid.replace("\\", "/"),
        candidate.namespaced_selector,
        *((candidate.full_name,) if candidate.full_name else ()),
    }


def resolve(
    plan: TestPlan, candidates: list[SelectionCandidate], *, unresolved: str = "warn"
) -> Selection:
    """Indices of the candidates a plan selects, and the entries that matched none."""
    if unresolved not in UNRESOLVED_POLICIES:
        raise TestPlanError(f"unresolved policy must be one of {', '.join(UNRESOLVED_POLICIES)}")
    selected: set[int] = set()
    missing: list[TestPlanEntry] = []
    for entry in plan.tests:
        matches = [
            index for index, candidate in enumerate(candidates) if _matches(entry, candidate)
        ]
        if matches:
            selected.update(matches)
        else:
            missing.append(entry)
    if missing and unresolved == "fail":
        first = missing[0]
        raise TestPlanError(
            f"{len(missing)} Allure test plan entr{'y' if len(missing) == 1 else 'ies'} "
            f"did not resolve (first: id={first.id!r}, selector={first.selector!r})"
        )
    if plan.tests and not selected:
        raise TestPlanError(
            f"no Allure test plan entry resolved to a collected test ({len(missing)} entries); "
            "check the plan against this job's test paths"
        )
    return Selection(frozenset(selected), tuple(missing))


def select_candidates(plan: TestPlan, candidates: list[SelectionCandidate]) -> set[int]:
    """Strict selection: every entry must resolve. Kept for callers of 0.1.0a1."""
    return set(resolve(plan, candidates, unresolved="fail").selected)
