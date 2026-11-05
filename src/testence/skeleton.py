"""``testence plan skeleton``: a PlanSpec and pytest stubs from a Markdown case list.

Cases usually arrive as a Markdown file written for people: a table of numbered cases
with steps and expected results, or one section per case with numbered steps and
"Expected:" lines. Turning that into a plan and a test skeleton by hand is the same
typing every time, and it is where an expected value most easily drifts from its source.
This module does the typing and nothing else:

- one scenario per case, one claim and one required assertion per expected result, and
  ``expected`` is the text of the file, verbatim. A case with no expected result gets no
  scenario: it is reported as an open question, never given an invented outcome;
- one test function per case, bound to its claims, with a commented stub per step and a
  bound ``ex.expect_visible`` stub per expected result. Addresses are never guessed:
  each stub calls ``TODO(...)``, which fails the step at once until an author replaces it
  with a ``Target`` found by ``testence explore``.

Regeneration never destroys work. Every generated file records a digest of its own
content in its first line; a file whose content no longer matches (an author edited it)
or that has no such line is kept as it is.
"""

from __future__ import annotations

import hashlib
import json
import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .contracts import load_plan
from .contracts._validation import ContractError
from .contracts.plan import PLAN_SCHEMA

SKELETON_SCHEMA = "testence/plan-skeleton/1"
MARKER = "testence:skeleton"

#: Field limits of PlanSpec v2 (``contracts/plan.py``).
_TITLE_MAX = 200
_TEXT_MAX = 1000
_ID_MAX = 128


class SkeletonError(ValueError):
    """The case file cannot be turned into a plan without guessing."""


@dataclass
class Step:
    text: str
    expected: list[str] = field(default_factory=list)


@dataclass
class Case:
    number: int
    title: str
    line: int
    steps: list[Step] = field(default_factory=list)
    #: Expected results not attached to a step: emitted after the last step.
    expected: list[str] = field(default_factory=list)
    precondition: str | None = None
    postcondition: str | None = None
    #: Headed "Case N"/"Кейс N"; a bare "N. title" heading is a case only with outcomes.
    keyword: bool = True

    @property
    def all_expected(self) -> list[str]:
        return [item for step in self.steps for item in step.expected] + self.expected


# --------------------------------------------------------------------------- parsing

_CYRILLIC = re.compile(r"[а-яё]", re.IGNORECASE)
_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)
_INLINE_NUMBERED = re.compile(r"(?:(?<=\s)|^)\d{1,3}[.)]\s+")
_LEADING_MARK = re.compile(r"^\s*(?:[-*+•]\s+|\d{1,3}[.)]\s+)")

_EXPECTED_LABEL = (
    r"ожидается|ожидаемый результат|ожидаемые результаты|ожидание|"
    r"expected results?|expected|expectation"
)
_EXPECTED_LINE = re.compile(
    rf"^\s*(?:[-*+]\s+)?\**(?:{_EXPECTED_LABEL})\**\s*:\s*\**\s*(?P<rest>.*)$", re.IGNORECASE
)
_EXPECTED_INLINE = re.compile(rf"\s*\**(?:{_EXPECTED_LABEL})\**\s*:\s*", re.IGNORECASE)
_ARROW_LINE = re.compile(r"^\s*(?:[-*+]\s+)?(?:→|->|=>)\s*(?P<rest>.+)$")
_STEPS_LABEL = re.compile(
    r"^\s*(?:[-*+]\s+)?\**(?:шаги|шаги воспроизведения|steps|actions|действия)\**\s*:\s*\**\s*(?P<rest>.*)$",
    re.IGNORECASE,
)
_PRE_LABEL = re.compile(
    r"^\s*(?:[-*+]\s+)?\**(?:предусловия?|preconditions?)\**\s*:\s*\**\s*(?P<rest>.*)$",
    re.IGNORECASE,
)
_POST_LABEL = re.compile(
    r"^\s*(?:[-*+]\s+)?\**(?:постусловия?|postconditions?|cleanup|уборка)\**\s*:\s*\**\s*(?P<rest>.*)$",
    re.IGNORECASE,
)
_META_LINE = re.compile(r"^\s*[-*+]\s+\**[^:\n]{1,40}\**\s*:\s")
_NUMBERED = re.compile(r"^(?P<indent>\s{0,3})(?P<n>\d{1,3})[.)]\s+(?P<rest>.+)$")
_BULLET = re.compile(r"^\s*[-*+]\s+(?P<rest>.+)$")
_HEADING = re.compile(r"^(?P<level>#{1,6})\s+(?P<text>.+?)\s*#*\s*$")
_CASE_HEADING = re.compile(
    r"^(?:(?:кейс|тест-кейс|тесткейс|сценарий|case|test case|testcase|scenario|tc)\s*"
    r"(?:№\s*)?(?P<kn>\d{1,4})\s*(?:[.:)—–-]\s*)?|(?P<n>\d{1,4})\s*[.):—–-](?!\d)\s*)"
    r"(?P<title>.*)$",
    re.IGNORECASE,
)

_COLUMNS: dict[str, frozenset[str]] = {
    "number": frozenset({"#", "№", "n", "no", "nr", "id", "номер", "n°"}),
    "title": frozenset(
        {"название", "наименование", "кейс", "тест-кейс", "сценарий", "title", "name", "case"}
    ),
    "steps": frozenset({"шаги", "шаг", "действия", "steps", "step", "actions"}),
    "expected": frozenset(
        {
            "ожидаемый результат",
            "ожидаемые результаты",
            "ожидается",
            "результат",
            "expected",
            "expected result",
            "expected results",
        }
    ),
    "precondition": frozenset({"предусловие", "предусловия", "precondition", "preconditions"}),
}


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _split_items(cell: str) -> list[str]:
    """Items of one table cell: ``<br>`` lines, or inline ``1. … 2. …`` numbering."""
    parts = [part for part in _BR.split(cell) if part.strip()]
    if len(parts) == 1 and len(_INLINE_NUMBERED.findall(parts[0])) > 1:
        parts = [part for part in _INLINE_NUMBERED.split(parts[0]) if part.strip()]
    return [_clean(_LEADING_MARK.sub("", part)) for part in parts if _clean(part)]


def _table_cells(line: str) -> list[str]:
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    cells = re.split(r"(?<!\\)\|", body)
    return [cell.replace("\\|", "|").strip() for cell in cells]


def _column_role(header: str) -> str | None:
    name = _clean(header.strip("*_` ")).casefold()
    for role, names in _COLUMNS.items():
        if name in names:
            return role
    return None


def _parse_table(lines: list[str]) -> list[Case]:
    index = 0
    while index < len(lines) - 1:
        line = lines[index]
        separator = lines[index + 1].strip()
        if line.lstrip().startswith("|") and re.fullmatch(
            r"\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?", separator
        ):
            roles = [_column_role(cell) for cell in _table_cells(line)]
            if "steps" in roles and "expected" in roles:
                return _table_rows(lines, index, roles)
        index += 1
    return []


def _table_rows(lines: list[str], header: int, roles: list[str | None]) -> list[Case]:
    cases: list[Case] = []
    row = header + 2
    while row < len(lines) and lines[row].lstrip().startswith("|"):
        cells = _table_cells(lines[row])
        values = {
            role: cells[position]
            for position, role in enumerate(roles)
            if role is not None and position < len(cells)
        }
        number_text = re.sub(r"\D", "", values.get("number", ""))
        number = int(number_text) if number_text else len(cases) + 1
        steps = [Step(text) for text in _split_items(values.get("steps", ""))]
        title = _clean(_BR.sub(" ", values.get("title", ""))) or (
            steps[0].text if steps else f"#{number}"
        )
        precondition = _clean(_BR.sub(" ", values.get("precondition", ""))) or None
        if any(values.values()):
            cases.append(
                Case(
                    number=number,
                    title=title,
                    line=row + 1,
                    steps=steps,
                    expected=_split_items(values.get("expected", "")),
                    precondition=precondition,
                )
            )
        row += 1
    return cases


def _parse_sections(lines: list[str]) -> list[Case]:
    cases: list[Case] = []
    current: Case | None = None
    case_level = 0
    mode = "steps"  # or "expected" after a bare "Expected:" label
    last_kind = ""  # what a continuation line extends: step, expected, pre, post

    def add_expected(case: Case, text: str) -> None:
        nonlocal last_kind
        text = _clean(text)
        if not text:
            return
        if case.steps and mode == "steps":
            case.steps[-1].expected.append(text)
        else:
            case.expected.append(text)
        last_kind = "expected"

    def add_step(case: Case, text: str) -> None:
        nonlocal last_kind
        head, *tail = _EXPECTED_INLINE.split(text, maxsplit=1)
        case.steps.append(Step(_clean(head)))
        last_kind = "step"
        if tail and _clean(tail[0]):
            case.steps[-1].expected.append(_clean(tail[0]))
            last_kind = "expected"

    for number, raw in enumerate(lines, start=1):
        heading = _HEADING.match(raw)
        if heading:
            level = len(heading.group("level"))
            match = _CASE_HEADING.match(heading.group("text").strip())
            if level >= 2 and match:
                current = Case(
                    number=int(match.group("kn") or match.group("n")),
                    title=_clean(match.group("title")) or heading.group("text").strip(),
                    line=number,
                    keyword=match.group("kn") is not None,
                )
                cases.append(current)
                case_level, mode, last_kind = level, "steps", ""
                continue
            if current is not None and level <= case_level:
                current = None
            continue
        if current is None or not raw.strip():
            if not raw.strip():
                last_kind = "" if last_kind in {"pre", "post"} else last_kind
            continue
        if label := _STEPS_LABEL.match(raw):
            mode, last_kind = "steps", ""
            if label.group("rest").strip():
                add_step(current, label.group("rest"))
            continue
        if label := _EXPECTED_LINE.match(raw):
            rest = label.group("rest").strip()
            if rest:
                add_expected(current, rest)
            else:
                mode = "expected"
            continue
        if label := _ARROW_LINE.match(raw):
            add_expected(current, label.group("rest"))
            continue
        if label := _PRE_LABEL.match(raw):
            current.precondition = _clean(label.group("rest")) or None
            last_kind = "pre"
            continue
        if label := _POST_LABEL.match(raw):
            current.postcondition = _clean(label.group("rest")) or None
            last_kind = "post"
            continue
        numbered = _NUMBERED.match(raw)
        bullet = _BULLET.match(raw)
        item = numbered or bullet
        if mode == "expected" and item is not None:
            add_expected(current, item.group("rest"))
            continue
        if numbered:
            add_step(current, numbered.group("rest"))
            continue
        if _META_LINE.match(raw) and not current.steps:
            last_kind = ""  # "- Priority: High" above the steps is metadata
            continue
        if bullet is not None and not (raw.startswith(("  ", "	")) and current.steps):
            # "- Open the page" is a step; an indented bullet under a step details it.
            add_step(current, bullet.group("rest"))
            continue
        if raw.startswith((" ", "\t")) and last_kind:
            # A wrapped line continues whatever it is indented under.
            text = _clean(raw)
            if last_kind == "step" and current.steps:
                current.steps[-1].text = f"{current.steps[-1].text} {text}"
            elif last_kind == "expected":
                bucket = (
                    current.steps[-1].expected
                    if current.steps and current.steps[-1].expected and mode == "steps"
                    else current.expected
                )
                if bucket:
                    bucket[-1] = f"{bucket[-1]} {text}"
            elif last_kind == "pre" and current.precondition:
                current.precondition = f"{current.precondition} {text}"
            elif last_kind == "post" and current.postcondition:
                current.postcondition = f"{current.postcondition} {text}"
    return cases


def parse_cases(text: str) -> tuple[str, list[Case]]:
    """Return the detected format (``table`` or ``sections``) and the cases."""
    lines = text.splitlines()
    cases = _parse_table(lines)
    kind = "table"
    if not cases:
        # "## 3. Overview" is a numbered section, not a case, unless it states an outcome.
        cases = [case for case in _parse_sections(lines) if case.keyword or case.all_expected]
        kind = "sections"
    if not cases:
        raise SkeletonError(
            "no cases found: expected a table with steps and expected-result columns, "
            "or sections headed '## Case N — title' / '### N. title' with numbered steps"
        )
    seen: dict[int, int] = {}
    for case in cases:
        if case.number in seen:
            raise SkeletonError(
                f"case number {case.number} appears twice (lines {seen[case.number]} and "
                f"{case.line}); case numbers become stable case IDs and must be unique"
            )
        seen[case.number] = case.line
    return kind, cases


# --------------------------------------------------------------------------- naming

_TRANSLIT = str.maketrans(
    {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
        "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
        "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts",
        "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu",
        "я": "ya",
    }
)  # fmt: skip


def slug(value: str, *, separator: str = "-", limit: int = 40) -> str:
    """ASCII slug of ``value``; Cyrillic is transliterated so names stay readable."""
    ascii_text = value.casefold().translate(_TRANSLIT)
    words = re.findall(r"[a-z0-9]+", ascii_text)
    result = ""
    for word in words:
        candidate = f"{result}{separator}{word}" if result else word
        if len(candidate) > limit:
            break
        result = candidate
    return result or (words[0][:limit] if words else "")


def _truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def _py(value: str) -> str:
    """A Python string literal quoted the way ``ruff format`` would quote it."""
    if '"' in value and "'" not in value:
        return repr(value)
    return json.dumps(value, ensure_ascii=False)  # JSON string syntax is valid Python


@dataclass(frozen=True)
class _Ids:
    plan_id: str

    def case(self, case: Case) -> str:
        return f"case-{case.number}"

    def claim(self, case: Case, index: int) -> str:
        return f"{self.plan_id}.case-{case.number}.expected-{index}"[:_ID_MAX]

    def assertion(self, case: Case, index: int) -> str:
        return f"assert.case-{case.number}.expected-{index}"


# --------------------------------------------------------------------------- plan


def build_plan(
    cases: list[Case],
    *,
    project_id: str,
    plan_id: str,
    title: str,
    source: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """PlanSpec v2 document and the open questions for cases without an outcome."""
    ids = _Ids(plan_id)
    claims: list[dict[str, Any]] = []
    assertions: list[dict[str, Any]] = []
    scenarios: list[dict[str, Any]] = []
    questions: list[dict[str, Any]] = []
    for case in cases:
        expected = case.all_expected
        if not expected:
            questions.append(
                {
                    "case": case.number,
                    "title": case.title,
                    "line": case.line,
                    "question": "the case states no expected result; no scenario until "
                    "its owner says what must be observed",
                }
            )
            continue
        bound: list[str] = []
        for index, text in enumerate(expected, start=1):
            if len(text) > _TEXT_MAX:
                raise SkeletonError(
                    f"case {case.number} expected result {index} is {len(text)} characters; "
                    f"PlanSpec keeps at most {_TEXT_MAX}. Split it in the source file"
                )
            claim_id = ids.claim(case, index)
            bound.append(claim_id)
            claims.append({"id": claim_id, "statement": text, "oracles": ["ui"]})
            assertions.append(
                {
                    "id": ids.assertion(case, index),
                    "claim_id": claim_id,
                    "oracle": "ui",
                    "required": True,
                    "expected": text,
                }
            )
        scenarios.append(
            {
                "id": ids.case(case),
                "title": _truncate(f"{case.number}. {case.title}", _TITLE_MAX),
                "claims": bound,
            }
        )
    if not scenarios:
        raise SkeletonError(
            "no case states an expected result, so there is nothing to prove; "
            "add 'Expected:' lines or an expected-result column"
        )
    plan = {
        "schema": PLAN_SCHEMA,
        "project_id": project_id,
        "id": plan_id,
        "title": _truncate(title, _TITLE_MAX),
        "source": _truncate(source, 500),
        "claims": claims,
        "assertions": assertions,
        "scenarios": scenarios,
    }
    return plan, questions


# --------------------------------------------------------------------------- tests

_ACTIONS: list[tuple[str, re.Pattern[str]]] = [
    (
        "observe",
        re.compile(
            r"^(посмотреть|осмотреть|проверить|убедиться|дождаться|подождать|обратить|"
            r"look|observe|verify|check that|ensure|wait|confirm that|inspect)\b",
            re.IGNORECASE,
        ),
    ),
    ("hover", re.compile(r"\b(навести|наведите|hover)", re.IGNORECASE)),
    (
        "uncheck",
        re.compile(r"\b(снять (галочку|флажок|отметку)|uncheck|untick)", re.IGNORECASE),
    ),
    (
        "check",
        re.compile(r"\b(отметить|поставить (галочку|флажок)|check the|tick)\b", re.IGNORECASE),
    ),
    ("select", re.compile(r"\b(выбрать|выберите|select|choose|pick)\b", re.IGNORECASE)),
    (
        "fill",
        re.compile(
            r"\b(ввести|введите|заполнить|заполните|указать|укажите|вписать|набрать|"
            r"type|enter|fill|input)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "click",
        re.compile(
            r"\b(нажать|нажмите|кликнуть|щ[её]лкнуть|открыть|откройте|перейти|удалить|"
            r"сохранить|click|press|tap|open|submit|delete|save)\b",
            re.IGNORECASE,
        ),
    ),
]
_KEY = re.compile(
    r"\b(?P<key>(?:(?:Ctrl|Control|Shift|Alt|Cmd|Meta)\+)+[A-Za-z0-9]+|Enter|Escape|Esc|"
    r"Tab|Backspace|F\d{1,2})\b"
)
_URL = re.compile(r"(?P<url>https?://\S+?|(?<![\w/])/[\w\-./?=&%#]*)(?=[`'\"»)\s,;]|$)")
_QUOTED = re.compile(r"«(?P<a>[^»]+)»|\"(?P<b>[^\"]+)\"|`(?P<c>[^`]+)`|“(?P<d>[^”]+)”")
_PRESS = re.compile(r"\b(press|hit|нажать|нажмите|клавиш)", re.IGNORECASE)
_KEY_NAMES = {"ctrl": "Control", "cmd": "Meta", "esc": "Escape"}


def _key(raw: str) -> str:
    return "+".join(_KEY_NAMES.get(part.casefold(), part) for part in raw.split("+"))


def _quoted(text: str) -> str | None:
    match = _QUOTED.search(text)
    if not match:
        return None
    return next(value for value in match.groups() if value)


def _comment(prefix: str, text: str, indent: str = "    ") -> list[str]:
    wrapped = textwrap.wrap(
        text, width=96 - len(indent) - 2, initial_indent=prefix, subsequent_indent="  "
    ) or [prefix]
    return [f"{indent}# {line}".rstrip() for line in wrapped]


def _call(name: str, args: list[str], indent: str = "    ") -> list[str]:
    one_line = f"{indent}ex.{name}({', '.join(args)})"
    if len(one_line) <= 100:
        return [one_line]
    return [f"{indent}ex.{name}("] + [f"{indent}    {arg}," for arg in args] + [f"{indent})"]


class _Words:
    def __init__(self, russian: bool) -> None:
        self.russian = russian

    def step(self, case: int, step: int) -> str:
        return f"кейс {case} ш.{step}" if self.russian else f"case {case} step {step}"

    def expected(self, case: int, index: int) -> str:
        return f"кейс {case} ож.{index}" if self.russian else f"case {case} expected {index}"


def _step_lines(case: Case, position: int, step: Step, words: _Words) -> list[str]:
    intent = _py(f"{words.step(case.number, position)}: {_truncate(step.text, 120)}")
    what = _py(_truncate(step.text, 60))
    lines = _comment(f"{position}. ", step.text)
    url = _URL.search(step.text)
    key = _KEY.search(step.text)
    if key and "+" not in key.group("key") and not _PRESS.search(step.text):
        key = None  # "Enter the name" types; "Press Enter" and "Ctrl+S" press a key
    # The key's own name must not pick the action: "Enter" is also a fill verb.
    verbs = _KEY.sub(" ", step.text) if key else step.text
    action = next((name for name, pattern in _ACTIONS if pattern.search(verbs)), None)
    press = _call("press", [_py(_key(key.group("key"))), f"intent={intent}"]) if key else []
    if action == "observe":
        lines.append("    # an observation: the expectations below check it")
    elif url and re.search(r"(открыть|перейти|зайти|open|go to|navigate|visit)", step.text, re.I):
        lines += _call("goto", [_py(url.group("url")), f"intent={intent}"])
    elif action in {"fill", "select"}:
        quoted = _quoted(step.text)
        value = _py(quoted) if quoted else f"TODO_VALUE({what})"
        lines += _call(action, [f"TODO({what})", value, f"intent={intent}"])
        lines += press  # "Type the name and press Enter"
    elif key:
        lines += press
    elif action in {"hover", "check", "uncheck", "click"}:
        lines += _call(action, [f"TODO({what})", f"intent={intent}"])
    else:
        lines.append("    # TODO: choose the action this step performs")
        lines += _call("click", [f"TODO({what})", f"intent={intent}"])
    return lines


def _expect_lines(case: Case, index: int, text: str, ids: _Ids, words: _Words) -> list[str]:
    intent = _py(f"{words.expected(case.number, index)}: {_truncate(text, 120)}")
    lines = _comment("Expected: " if not words.russian else "Ожидается: ", text)
    lines += _call(
        "expect_visible",
        [
            f"TODO({_py(_truncate(text, 60))})",
            f"intent={intent}",
            f"assertion_id={_py(ids.assertion(case, index))}",
            f"claim_id={_py(ids.claim(case, index))}",
        ],
    )
    return lines


def _function(case: Case, ids: _Ids, words: _Words) -> list[str]:
    name = f"test_{case.number:02d}"
    if suffix := slug(case.title, separator="_", limit=48):
        name = f"{name}_{suffix}"
    claims = [ids.claim(case, index) for index in range(1, len(case.all_expected) + 1)]
    marker_args = [
        "plan=PLAN",
        f"claims=[{', '.join(_py(claim) for claim in claims)}]",
        f"case_id={_py(ids.case(case))}",
    ]
    marker = f"@pytest.mark.testence({', '.join(marker_args)})"
    if len(marker) > 100:
        marker_lines = ["@pytest.mark.testence("]
        marker_lines += ["    plan=PLAN,", "    claims=["]
        marker_lines += [f"        {_py(claim)}," for claim in claims]
        marker_lines += ["    ],", f"    case_id={_py(ids.case(case))},", ")"]
    else:
        marker_lines = [marker]
    doc = [f'    """{case.number}. {_docstring(case.title)}']
    for label, value in (("Precondition", case.precondition), ("Cleanup", case.postcondition)):
        if value:
            doc.append("")
            doc += [
                f"    {line}" for line in textwrap.wrap(f"{label}: {_docstring(value)}", width=92)
            ]
    if len(doc) == 1:
        doc[0] += '"""'
    else:
        doc.append('    """')
    lines = [*marker_lines, f"def {name}(ex):", *doc]
    counter = 0
    for position, step in enumerate(case.steps, start=1):
        lines += _step_lines(case, position, step, words)
        for text in step.expected:
            counter += 1
            lines += _expect_lines(case, counter, text, ids, words)
    for text in case.expected:
        counter += 1
        lines += _expect_lines(case, counter, text, ids, words)
    return lines


def _docstring(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
    return f"{escaped} " if escaped.endswith('"') else escaped


def _module(cases: list[Case], ids: _Ids, words: _Words, *, plan_ref: str, source: str) -> str:
    header = [
        f'"""Test skeleton for {_docstring(source)}, generated by `testence plan skeleton`.',
        "",
        "Replace each TODO(...) with a Target from `testence explore` or the failure",
        "snapshot. Once this file is edited, regeneration leaves it alone.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "import pytest",
        "",
        "from testence.engine import Target",
        "",
        f"PLAN = {_py(plan_ref)}",
        "",
        "",
        "def TODO(what: str) -> Target:",
        '    """An address the case file does not give: fails the step until replaced."""',
        '    raise NotImplementedError(f"skeleton: no Target yet for {what!r}")',
        "",
        "",
        "def TODO_VALUE(what: str) -> str:",
        '    """A value the case file does not quote: fails the step until replaced."""',
        '    raise NotImplementedError(f"skeleton: no value yet for {what!r}")',
    ]
    body: list[str] = []
    for case in cases:
        body += ["", "", *_function(case, ids, words)]
    return "\n".join(header + body) + "\n"


# --------------------------------------------------------------------------- writing


def _digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _stamp_py(body: str) -> str:
    return f"# {MARKER} sha256={_digest(body)}\n{body}"


def _stamp_md(body: str) -> str:
    return f"<!-- {MARKER} sha256={_digest(body)} -->\n{body}"


_STAMP = re.compile(rf"^(?:# |<!-- ){re.escape(MARKER)} sha256=(?P<digest>[0-9a-f]{{16}})")


def _untouched(existing: str) -> bool:
    """True when ``existing`` is a generated file nobody has edited since."""
    first, _, rest = existing.partition("\n")
    match = _STAMP.match(first)
    return match is not None and match.group("digest") == _digest(rest)


def _untouched_json(existing: str) -> bool:
    try:
        document = json.loads(existing)
    except json.JSONDecodeError:
        return False
    if not isinstance(document, dict):
        return False
    stamp = document.pop("x-testence-skeleton", None)
    return isinstance(stamp, dict) and stamp.get("sha256") == _digest(_canonical(document))


def _canonical(document: dict[str, Any]) -> str:
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def read_utf8(path: Path, error: type[ValueError] = ValueError) -> str:
    """Read a text file as UTF-8 (a BOM is fine), raising ``error`` with a fix otherwise."""
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise error(
            f"{path} is not UTF-8 text (byte {exc.start}: {exc.reason}); save it as UTF-8, "
            "for example in an editor's 'Save with encoding' or with "
            "`iconv -f cp1251 -t utf-8`"
        ) from exc
    except OSError as exc:
        raise error(f"cannot read {path}: {exc}") from exc


def _write(path: Path, content: str, untouched: Any) -> str:
    """Write a generated file unless an author owns it now; return what happened."""
    if path.exists():
        existing = read_utf8(path, SkeletonError)
        if existing == content:
            return "unchanged"
        if not untouched(existing):
            return "kept"
        status = "updated"
    else:
        status = "created"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return status


def _plan_content(path: Path, plan: dict[str, Any], questions: list[dict[str, Any]]) -> str:
    if path.suffix.lower() == ".json":
        stamped = {**plan, "x-testence-skeleton": {"sha256": _digest(_canonical(plan))}}
        return json.dumps(stamped, ensure_ascii=False, indent=2) + "\n"
    lines = [
        f"# {plan['title']}",
        "",
        f"Generated by `testence plan skeleton` from `{plan['source']}`. Each expected",
        "result of the source is one claim; its `expected` is the source text, verbatim.",
        "",
        "```testence-planspec",
        json.dumps(plan, ensure_ascii=False, indent=2),
        "```",
    ]
    if questions:
        lines += ["", "## Open questions", ""]
        lines += [
            f"- case {item['case']} ({item['title']}, line {item['line']}): {item['question']}."
            for item in questions
        ]
    return _stamp_md("\n".join(lines) + "\n")


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def skeleton(
    cases_path: Path | str,
    plan_path: Path | str,
    tests_dir: Path | str,
    *,
    module: str | None = None,
    root: Path | str = ".",
    project_id: str | None = None,
    plan_id: str | None = None,
) -> dict[str, Any]:
    """Generate (or refresh) a PlanSpec and a pytest skeleton from a Markdown case file.

    ``root`` is the pytest root directory: the ``plan=`` path in each marker is relative
    to it. Returns a ``testence/plan-skeleton/1`` document describing what was written.
    """
    source = Path(cases_path)
    plan_file = Path(plan_path)
    tests = Path(tests_dir)
    root_dir = Path(root)
    if plan_file.suffix.lower() not in {".json", ".md"}:
        raise SkeletonError("--plan must end in .json or .md")
    text = read_utf8(source, SkeletonError)
    kind, cases = parse_cases(text)

    heading = next(
        (match.group("text") for match in map(_HEADING.match, text.splitlines())
         if match and len(match.group("level")) == 1),
        None,
    )  # fmt: skip
    resolved_plan_id = plan_id or slug(source.stem, limit=_ID_MAX) or "cases"
    resolved_project = (
        project_id or slug(root_dir.resolve().name, limit=_ID_MAX) or "testence-project"
    )
    plan, questions = build_plan(
        cases,
        project_id=resolved_project,
        plan_id=resolved_plan_id,
        title=heading or source.stem,
        source=_relative(source, root_dir),
    )
    try:
        from .contracts.plan import PlanSpec

        PlanSpec.from_dict(plan)
    except ContractError as exc:  # a generator bug, not an input problem
        raise SkeletonError(f"generated plan is invalid: {exc}") from exc

    files: list[dict[str, str]] = []
    plan_status = _write(
        plan_file,
        _plan_content(plan_file, plan, questions),
        _untouched_json if plan_file.suffix.lower() == ".json" else _untouched,
    )
    files.append({"path": str(plan_file), "kind": "plan", "status": plan_status})

    ids = _Ids(resolved_plan_id)
    words = _Words(bool(_CYRILLIC.search(text)))
    plan_ref = _relative(plan_file, root_dir)
    covered = [case for case in cases if case.all_expected]
    case_rows: list[dict[str, Any]] = []
    if module:
        name = module if module.endswith(".py") else f"{module}.py"
        target = tests / name
        content = _stamp_py(_module(covered, ids, words, plan_ref=plan_ref, source=source.name))
        files.append(
            {"path": str(target), "kind": "tests", "status": _write(target, content, _untouched)}
        )
        targets = {case.number: target for case in covered}
    else:
        targets = {}
        for case in covered:
            suffix = slug(case.title, separator="_", limit=40)
            target = tests / (f"test_{case.number:02d}" + (f"_{suffix}" if suffix else "") + ".py")
            content = _stamp_py(_module([case], ids, words, plan_ref=plan_ref, source=source.name))
            files.append(
                {
                    "path": str(target),
                    "kind": "tests",
                    "status": _write(target, content, _untouched),
                }
            )
            targets[case.number] = target
    files += _stale(tests, {Path(entry["path"]) for entry in files}, plan_ref)
    warnings = [
        {
            "case": case.number,
            "line": case.line,
            "warning": "no steps found: the test has checks only; number the steps "
            "(1. …) or list them as '- …' bullets",
        }
        for case in covered
        if not case.steps
    ]
    for case in covered:
        case_rows.append(
            {
                "number": case.number,
                "case_id": ids.case(case),
                "title": case.title,
                "steps": len(case.steps),
                "claims": [ids.claim(case, i) for i in range(1, len(case.all_expected) + 1)],
                "test": str(targets[case.number]),
            }
        )

    try:
        load_plan(plan_file)
        plan_valid = True
    except ContractError:
        plan_valid = False  # an author's edit of a kept plan; reported, not hidden
    return {
        "schema": SKELETON_SCHEMA,
        "source": str(source),
        "format": kind,
        "plan": {"path": str(plan_file), "id": resolved_plan_id, "valid": plan_valid},
        "cases": case_rows,
        "files": files,
        "open_questions": questions,
        "warnings": warnings,
    }


def _stale(tests: Path, written: set[Path], plan_ref: str) -> list[dict[str, str]]:
    """Earlier skeletons of this plan that no case produces any more (a retitled case).

    Left in place they would bind the same claims twice. An untouched one is removed;
    one an author edited is reported as ``stale`` and kept for them to merge.
    """
    if not tests.is_dir():
        return []
    reference = f"PLAN = {_py(plan_ref)}"
    found: list[dict[str, str]] = []
    resolved = {path.resolve() for path in written}
    for path in sorted(tests.glob("*.py")):
        if path.resolve() in resolved:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not _STAMP.match(text.partition("\n")[0]) or reference not in text:
            continue
        if _untouched(text):
            path.unlink()
            found.append({"path": str(path), "kind": "tests", "status": "removed"})
        else:
            found.append({"path": str(path), "kind": "tests", "status": "stale"})
    return found
