"""Allure identity and metadata of a pytest item, compatible with allure-pytest.

A team moving an allure-pytest suite onto Testence keeps its Allure TestOps test
cases only if every result lands on the same identity: ``fullName``, ``testCaseId``
and ``historyId`` computed exactly as allure-pytest computes them, and the
``@allure.*`` decorators still read. This module reproduces those rules without
importing ``allure``: the decorators are ordinary pytest marks
(``allure_label``, ``allure_link``, ``allure_description``) and a function attribute
(``__allure_display_name__``), so they are read from the item.

Reference: allure-pytest ``utils.py`` and ``listener.py`` (allure-python 2.x). The
golden in ``tests/fixtures/allure-pytest-reference`` pins the reproduced values
against real allure-pytest output.

Hashes of parameter values are computed here, while the values exist; the ledger
keeps the digests and redacted display values, never the raw values.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

#: Marks that allure-pytest never turns into tags, plus Testence's own contract marks.
IGNORED_TAG_MARKS = frozenset(
    {
        "usefixtures",
        "filterwarnings",
        "skip",
        "skipif",
        "xfail",
        "parametrize",
        "testence",
        "testence_quarantine",
    }
)
#: Labels that keep only their first value, as in allure-pytest.
_UNIQUE_LABELS = frozenset(
    {"severity", "framework", "host", "suite", "parentSuite", "subSuite", "thread"}
)
ALLURE_ID_LABELS = ("as_id", "ALLURE_ID")


def md5(*parts: Any) -> str:
    """allure-commons ``md5``: strings as UTF-8, other values by ``repr``."""
    digest = hashlib.md5()  # noqa: S324 - identity hash defined by allure-pytest
    for part in parts:
        if not isinstance(part, bytes):
            part = (part if isinstance(part, str) else repr(part)).encode("utf-8")
        digest.update(part)
    return digest.hexdigest()


def represent(value: Any) -> str:
    """allure-commons ``represent``: how a parameter value is displayed."""
    if isinstance(value, str):
        return f"'{value}'"
    if isinstance(value, (bytes, bytearray)):
        return repr(type(value))
    return repr(value)


@dataclass(frozen=True)
class ParsedNodeId:
    filepath: str
    path_segments: tuple[str, ...]
    parent_package: str
    module: str
    package: str
    class_names: tuple[str, ...]
    test_function: str

    @classmethod
    def parse(cls, nodeid: str) -> ParsedNodeId:
        segments = nodeid.split("::")
        filepath = segments[0]
        function_segment = segments[-1] if len(segments) > 1 else ""
        class_names = tuple(segments[1:-1])
        path_segments = tuple(filepath.split("/"))
        parent_dirs, filename = path_segments[:-1], path_segments[-1]
        parent_package = ".".join(parent_dirs)
        module = filename.rsplit(".", 1)[0]
        return cls(
            filepath=filepath,
            path_segments=path_segments,
            parent_package=parent_package,
            module=module,
            package=".".join(part for part in (parent_package, module) if part),
            class_names=class_names,
            test_function=function_segment.split("[", 1)[0],
        )


def full_name(nodeid: str, originalname: str | None = None) -> str:
    """``package[.Class...]#function`` without parameters."""
    parsed = ParsedNodeId.parse(nodeid.replace("\\", "/"))
    class_part = ("." + ".".join(parsed.class_names)) if parsed.class_names else ""
    return f"{parsed.package}{class_part}#{originalname or parsed.test_function}"


def history_id(name: str, parameters: dict[str, Any]) -> str:
    """allure-pytest ``historyId``: full name plus original values sorted by name."""
    return md5(name, *(parameters[key] for key in sorted(parameters)))


def _marks(item: Any, name: str) -> list[Any]:
    return [mark for mark in item.iter_markers() if getattr(mark, "name", None) == name]


def _first_arg(item: Any, name: str) -> Any:
    marks = _marks(item, name)
    return marks[0].args[0] if marks and marks[0].args else None


def labels(item: Any) -> list[tuple[str, str]]:
    """``@allure.label``/``feature``/``story``/``severity``/``id``/``tag`` marks."""
    unique: dict[str, str] = {}
    found: list[tuple[str, str]] = []
    for mark in _marks(item, "allure_label"):
        label_type = str(mark.kwargs.get("label_type", ""))
        if not label_type:
            continue
        if label_type in _UNIQUE_LABELS:
            if label_type not in unique and mark.args:
                unique[label_type] = str(mark.args[0])
            continue
        for value in mark.args:
            pair = (label_type, str(value))
            if pair not in found:
                found.append(pair)
    found.extend(unique.items())
    return sorted(found)


def links(item: Any) -> list[dict[str, str]]:
    result = []
    for mark in _marks(item, "allure_link"):
        if not mark.args:
            continue
        url = str(mark.args[0])
        result.append(
            {
                "type": str(mark.kwargs.get("link_type") or "link"),
                "url": url,
                "name": str(mark.kwargs.get("name") or url),
            }
        )
    return result


def tags(item: Any) -> list[str]:
    """Markers without arguments, as allure-pytest turns them into tags."""
    names = []
    for mark in item.iter_markers():
        if mark.name in IGNORED_TAG_MARKS or mark.name.startswith("allure_"):
            continue
        if mark.args or mark.kwargs:
            continue
        if mark.name not in names:
            names.append(mark.name)
    return sorted(names)


def title(item: Any, parameters: dict[str, Any]) -> str | None:
    """``@allure.title``, formatted with the parameters as allure-pytest does."""
    template = getattr(getattr(item, "obj", None), "__allure_display_name__", None)
    if not template:
        return None
    values: dict[str, Any] = {}
    param_id = getattr(getattr(item, "callspec", None), "id", None)
    if param_id:
        values["param_id"] = param_id
    values.update(parameters)
    values.update(getattr(item, "funcargs", {}) or {})
    try:
        return str(template).format(**values)
    except (KeyError, IndexError, ValueError):
        return str(template)


def description(item: Any) -> str | None:
    """``@allure.description`` only; the docstring is :func:`docstring`."""
    value = _first_arg(item, "allure_description")
    return str(value) if value else None


def docstring(item: Any) -> str | None:
    function = getattr(item, "function", None)
    doc = getattr(function, "__doc__", None)
    return doc if isinstance(doc, str) and doc.strip() else None


def allure_id(item: Any) -> str | None:
    for label_type, value in labels(item):
        if label_type in ALLURE_ID_LABELS and value.strip():
            return value.strip()
    return None


def record(item: Any) -> dict[str, Any]:
    """The ``allure`` object of a ``test.start`` event (evidence-schema.md)."""
    nodeid = str(item.nodeid).replace("\\", "/")
    parsed = ParsedNodeId.parse(nodeid)
    parameters = dict(getattr(getattr(item, "callspec", None), "params", {}) or {})
    name = full_name(nodeid, getattr(item, "originalname", None))
    document: dict[str, Any] = {
        "full_name": name,
        "test_case_id": md5(name),
        "history_id": history_id(name, parameters),
        "title_path": [part for part in (*parsed.path_segments, *parsed.class_names) if part],
        "package": parsed.package,
        "suite": {
            "parentSuite": parsed.parent_package,
            "suite": parsed.module,
            "subSuite": " > ".join(parsed.class_names),
        },
        "test_class": ".".join(parsed.class_names),
        "test_method": parsed.test_function,
        "labels": [{"name": label_type, "value": value} for label_type, value in labels(item)],
        "links": links(item),
        "tags": tags(item),
        # Name/value records: the redactor masks the value of a secret-named parameter.
        "parameters": [
            {"name": str(key), "value": represent(parameters[key])} for key in sorted(parameters)
        ],
    }
    display = title(item, parameters)
    if display:
        document["title"] = display
    text = description(item)
    if text:
        document["description"] = text
    doc = docstring(item)
    if doc:
        document["docstring"] = doc
    html = _first_arg(item, "allure_description_html")
    if html:
        document["description_html"] = str(html)
    return document
