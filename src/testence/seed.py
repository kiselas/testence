"""``testence seed scaffold``: temporary-object fixtures generated from an OpenAPI document.

Every suite that creates data needs the same three things: names that mark an object as
temporary, a cleanup that deletes exactly those objects, and proof that the cleanup
worked. Written by hand, cleanup is where suites go wrong quietly: a parent deleted
before its children answers 409 forever, or a DELETE that returned 200 left the object
in place. This module reads an OpenAPI 3.x document and writes a fixture module that
does it in the right order:

- ``temp_name(ticket, label)`` carries the marker;
- ``Sweeper`` finds marked objects by name, deletes them **dependents first** (the order
  comes from ``$ref`` properties, ``<name>_id`` fields and nested paths of the schema),
  repeats a DELETE answered with 409 for up to five seconds, requires ``GET`` to answer
  404 afterwards, and finally asserts that nothing marked is left.

The generated code uses :class:`testence.api.ApiClient` only (through the
``testence_api`` fixture), never the browser.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SEED_SCHEMA = "testence/seed-scaffold/1"
MARKER = "testence:seed-scaffold"
_NAME_FIELDS = ("name", "title", "label", "display_name", "displayName")
_SEARCH_PARAMS = ("search", "q", "query", "name", "filter", "name__icontains", "name_contains")
_ITEMS_KEYS = ("items", "data", "results", "content", "records", "rows")
_FETCH_TIMEOUT_S = 30.0


class SeedError(ValueError):
    """The OpenAPI document cannot be turned into a safe cleanup."""


@dataclass
class Collection:
    name: str
    list_path: str
    item_path: str
    id_param: str
    id_field: str = "id"
    name_field: str = ""
    search_param: str | None = None
    items_key: str | None = None
    schema: str | None = None
    parent: str | None = None
    parent_param: str | None = None
    depends_on: set[str] = field(default_factory=set)

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "list_path": self.list_path,
            "item_path": self.item_path,
            "name_field": self.name_field,
            "search_param": self.search_param,
            "items_key": self.items_key,
            "parent": self.parent,
            "depends_on": sorted(self.depends_on),
        }


# --------------------------------------------------------------------------- loading


def load_openapi(source: str) -> dict[str, Any]:
    """Read an OpenAPI 3.x document from a path or an http(s) URL, JSON or YAML."""
    if re.match(r"^https?://", source, re.IGNORECASE):
        request = urllib.request.Request(source, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=_FETCH_TIMEOUT_S) as response:  # noqa: S310
                raw = response.read().decode("utf-8")
        except OSError as exc:
            raise SeedError(f"cannot fetch {source}: {exc}") from exc
    else:
        try:
            raw = Path(source).read_text(encoding="utf-8-sig")
        except OSError as exc:
            raise SeedError(f"cannot read {source}: {exc}") from exc
    document: Any
    try:
        document = json.loads(raw)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError as exc:
            raise SeedError(
                f"{source} is not JSON; a YAML document needs PyYAML (pip install pyyaml), "
                "or pass the JSON form of the document"
            ) from exc
        try:
            document = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            raise SeedError(f"{source} is neither valid JSON nor valid YAML: {exc}") from exc
    if not isinstance(document, dict) or not str(document.get("openapi", "")).startswith("3"):
        raise SeedError(f"{source} is not an OpenAPI 3.x document (no 'openapi: 3.x' field)")
    if not isinstance(document.get("paths"), dict):
        raise SeedError(f"{source} has no paths")
    return document


# --------------------------------------------------------------------------- analysis


def _ref_name(node: Any) -> str | None:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            return ref.rsplit("/", 1)[1]
    return None


def _resolve(document: dict[str, Any], node: Any, depth: int = 0) -> dict[str, Any]:
    """A schema with local ``$ref`` and ``allOf`` merged into one object."""
    if not isinstance(node, dict) or depth > 20:
        return {}
    name = _ref_name(node)
    if name is not None:
        target = document.get("components", {}).get("schemas", {}).get(name)
        return _resolve(document, target, depth + 1)
    if "allOf" in node and isinstance(node["allOf"], list):
        merged: dict[str, Any] = {"properties": {}, "required": []}
        for part in node["allOf"]:
            resolved = _resolve(document, part, depth + 1)
            merged["properties"].update(resolved.get("properties", {}))
            merged["required"] += list(resolved.get("required", []))
        return merged
    return node


def _json_schema(operation: Any, *, request: bool) -> Any:
    if not isinstance(operation, dict):
        return None
    if request:
        content = (operation.get("requestBody") or {}).get("content") or {}
    else:
        responses = operation.get("responses") or {}
        answer = next(
            (responses[code] for code in ("200", "201", 200, 201) if code in responses), None
        )
        content = (answer or {}).get("content") or {}
    media = next((value for key, value in content.items() if "json" in key), None)
    return (media or {}).get("schema")


def _schema_name(document: dict[str, Any], node: Any) -> str | None:
    if not isinstance(node, dict):
        return None
    direct = _ref_name(node)
    if direct:
        return direct
    for part in node.get("allOf", []) or []:
        found = _ref_name(part)
        if found:
            return found
    return None


def _static(segment: str) -> bool:
    return not (segment.startswith("{") and segment.endswith("}"))


def _server_prefix(document: dict[str, Any]) -> str:
    servers = document.get("servers") or []
    if not servers or not isinstance(servers[0], dict):
        return ""
    path = urllib.parse.urlsplit(str(servers[0].get("url", ""))).path
    return path.rstrip("/")


def _singular(name: str) -> str:
    if name.endswith("ies"):
        return name[:-3] + "y"
    if name.endswith(("ses", "xes", "zes", "ches", "shes")):
        return name[:-2]
    if name.endswith("s") and not name.endswith("ss"):
        return name[:-1]
    return name


def _identifier(value: str) -> str:
    text = re.sub(r"[^0-9a-zA-Z]+", "_", value).strip("_").lower()
    return text if text and not text[0].isdigit() else f"c_{text}"


def analyse(document: dict[str, Any]) -> tuple[list[Collection], list[dict[str, str]]]:
    """Deletable collections of ``document`` with their dependencies, and what was skipped."""
    prefix = _server_prefix(document)
    paths: dict[str, dict[str, Any]] = {
        path: ops for path, ops in document["paths"].items() if isinstance(ops, dict)
    }
    found: dict[str, Collection] = {}
    skipped: list[dict[str, str]] = []
    for path, ops in sorted(paths.items()):
        segments = [part for part in path.strip("/").split("/") if part]
        if not segments or not _static(segments[-1]) or "get" not in ops:
            continue
        item = next(
            (
                (candidate, candidate.rsplit("/", 1)[1][1:-1])
                for candidate in paths
                if candidate.rstrip("/").rsplit("/", 1)[0] == path.rstrip("/")
                and not _static(candidate.rstrip("/").rsplit("/", 1)[1])
                and "delete" in paths[candidate]
            ),
            None,
        )
        if item is None:
            continue
        item_path, id_param = item
        name = _identifier(segments[-1])
        if name in found:
            name = _identifier("_".join(s for s in segments if _static(s))[-60:])
        schema_name = (
            _schema_name(document, _json_schema(ops.get("post"), request=True))
            or _schema_name(document, _json_schema(paths[item_path].get("get"), request=False))
            or _schema_name(
                document, (_json_schema(ops.get("get"), request=False) or {}).get("items")
            )
        )
        schema = _resolve(
            document,
            _json_schema(ops.get("post"), request=True)
            or _json_schema(paths[item_path].get("get"), request=False)
            or {},
        )
        properties = schema.get("properties") or {}
        name_field = next((key for key in _NAME_FIELDS if key in properties), "")
        if not name_field:
            skipped.append(
                {"name": name, "reason": "no name/title/label field to carry the marker"}
            )
            continue
        parameters = (ops.get("get") or {}).get("parameters") or []
        query = {
            entry.get("name")
            for entry in parameters
            if isinstance(entry, dict) and entry.get("in") == "query"
        }
        list_schema = _resolve(document, _json_schema(ops.get("get"), request=False) or {})
        items_key = None
        if list_schema.get("type") != "array":
            items_key = next(
                (key for key in _ITEMS_KEYS if key in (list_schema.get("properties") or {})),
                None,
            )
        id_field = "id" if "id" in properties or id_param in ("id",) else id_param
        collection = Collection(
            name=name,
            list_path=prefix + path,
            item_path=prefix + item_path,
            id_param=id_param,
            id_field="id" if "id" in properties else id_field,
            name_field=name_field,
            search_param=next((p for p in _SEARCH_PARAMS if p in query), None),
            items_key=items_key,
            schema=schema_name,
        )
        params_in_list = [segment[1:-1] for segment in segments if not _static(segment)]
        if params_in_list:
            collection.parent_param = params_in_list[-1]
            parent_path = "/" + "/".join(segments[: segments.index("{" + params_in_list[-1] + "}")])
            collection.parent = parent_path  # resolved to a collection name below
        found[name] = collection

    by_path = {c.list_path[len(prefix) :].rstrip("/"): c.name for c in found.values()}
    by_schema = {c.schema: c.name for c in found.values() if c.schema}
    by_singular = {_singular(c.name): c.name for c in found.values()}
    by_singular.update({c.name: c.name for c in found.values()})
    for collection in found.values():
        if collection.parent is not None:
            parent = by_path.get(collection.parent.rstrip("/"))
            if parent is None:
                skipped.append(
                    {
                        "name": collection.name,
                        "reason": f"nested under {collection.parent}, which is not a "
                        "deletable collection",
                    }
                )
            collection.parent = parent
            if parent:
                collection.depends_on.add(parent)
        _references(document, collection, paths, prefix, by_schema, by_singular)
    unusable = {entry["name"] for entry in skipped}
    return [c for c in found.values() if c.name not in unusable], skipped


def _references(
    document: dict[str, Any],
    collection: Collection,
    paths: dict[str, dict[str, Any]],
    prefix: str,
    by_schema: dict[str, str],
    by_singular: dict[str, str],
) -> None:
    """Add what ``collection`` refers to: ``$ref`` properties and ``<name>_id`` fields."""
    list_ops = paths[collection.list_path[len(prefix) :]]
    item_ops = paths[collection.item_path[len(prefix) :]]
    schemas = [
        _json_schema(list_ops.get("post"), request=True),
        _json_schema(item_ops.get("get"), request=False),
    ]
    for node in schemas:
        properties = _resolve(document, node or {}).get("properties") or {}
        for key, value in properties.items():
            targets = set()
            for candidate in (
                value,
                (value or {}).get("items") if isinstance(value, dict) else None,
            ):
                name = _schema_name(document, candidate)
                if name and name in by_schema:
                    targets.add(by_schema[name])
            match = re.fullmatch(r"(?P<base>.+?)(?:_ids?|Ids?|_uuids?)", key)
            if match:
                base = re.sub(r"(?<!^)(?=[A-Z])", "_", match.group("base")).lower()
                for guess in (base, f"{base}s", f"{base}es", f"{base[:-1]}ies"):
                    if guess in by_singular:
                        targets.add(by_singular[guess])
                        break
            targets.discard(collection.name)
            collection.depends_on.update(targets)


def delete_order(collections: list[Collection]) -> list[str]:
    """Collection names with every dependent before what it depends on."""
    names = {c.name for c in collections}
    dependents: dict[str, set[str]] = {name: set() for name in names}
    for collection in collections:
        for target in collection.depends_on & names:
            dependents[target].add(collection.name)
    # A collection may be deleted once everything that depends on it is gone.
    blockers = {name: set(dependents[name]) for name in names}
    order: list[str] = []
    while blockers:
        ready = sorted(name for name, waiting in blockers.items() if not waiting)
        if not ready:
            cycle = ", ".join(sorted(blockers))
            raise SeedError(
                f"the references between {cycle} form a cycle; no deletion order is safe. "
                "Select collections without the cycle with --collections"
            )
        for name in ready:
            order.append(name)
            del blockers[name]
        for waiting in blockers.values():
            waiting.difference_update(ready)
    return order


# --------------------------------------------------------------------------- rendering


def _literal(value: Any) -> str:
    if value is None:
        return "None"
    if isinstance(value, str) and '"' in value and "'" not in value:
        return repr(value)
    return json.dumps(value, ensure_ascii=False)


_TEMPLATE = '''"""Temporary objects for tests, generated by `testence seed scaffold` from {source}.

Every object a test creates carries MARKER in its name (`temp_name`); `temp_sweeper`
deletes every marked object after the test, dependents first, and asserts that none is
left. Edit freely: once this file changes, regeneration leaves it alone.

Use it from a conftest.py: `pytest_plugins = ["{module}"]`. Under parallel workers give
each worker its own marker, or the sweepers delete each other's objects.
"""

from __future__ import annotations

import time
import urllib.parse
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import pytest

from testence.api import ApiClient

MARKER = {marker}
#: How long a DELETE answered with 409 (a dependent still being removed) is repeated.
CONFLICT_TIMEOUT_S = 5.0
POLL_S = 0.25


def temp_name(ticket: str, label: str) -> str:
    """A name the sweeper recognises as temporary: ``<ticket> <label> <MARKER>``."""
    return f"{{ticket}} {{label}} {{MARKER}}"


@dataclass(frozen=True)
class Collection:
    name: str
    list_path: str
    item_path: str
    id_param: str
    id_field: str
    name_field: str
    search_param: str | None = None
    items_key: str | None = None
    parent: str | None = None
    parent_param: str | None = None


COLLECTIONS: dict[str, Collection] = {{
{collections}
}}

#: Dependents first: an object is deleted only after everything that refers to it.
DELETE_ORDER: tuple[str, ...] = ({order})


class Sweeper:
    """Find, delete and prove absent every object whose name carries the marker."""

    def __init__(self, api: ApiClient, marker: str = MARKER) -> None:
        self.api = api
        self.marker = marker

    def create(
        self,
        collection: str,
        ticket: str,
        label: str,
        parent_id: Any = None,
        **fields: Any,
    ) -> dict[str, Any]:
        """POST a marked object; ``fields`` are the rest of the request body."""
        spec = COLLECTIONS[collection]
        body = {{spec.name_field: temp_name(ticket, label), **fields}}
        response = self.api.post(self._list_path(spec, parent_id), body)
        if not response.ok:
            raise AssertionError(
                f"creating {{collection}} returned HTTP {{response.status}}: {{response.body[:300]}}"
            )
        created = response.json
        assert isinstance(created, dict), f"creating {{collection}} returned {{created!r}}"
        return created

    def find(self, collection: str) -> list[tuple[str, dict[str, Any]]]:
        """Marked objects of ``collection`` as (item path, object) pairs."""
        spec = COLLECTIONS[collection]
        parents: list[Any] = [None]
        if spec.parent is not None:
            parent_spec = COLLECTIONS[spec.parent]
            parents = [item[parent_spec.id_field] for _, item in self.find(spec.parent)]
        found: list[tuple[str, dict[str, Any]]] = []
        for parent_id in parents:
            path = self._list_path(spec, parent_id)
            if spec.search_param:
                query = urllib.parse.urlencode({{spec.search_param: self.marker}})
                path = f"{{path}}?{{query}}"
            response = self.api.get_fresh(path)
            if not response.ok:
                raise AssertionError(f"GET {{path}} returned HTTP {{response.status}}")
            body = response.json
            items = body
            if spec.items_key and isinstance(body, dict):
                items = body.get(spec.items_key, [])
            assert isinstance(items, list), f"GET {{path}} did not return a list: {{body!r:.200}}"
            for item in items:
                if isinstance(item, dict) and self.marker in str(item.get(spec.name_field, "")):
                    found.append((self._item_path(spec, item[spec.id_field], parent_id), item))
        return found

    def delete(self, path: str) -> None:
        """DELETE one object, repeating on 409 for a while, then require GET to answer 404."""
        deadline = time.monotonic() + CONFLICT_TIMEOUT_S
        while True:
            response = self.api.delete(path)
            if response.status != 409 or time.monotonic() >= deadline:
                break
            time.sleep(POLL_S)
        if not (response.ok or response.status == 404):
            raise AssertionError(
                f"DELETE {{path}} returned HTTP {{response.status}}: {{response.body[:300]}}"
            )
        while True:
            status = self.api.get_fresh(path).status
            if status == 404:
                return
            if time.monotonic() >= deadline:
                raise AssertionError(f"expected 404 after DELETE {{path}}, got {{status}}")
            time.sleep(POLL_S)

    def sweep(self) -> dict[str, int]:
        """Delete every marked object in DELETE_ORDER; return how many per collection."""
        deleted: dict[str, int] = {{}}
        for collection in DELETE_ORDER:
            items = self.find(collection)
            for path, _ in items:
                self.delete(path)
            deleted[collection] = len(items)
        return deleted

    def assert_clean(self) -> None:
        """Nothing marked is left in any collection."""
        left = {{name: len(items) for name in DELETE_ORDER if (items := self.find(name))}}
        assert not left, f"temporary objects left after cleanup: {{left}}"

    @staticmethod
    def _list_path(spec: Collection, parent_id: Any) -> str:
        if spec.parent_param is None:
            return spec.list_path
        return spec.list_path.replace("{{" + spec.parent_param + "}}", str(parent_id))

    def _item_path(self, spec: Collection, item_id: Any, parent_id: Any) -> str:
        path = spec.item_path.replace("{{" + spec.id_param + "}}", str(item_id))
        if spec.parent_param is not None:
            path = path.replace("{{" + spec.parent_param + "}}", str(parent_id))
        return path


@pytest.fixture
def temp_sweeper(testence_api: ApiClient) -> Iterator[Sweeper]:
    """A sweeper whose teardown deletes every marked object and proves none is left."""
    sweeper = Sweeper(testence_api)
    yield sweeper
    sweeper.sweep()
    sweeper.assert_clean()
{factories}'''

_FACTORY = '''

@pytest.fixture
def make_temp_{singular}(temp_sweeper: Sweeper) -> Callable[..., dict[str, Any]]:
    """Create a marked {name} object: ``make_temp_{singular}(ticket, label{parent_hint}, **fields)``."""

    def make(ticket: str, label: str{parent_arg}, **fields: Any) -> dict[str, Any]:
        return temp_sweeper.create({name_literal}, ticket, label{parent_pass}, **fields)

    return make
'''


def render(
    collections: list[Collection], order: list[str], *, marker: str, source: str, module: str
) -> str:
    rows = []
    for collection in sorted(collections, key=lambda c: order.index(c.name)):
        fields = {
            "name": collection.name,
            "list_path": collection.list_path,
            "item_path": collection.item_path,
            "id_param": collection.id_param,
            "id_field": collection.id_field,
            "name_field": collection.name_field,
            "search_param": collection.search_param,
            "items_key": collection.items_key,
            "parent": collection.parent,
            "parent_param": collection.parent_param,
        }
        arguments = "".join(
            f"        {key}={_literal(value)},\n"
            for key, value in fields.items()
            if value is not None
        )
        rows.append(f"    {_literal(collection.name)}: Collection(\n{arguments}    ),")
    factories = "".join(
        _FACTORY.format(
            singular=_identifier(_singular(c.name)),
            name=c.name,
            name_literal=_literal(c.name),
            parent_hint=", parent_id" if c.parent else "",
            parent_arg=", parent_id: Any" if c.parent else "",
            parent_pass=", parent_id" if c.parent else "",
        )
        for c in sorted(collections, key=lambda c: c.name)
    )
    order_literal = ", ".join(_literal(name) for name in order) + ("," if len(order) == 1 else "")
    return _TEMPLATE.format(
        source=source.replace('"""', "'''"),
        module=module,
        marker=_literal(marker),
        collections="\n".join(rows),
        order=order_literal,
        factories=factories,
    )


# --------------------------------------------------------------------------- writing


def _digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


_STAMP = re.compile(rf"^# {re.escape(MARKER)} sha256=(?P<digest>[0-9a-f]{{16}})$")


def _untouched(existing: str) -> bool:
    first, _, rest = existing.partition("\n")
    match = _STAMP.match(first)
    return match is not None and match.group("digest") == _digest(rest)


def scaffold(
    openapi: str,
    out: Path | str,
    *,
    marker: str = "(temp)",
    collections: list[str] | None = None,
) -> dict[str, Any]:
    """Write the fixture module; return a ``testence/seed-scaffold/1`` document."""
    if not marker.strip():
        raise SeedError("--marker must not be empty: it is what the sweeper deletes by")
    document = load_openapi(openapi)
    found, skipped = analyse(document)
    by_name = {c.name: c for c in found}
    if collections:
        unknown = sorted(set(collections) - set(by_name))
        if unknown:
            available = ", ".join(sorted(by_name)) or "none"
            reasons = {entry["name"]: entry["reason"] for entry in skipped}
            details = "; ".join(f"{name}: {reasons.get(name, 'not found')}" for name in unknown)
            raise SeedError(f"unusable collection(s): {details} (usable: {available})")
        selected = [by_name[name] for name in collections]
        for collection in selected:
            if collection.parent and collection.parent not in collections:
                raise SeedError(
                    f"{collection.name} is nested under {collection.parent}; add "
                    f"{collection.parent} to --collections so its objects can be found"
                )
    else:
        selected = found
    if not selected:
        raise SeedError("no deletable collection (a list GET, an item DELETE and a name field)")
    order = delete_order(selected)
    target = Path(out)
    module = target.stem
    body = render(selected, order, marker=marker, source=Path(openapi).name, module=module)
    content = f"# {MARKER} sha256={_digest(body)}\n{body}"
    if target.exists():
        existing = target.read_text(encoding="utf-8")
        if existing == content:
            status = "unchanged"
        elif _untouched(existing):
            status = "updated"
        else:
            status = "kept"
    else:
        status = "created"
    if status in {"created", "updated"}:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
    return {
        "schema": SEED_SCHEMA,
        "source": openapi,
        "out": str(target),
        "status": status,
        "marker": marker,
        "collections": [c.describe() for c in sorted(selected, key=lambda c: order.index(c.name))],
        "delete_order": order,
        "skipped": skipped,
    }
