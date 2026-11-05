"""``testence inventory``: a screen reference built from what a run actually did.

Authors keep a page per screen: which controls a test touches and how they are
addressed, what the page asks the API, which texts prove an outcome, and which steps
needed a second try. That knowledge is in every run's ledger already. This module
reads one run (``run.jsonl`` and, on failure, ``pack.json``) and writes one Markdown
file per page, merging with what earlier runs wrote:

- the page of a step is the last navigation of its test: a ``goto``/``navigate`` step
  whose intent names a URL (the DSL default ``open <url>``, or a path in a custom
  intent), a ``page_url`` field on a step, or the ``page_url`` of a failure pack;
  steps before any known navigation are filed under ``unknown-page``;
- a Target is listed with its role, name, actions and the text the element showed;
- API calls are the browser's (``net`` event: method, templated path, statuses) and,
  separately, the test's own client calls (``api.request``);
- texts are what green ``expect_*`` steps saw;
- traps are steps that failed at least once, with whether the test then went green.

A section whose heading line or first line carries ``<!-- manual -->`` is the author's
and is kept, verbatim, on every regeneration.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
from pathlib import Path
from typing import Any

from .skeleton import _TRANSLIT, read_utf8

INVENTORY_SCHEMA = "testence/inventory/1"
UNKNOWN_PAGE = "unknown-page"
_DATA = re.compile(r"<!-- testence:inventory (?P<json>\{.*?\}) -->", re.DOTALL)
_MANUAL = "<!-- manual -->"
_NAVIGATION = re.compile(
    r"^\s*(?:open|go to|goto|navigate to|visit|открыть|перейти на|перейти)\b",
    re.IGNORECASE,
)
_URL_IN_TEXT = re.compile(r"(https?://[^\s'\"`»)]+|file:///[^\s'\"`»)]+|(?<![\w/.])/[\w\-./{}%~]*)")
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_DESCRIBED = re.compile(r"(?P<key>\w+)=(?P<q>['\"])(?P<value>.*?)(?P=q)")
_EXPECT_TEXT = re.compile(r"^expect (?P<q>['\"])(?P<text>.*?)(?P=q) at ")


class InventoryError(ValueError):
    """The run directory cannot be read as a Testence run."""


def _identifier(segment: str) -> bool:
    return bool(
        segment.isdigit()
        or _UUID.match(segment)
        or (len(segment) >= 16 and re.fullmatch(r"[0-9a-fA-F]+", segment))
    )


def template_path(url: str) -> str:
    """A page or API path with origin, query and identifiers removed."""
    parsed = urllib.parse.urlsplit(url)
    path = parsed.path or "/"
    if parsed.scheme == "file":
        path = "/" + Path(urllib.parse.unquote(path)).name
    parts = ["{id}" if part and _identifier(part) else part for part in path.split("/")]
    templated = "/".join(parts) or "/"
    return templated if templated == "/" else templated.rstrip("/")


_RESERVED = frozenset({"index", UNKNOWN_PAGE})


def page_slug(page: str) -> str:
    """A file name for ``page`` that no other page can share.

    Segments are joined with ``_`` and kept readable (Cyrillic is transliterated). When
    that loses anything (case, punctuation, ``{id}``, other scripts, length) a digest of
    the page is appended, so ``/a/b`` and ``/a-b`` or ``/`` and ``/привет`` never
    meet in one file.
    """
    if page == UNKNOWN_PAGE:
        return UNKNOWN_PAGE
    if page == "/":
        return "index"
    segments = page.strip("/").split("/")
    readable = "_".join(
        re.sub(r"[^a-z0-9]+", "-", segment.casefold().translate(_TRANSLIT)).strip("-")
        for segment in segments
    )
    # "{id}" reads as "id"; a literal "id" segment is the one that gets the digest.
    rebuilt = "/" + "/".join("{id}" if part == "id" else part for part in readable.split("_"))
    lossless = rebuilt == page and readable not in _RESERVED
    if lossless and len(readable) <= 80:
        return readable
    digest = hashlib.sha256(page.encode("utf-8")).hexdigest()[:8]
    return f"{readable[:80].strip('-_')}-{digest}" if readable.strip("-_") else digest


def _navigation_url(event: dict[str, Any]) -> str | None:
    explicit = event.get("page_url") or event.get("url")
    if isinstance(explicit, str) and explicit:
        return explicit
    intent = str(event.get("intent") or "")
    if event.get("target") or not _NAVIGATION.search(intent):
        return None
    match = _URL_IN_TEXT.search(intent)
    return match.group(1) if match else None


def _target_parts(described: str) -> dict[str, str]:
    """``role='button' name='Save'`` -> {kind: role, value: button, name: Save}."""
    parts = {m.group("key"): m.group("value") for m in _DESCRIBED.finditer(described)}
    first = _DESCRIBED.search(described)
    result: dict[str, str] = {}
    if first is not None:
        result["kind"] = first.group("key")
        result["value"] = first.group("value")
    if "name" in parts and result.get("kind") != "name":
        result["name"] = parts["name"]
    return result


def _action(start: dict[str, Any]) -> str:
    """``click``/``fill`` from the recorded operation, else the intent's verb.

    Only click and fill annotate their steps; any other step on a Target whose intent
    does not start with an action verb is an observation (``expect_*``) and is listed
    as ``check``.
    """
    operation = start.get("operation")
    if isinstance(operation, dict) and operation.get("method"):
        return str(operation["method"])
    intent = str(start.get("intent") or "").strip().lower()
    head = intent.split(" ", 1)[0] if intent else ""
    if head in _ACTION_VERBS:
        return head
    return "check" if start.get("target") else "step"


_ACTION_VERBS = frozenset(
    {"click", "fill", "type", "select", "press", "check", "uncheck", "hover", "drag", "focus"}
    | {"upload", "download", "scroll", "open", "close", "switch"}
)


def _empty_page(page: str) -> dict[str, Any]:
    return {
        "page": page,
        "urls": [],
        "runs": [],
        "targets": {},
        "api": {},
        "texts": [],
        "traps": {},
    }


def _add(values: list[Any], value: Any, limit: int = 20) -> None:
    if value not in values and len(values) < limit:
        values.append(value)


def collect(events: list[dict[str, Any]], run_dir: Path) -> dict[str, dict[str, Any]]:
    """Per-page facts of one run's events."""
    pages: dict[str, dict[str, Any]] = {}
    run_id = next((str(e["run_id"]) for e in events if e.get("run_id")), run_dir.name)
    current: dict[str, str] = {}  # attempt -> page
    attempt_pages: dict[str, set[str]] = {}
    starts: dict[tuple[str, str], tuple[dict[str, Any], str]] = {}
    failed_steps: list[tuple[str, str, dict[str, Any], dict[str, Any], str]] = []
    final_status: dict[str, str] = {}

    def page_of(name: str) -> dict[str, Any]:
        if name not in pages:
            pages[name] = _empty_page(name)
            pages[name]["runs"].append(run_id)
        return pages[name]

    for event in events:
        kind = event.get("kind")
        test = str(event.get("test") or event.get("nodeid") or "")
        attempt = f"{test}#{event.get('attempt_id', '')}"
        if kind == "step.start":
            url = _navigation_url(event)
            if url:
                page = template_path(url)
                current[attempt] = page
                _add(page_of(page)["urls"], url)
            page = current.get(attempt, UNKNOWN_PAGE)
            attempt_pages.setdefault(attempt, set()).add(page)
            starts[(attempt, str(event.get("step")))] = (event, page)
        elif kind == "step.end":
            found = starts.get((attempt, str(event.get("step"))))
            if found is None:
                continue
            start, page = found
            url = event.get("page_url")
            if isinstance(url, str) and url:
                page = template_path(url)
                current[attempt] = page
                _add(page_of(page)["urls"], url)
            facts = page_of(page)
            described = start.get("target")
            action = _action(start)
            fingerprint = (
                event.get("fingerprint") if isinstance(event.get("fingerprint"), dict) else {}
            )
            seen_text = str((fingerprint or {}).get("text") or "").strip()
            if described:
                entry = facts["targets"].setdefault(
                    str(described),
                    {
                        "target": str(described),
                        **_target_parts(str(described)),
                        "actions": [],
                        "texts": [],
                        "tests": [],
                    },
                )
                _add(entry["actions"], action)
                _add(entry["tests"], test, limit=10)
                if seen_text and event.get("status") == "ok":
                    _add(entry["texts"], seen_text[:200], limit=5)
            if event.get("status") == "ok" and action == "check":
                quoted = _EXPECT_TEXT.match(str(start.get("intent") or ""))
                text = quoted.group("text") if quoted else seen_text
                if text:
                    _add(facts["texts"], text[:200], limit=50)
            if event.get("status") == "fail":
                failed_steps.append((attempt, test, start, event, page))
        elif kind == "net":
            for page in attempt_pages.get(attempt, {UNKNOWN_PAGE}):
                api = page_of(page)["api"]
                for record in list(event.get("reads") or []) + list(event.get("mutations") or []):
                    if not isinstance(record, dict):
                        continue
                    method = str(record.get("method", "GET")).upper()
                    path = template_path(str(record.get("path", "")))
                    entry = api.setdefault(
                        f"{method} {path}",
                        {"method": method, "path": path, "source": "page", "statuses": []},
                    )
                    if record.get("status") is not None:
                        _add(entry["statuses"], record["status"])
        elif kind == "api.request":
            page = current.get(attempt, UNKNOWN_PAGE)
            method = str(event.get("method", "GET")).upper()
            path = template_path(str(event.get("url", "")))
            entry = page_of(page)["api"].setdefault(
                f"test {method} {path}",
                {"method": method, "path": path, "source": "test", "statuses": []},
            )
            _add(entry["statuses"], event.get("status", "error"))
        elif kind == "test.end":
            final_status[test] = str(event.get("status", ""))
            pack = event.get("pack")
            if isinstance(pack, str) and current.get(attempt) is None:
                url = _pack_page_url(run_dir / pack)
                if url:
                    current[attempt] = template_path(url)
                    _add(page_of(current[attempt])["urls"], url)

    for attempt, test, start, end, page in failed_steps:
        if page == UNKNOWN_PAGE and current.get(attempt):
            page = current[attempt]
        key = f"{test} :: {start.get('intent')}"
        trap = page_of(page)["traps"].setdefault(
            key,
            {
                "test": test,
                "intent": str(start.get("intent") or ""),
                "target": start.get("target"),
                "failures": 0,
                "errors": [],
                "then_green": False,
            },
        )
        trap["failures"] += 1
        _add(trap["errors"], str(end.get("error") or "").splitlines()[0][:240], limit=3)
        trap["then_green"] = trap["then_green"] or final_status.get(test) == "passed"
    return pages


def _pack_page_url(pack_dir: Path) -> str | None:
    try:
        document = json.loads((pack_dir / "pack.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    value = document.get("page_url") if isinstance(document, dict) else None
    return value if isinstance(value, str) and value else None


# --------------------------------------------------------------------------- merging


def _merge(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    merged = json.loads(json.dumps(old))
    for url in new["urls"]:
        _add(merged["urls"], url)
    for run in new["runs"]:
        if run not in merged["runs"]:
            merged["runs"].append(run)
    merged["runs"] = merged["runs"][-20:]
    for key, entry in new["targets"].items():
        target = merged["targets"].setdefault(
            key, {**entry, "actions": [], "texts": [], "tests": []}
        )
        for field, limit in (("actions", 20), ("texts", 5), ("tests", 10)):
            for value in entry[field]:
                _add(target[field], value, limit=limit)
    for key, entry in new["api"].items():
        call = merged["api"].setdefault(key, {**entry, "statuses": []})
        for status in entry["statuses"]:
            _add(call["statuses"], status)
    for text in new["texts"]:
        _add(merged["texts"], text, limit=50)
    for key, trap in new["traps"].items():
        known = merged["traps"].setdefault(key, {**trap, "failures": 0, "errors": []})
        known["failures"] += trap["failures"]
        for error in trap["errors"]:
            _add(known["errors"], error, limit=3)
        known["then_green"] = known["then_green"] or trap["then_green"]
    return merged


def _read_existing(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    """Previous data and the author's manual sections of an inventory file."""
    if not path.exists():
        return None, []
    text = read_utf8(path, InventoryError)
    data = None
    match = _DATA.search(text)
    if match:
        try:
            data = json.loads(match.group("json"))
        except json.JSONDecodeError:
            data = None
    body = _DATA.sub("", text)
    sections = re.split(r"(?m)^(?=## )", body)
    manual = [
        section.rstrip() + "\n"
        for section in sections[1:]
        if _MANUAL in section.split("\n", 2)[0] or _MANUAL in "\n".join(section.split("\n", 2)[:2])
    ]
    return data, manual


# --------------------------------------------------------------------------- rendering


def _cell(value: Any) -> str:
    text = str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")
    return text or "—"


def render(data: dict[str, Any], manual: list[str]) -> str:
    page = data["page"]
    lines = [f"# {page if page != UNKNOWN_PAGE else 'Steps before any known page'}", ""]
    lines.append(
        "Generated by `testence inventory` from runs "
        + ", ".join(f"`{run}`" for run in data["runs"])
        + ". Sections marked `<!-- manual -->` are kept on regeneration."
    )
    if page == UNKNOWN_PAGE:
        lines += [
            "",
            "These steps ran before a navigation the ledger could name. Put the URL in the "
            "`goto` intent (the default `open <url>` does) to file them under their page.",
        ]
    if data["urls"]:
        lines += ["", "URLs seen: " + ", ".join(f"`{url}`" for url in data["urls"][:5])]
    lines += ["", "## Targets", ""]
    if data["targets"]:
        lines += [
            "| Target | Role / kind | Name | Actions | Text seen | Tests |",
            "|---|---|---|---|---|---|",
        ]
        for entry in sorted(data["targets"].values(), key=lambda e: e["target"]):
            kind = entry.get("value") if entry.get("kind") == "role" else entry.get("kind")
            lines.append(
                f"| `{_cell(entry['target'])}` | {_cell(kind)} | {_cell(entry.get('name'))} | "
                f"{_cell(', '.join(entry['actions']))} | {_cell('; '.join(entry['texts']))} | "
                f"{len(entry['tests'])} |"
            )
    else:
        lines.append("No step addressed a Target on this page.")
    lines += ["", "## API calls", ""]
    if data["api"]:
        lines += ["| Source | Method | Path | Statuses |", "|---|---|---|---|"]
        for entry in sorted(
            data["api"].values(), key=lambda e: (e["source"], e["path"], e["method"])
        ):
            statuses = ", ".join(str(s) for s in entry["statuses"])
            lines.append(
                f"| {entry['source']} | {entry['method']} | `{_cell(entry['path'])}` | {_cell(statuses)} |"
            )
        lines += [
            "",
            "`page` rows are the browser's requests in tests that visited this page; `test` "
            "rows are the test's own API client (seed and oracles).",
        ]
    else:
        lines.append("No API call was recorded (browser network capture or `testence_api`).")
    lines += ["", "## Texts", ""]
    lines += [f"- {_cell(text)}" for text in data["texts"]] or [
        "No green `expect_*` step saw a text."
    ]
    lines += ["", "## Traps", ""]
    if data["traps"]:
        for trap in sorted(data["traps"].values(), key=lambda t: (-t["failures"], t["intent"])):
            outcome = "then green" if trap["then_green"] else "not green yet"
            target = f" at `{trap['target']}`" if trap.get("target") else ""
            lines.append(
                f"- **{_cell(trap['intent'])}**{target}: failed {trap['failures']}x, {outcome} "
                f"({trap['test']})"
            )
            lines += [f"  - `{_cell(error)}`" for error in trap["errors"]]
    else:
        lines.append("No step on this page failed.")
    out = "\n".join(lines) + "\n"
    for section in manual:
        out += "\n" + section
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True).replace("--", "-\\u002d")
    return out + f"\n<!-- testence:inventory {payload} -->\n"


def inventory(run_dir: Path | str, out: Path | str = Path("docs/inventory")) -> dict[str, Any]:
    """Write or merge one Markdown file per page; return a ``testence/inventory/1`` document."""
    from .metrics import load_run

    root = Path(run_dir)
    try:
        events = load_run(root)
    except (OSError, ValueError) as exc:
        raise InventoryError(str(exc)) from exc
    pages = collect(events, root)
    target_dir = Path(out)
    files: list[dict[str, Any]] = []
    for page, data in sorted(pages.items()):
        path = target_dir / f"{page_slug(page)}.md"
        previous, manual = _read_existing(path)
        if previous is not None and previous.get("page") != page:
            # Another page owns this name (a file from an older naming, or a digest
            # collision): never merge into it or take its manual sections.
            digest = hashlib.sha256(page.encode("utf-8")).hexdigest()[:16]
            path = target_dir / f"{page_slug(page)}-{digest}.md"
            previous, manual = _read_existing(path)
        if previous and previous.get("page") == page:
            # A run already merged is not counted twice: rerunning is idempotent.
            seen = set(data["runs"]) <= set(previous.get("runs", []))
            merged = previous if seen else _merge(previous, data)
        else:
            merged = data
        content = render(merged, manual)
        status = "created" if not path.exists() else "updated"
        if path.exists() and read_utf8(path, InventoryError) == content:
            status = "unchanged"
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
        files.append(
            {
                "page": page,
                "path": str(path),
                "status": status,
                "targets": len(merged["targets"]),
                "api_calls": len(merged["api"]),
                "texts": len(merged["texts"]),
                "traps": len(merged["traps"]),
                "manual_sections": len(manual),
            }
        )
    return {
        "schema": INVENTORY_SCHEMA,
        "run_dir": str(root),
        "out": str(target_dir),
        "pages": files,
    }
