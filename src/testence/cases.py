"""Manual cases against tests and results: which case has a test, and how it went.

A team that keeps its cases in Markdown files (the format ``testence plan skeleton``
reads) binds a test to the cases it automates through the existing marker:

```python
@pytest.mark.testence(tms={"cases": ["SHOP-12/3", "SHOP-12/4"]})
def test_checkout_charges_once(ex): ...
```

``testence.json`` says where the files are and how a file names its key:

```json
"cases": {"paths": ["cases/*.md"], "key": "^[A-Z][A-Z0-9]*-[0-9]+"}
```

A case's id is ``<key>/<number>``: the key matched at the start of the file name, or
the whole file name without its extension when the pattern does not match. The
command lists every case of the files with its tests and their outcome in a run (or,
without a run, in a collection), counts the automated cases per file, and fails when a
marker names a case no file has: an id that points nowhere is a link that went stale.
"""

from __future__ import annotations

import glob
import json
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from testence.skeleton import SkeletonError, parse_cases, read_utf8

#: The ``tms`` system that carries manual case ids.
SYSTEM = "cases"
DEFAULT_KEY = r"^[A-Z][A-Z0-9]*-[0-9]+"
SCHEMA = "testence/cases/1"
_PRIORITY = re.compile(r"^\s*[-*]\s*(?:Priority|Приоритет)\s*:\s*(.+?)\s*$", re.IGNORECASE)
_REMOVED = re.compile(r"^\s*[-*]\s*(?:Removed|Deleted|Удал[её]н)[^:]*:", re.IGNORECASE)
#: Outcomes ordered from worst: a case with several tests shows the worst of them.
_RANK = ("broken", "failed", "aborted", "not_run", "skipped", "passed")


class CasesError(ValueError):
    """The configuration or a case file cannot be read."""


@dataclass(frozen=True)
class CasesConfig:
    paths: tuple[str, ...]
    key: str = DEFAULT_KEY


@dataclass
class ManualCase:
    id: str
    file: str
    number: int
    title: str
    priority: str | None = None
    removed: bool = False
    tests: list[dict[str, str]] = field(default_factory=list)

    @property
    def outcome(self) -> str:
        """The worst outcome of its tests, ``not_automated`` without a test."""
        if not self.tests:
            return "not_automated"
        statuses = [test.get("status") or "collected" for test in self.tests]
        ranked = [status for status in _RANK if status in statuses]
        return ranked[0] if ranked else statuses[0]


def parse_config(value: Any) -> CasesConfig | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = {"paths": [value]}
    if not isinstance(value, dict):
        raise CasesError("cases must be an object with paths")
    unknown = sorted(set(value) - {"paths", "key"})
    if unknown:
        raise CasesError(f"cases has unknown key {unknown[0]!r}")
    paths = value.get("paths")
    if isinstance(paths, str):
        paths = [paths]
    if not isinstance(paths, list) or not paths or not all(isinstance(p, str) and p for p in paths):
        raise CasesError("cases.paths must be a non-empty list of file patterns")
    key = value.get("key", DEFAULT_KEY)
    if not isinstance(key, str) or not key:
        raise CasesError("cases.key must be a regular expression")
    try:
        re.compile(key)
    except re.error as exc:
        raise CasesError(f"cases.key is not a regular expression: {exc}") from exc
    return CasesConfig(paths=tuple(paths), key=key)


def _file_key(path: Path, pattern: str) -> str:
    match = re.match(pattern, path.name)
    return match.group(0) if match else path.stem


def _meta(lines: list[str], start: int, stop: int) -> tuple[str | None, bool]:
    priority: str | None = None
    removed = False
    for line in lines[start:stop]:
        if line.lstrip().startswith("#") and line is not lines[start]:
            break
        if priority is None and (found := _PRIORITY.match(line)):
            priority = found.group(1)
        if _REMOVED.match(line):
            removed = True
    return priority, removed


def load_cases(config: CasesConfig, root: Path) -> tuple[list[ManualCase], list[str]]:
    """Every case of the configured files, and the files that could not be read."""
    files: list[Path] = []
    for pattern in config.paths:
        joined = pattern if Path(pattern).is_absolute() else str(root / pattern)
        files.extend(Path(found) for found in sorted(glob.glob(joined, recursive=True)))
    cases: list[ManualCase] = []
    problems: list[str] = []
    seen: dict[str, str] = {}
    for path in dict.fromkeys(files):
        try:
            text = read_utf8(path, CasesError)
            _, parsed = parse_cases(text)
        except (CasesError, SkeletonError, OSError) as exc:
            problems.append(f"{path}: {exc}")
            continue
        lines = text.splitlines()
        key = _file_key(path, config.key)
        starts = [case.line for case in parsed]
        for index, case in enumerate(parsed):
            stop = starts[index + 1] - 1 if index + 1 < len(starts) else len(lines)
            priority, removed = _meta(lines, case.line - 1, stop)
            case_id = f"{key}/{case.number}"
            if case_id in seen:
                problems.append(f"{path}: case {case_id} is also in {seen[case_id]}")
                continue
            seen[case_id] = str(path)
            cases.append(
                ManualCase(
                    id=case_id,
                    file=path.name,
                    number=case.number,
                    title=case.title,
                    priority=priority,
                    removed=removed,
                )
            )
    if not files:
        problems.append("no case file matches " + ", ".join(config.paths))
    return cases, problems


def tests_from_run(run_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """The tests of a run with their case ids and outcome, and the target's build."""
    from testence.export._model import LoadedRun
    from testence.metrics import load_run

    run = LoadedRun.from_events(load_run(run_dir), run_dir)
    tests = [
        {"nodeid": test.nodeid, "status": test.status, "cases": list(test.tms.get(SYSTEM, ()))}
        for test in run.tests
    ]
    return tests, run.target_start


def tests_from_collection(project: Path, pytest_args: list[str]) -> list[dict[str, Any]]:
    """The collected tests with their case ids, without running any of them."""
    from testence._process import run_owned

    with tempfile.TemporaryDirectory(prefix="testence-cases-") as temporary:
        out = Path(temporary) / "cases.json"
        result = run_owned(
            [
                sys.executable,
                "-m",
                "testence.cases_collect",
                "--out",
                str(out),
                "--",
                *pytest_args,
                # A collection runs nothing: its ledger is not a run of the project.
                "--testence-runs-root",
                str(Path(temporary) / "runs"),
            ],
            cwd=project,
            timeout=300,
            output_limit=4_000,
        )
        if not out.is_file():
            tail = (result.stdout + result.stderr).strip()[-1_500:]
            raise CasesError(f"collection did not complete:\n{tail}")
        return list(json.loads(out.read_text(encoding="utf-8"))["tests"])


def report(
    cases: list[ManualCase],
    tests: list[dict[str, Any]],
    *,
    problems: list[str] = (),  # type: ignore[assignment]
    target: dict[str, Any] | None = None,
    source: str = "",
) -> dict[str, Any]:
    by_id = {case.id: case for case in cases}
    unknown: list[dict[str, str]] = []
    for test in tests:
        for case_id in test.get("cases", ()):
            case = by_id.get(case_id)
            if case is None:
                unknown.append({"case": case_id, "nodeid": test["nodeid"]})
                continue
            case.tests.append({"nodeid": test["nodeid"], "status": test.get("status", "")})
    files: dict[str, dict[str, int]] = {}
    for case in cases:
        if case.removed:
            continue
        counts = files.setdefault(case.file, {"cases": 0, "automated": 0})
        counts["cases"] += 1
        counts["automated"] += bool(case.tests)
    return {
        "schema": SCHEMA,
        "source": source,
        "target": target,
        "files": files,
        "cases": [
            {
                "id": case.id,
                "file": case.file,
                "title": case.title,
                "priority": case.priority,
                "removed": case.removed,
                "tests": case.tests,
                "outcome": case.outcome,
            }
            for case in cases
        ],
        "unknown": unknown,
        "problems": list(problems),
    }


def _cell(text: Any) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def render_markdown(result: dict[str, Any]) -> str:
    """One table per case file: case, title, priority, tests and outcome."""
    from testence.target_info import describe

    lines = [f"### Manual cases{' in ' + result['source'] if result['source'] else ''}", ""]
    if result.get("target"):
        lines += [f"Target: {_cell(describe(result['target']))}", ""]
    by_file: dict[str, list[dict[str, Any]]] = {}
    for case in result["cases"]:
        by_file.setdefault(case["file"], []).append(case)
    for name, cases in by_file.items():
        counts = result["files"].get(name, {"cases": 0, "automated": 0})
        lines += [
            f"#### {name}: {counts['automated']} of {counts['cases']} automated",
            "",
            "| Case | Title | Priority | Tests | Outcome |",
            "|---|---|---|---|---|",
        ]
        for case in cases:
            if case["removed"]:
                continue
            tests = "<br>".join(f"`{_cell(t['nodeid'])}`" for t in case["tests"]) or "—"
            lines.append(
                f"| {case['id']} | {_cell(case['title'])} | {_cell(case['priority'] or '')} "
                f"| {tests} | {case['outcome']} |"
            )
        lines.append("")
    if result["unknown"]:
        lines += ["**Markers naming a case no file has:**", ""]
        lines += [f"- `{item['case']}` in `{_cell(item['nodeid'])}`" for item in result["unknown"]]
        lines.append("")
    if result["problems"]:
        lines += ["**Case files that could not be read:**", ""]
        lines += [f"- {_cell(problem)}" for problem in result["problems"]]
        lines.append("")
    return "\n".join(lines)


def render_text(result: dict[str, Any]) -> str:
    lines = []
    for name, counts in result["files"].items():
        lines.append(f"{name}: {counts['automated']} of {counts['cases']} cases automated")
    outcomes: dict[str, int] = {}
    for case in result["cases"]:
        if not case["removed"]:
            outcomes[case["outcome"]] = outcomes.get(case["outcome"], 0) + 1
    if outcomes:
        lines.append("outcomes: " + ", ".join(f"{n} {k}" for k, n in sorted(outcomes.items())))
    for item in result["unknown"]:
        lines.append(f"unknown case {item['case']} in {item['nodeid']}")
    for problem in result["problems"]:
        lines.append(f"unreadable: {problem}")
    return "\n".join(lines)
