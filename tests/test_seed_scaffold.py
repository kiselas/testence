"""``testence seed scaffold``: ordered cleanup of temporary objects from an OpenAPI file."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from testence.api import Response
from testence.cli import main
from testence.seed import SeedError, analyse, delete_order, load_openapi, scaffold

ROOT = Path(__file__).resolve().parent.parent
OPENAPI = Path(__file__).parent / "fixtures" / "openapi_two_levels.json"


def _import(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"seed_{abs(hash(path))}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve annotations through it
    spec.loader.exec_module(module)
    return module


def test_references_two_levels_deep_order_the_cleanup_dependents_first() -> None:
    collections, skipped = analyse(load_openapi(str(OPENAPI)))
    by_name = {collection.name: collection for collection in collections}

    # comments -> posts through a $ref inside allOf; posts -> projects through project_id;
    # members are nested under /projects/{project_id}.
    assert by_name["comments"].depends_on == {"posts"}
    assert by_name["posts"].depends_on == {"projects"}
    assert by_name["members"].depends_on == {"projects"}
    assert by_name["members"].parent == "projects"
    order = delete_order(collections)
    assert order == ["comments", "members", "posts", "projects"]
    assert order.index("comments") < order.index("posts") < order.index("projects")
    # The server prefix, the search parameter and an object-wrapped list are carried over.
    assert by_name["posts"].list_path == "/api/v1/posts"
    assert (by_name["posts"].search_param, by_name["posts"].items_key) == ("q", "items")
    assert skipped == [
        {"name": "tokens", "reason": "no name/title/label field to carry the marker"}
    ]


def test_generated_module_imports_and_passes_ruff(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "conftest_seed.py"
    code = main(
        ["seed", "scaffold", "--openapi", str(OPENAPI), "--out", str(out), "--marker", "(temp)"]
        + ["--collections", "projects,posts,comments", "--json"]
    )
    assert code == 0
    result = json.loads(capsys.readouterr().out)
    assert result["delete_order"] == ["comments", "posts", "projects"]
    assert result["status"] == "created"

    for args in (["check"], ["format", "--check"]):
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "ruff",
                *args,
                "--config",
                str(ROOT / "pyproject.toml"),
                str(out),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr

    module = _import(out)
    assert module.DELETE_ORDER == ("comments", "posts", "projects")
    assert module.temp_name("T-1", "first") == "T-1 first (temp)"
    assert "playwright" not in out.read_text(encoding="utf-8").lower()
    assert callable(module.make_temp_post)


class _FakeApi:
    """Answers like a small server: projects referenced by posts, a 409 until posts go."""

    def __init__(self) -> None:
        self.objects: dict[str, dict[str, Any]] = {
            "/api/v1/projects/1": {"id": 1, "name": "T-1 p (temp)"},
            "/api/v1/projects/2": {"id": 2, "name": "kept project"},
            "/api/v1/posts/7": {"id": 7, "title": "T-1 post (temp)", "project_id": 1},
        }
        self.calls: list[str] = []
        self.conflicts = 2

    def get_fresh(self, path: str) -> Response:
        self.calls.append(f"GET {path}")
        base = path.split("?", 1)[0]
        if base in self.objects:
            return Response(200, [], json.dumps(self.objects[base]))
        items = [obj for key, obj in self.objects.items() if key.rsplit("/", 1)[0] == base]
        if base.endswith("/members"):
            return Response(200, [], "[]")
        if base == "/api/v1/posts":
            return Response(200, [], json.dumps({"items": items, "total": len(items)}))
        if base in {"/api/v1/projects", "/api/v1/comments"}:
            return Response(200, [], json.dumps(items))
        return Response(404, [], "")

    def delete(self, path: str) -> Response:
        self.calls.append(f"DELETE {path}")
        if path == "/api/v1/projects/1" and "/api/v1/posts/7" in self.objects:
            return Response(409, [], "has posts")
        if path == "/api/v1/projects/1" and self.conflicts:
            self.conflicts -= 1  # the post's removal is still settling
            return Response(409, [], "has posts")
        self.objects.pop(path, None)
        return Response(204, [], "")


def test_sweeper_deletes_in_order_repeats_409_and_proves_absence(tmp_path: Path) -> None:
    out = tmp_path / "conftest_seed.py"
    scaffold(str(OPENAPI), out)
    module = _import(out)
    module.POLL_S = 0.0
    api = _FakeApi()

    deleted = module.Sweeper(api).sweep()

    assert deleted == {"comments": 0, "members": 0, "posts": 1, "projects": 1}
    deletes = [call for call in api.calls if call.startswith("DELETE")]
    assert deletes == ["DELETE /api/v1/posts/7"] + ["DELETE /api/v1/projects/1"] * 3
    assert "GET /api/v1/posts/7" in api.calls  # absence is read, not assumed
    assert set(api.objects) == {"/api/v1/projects/2"}
    module.Sweeper(api).assert_clean()

    api.objects["/api/v1/posts/8"] = {"id": 8, "title": "T-2 left (temp)", "project_id": 2}
    with pytest.raises(AssertionError, match="left after cleanup"):
        module.Sweeper(api).assert_clean()


def test_a_delete_that_does_not_remove_the_object_fails(tmp_path: Path) -> None:
    out = tmp_path / "conftest_seed.py"
    scaffold(str(OPENAPI), out)
    module = _import(out)
    module.POLL_S = 0.0
    module.CONFLICT_TIMEOUT_S = 0.0

    class _Sticky(_FakeApi):
        def delete(self, path: str) -> Response:
            return Response(200, [], "")

    with pytest.raises(AssertionError, match="expected 404 after DELETE /api/v1/posts/7, got 200"):
        module.Sweeper(_Sticky()).sweep()


def test_selection_errors_cycles_and_yaml_without_pyyaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "seed.py"
    with pytest.raises(SeedError, match="nested under projects"):
        scaffold(str(OPENAPI), out, collections=["members"])
    with pytest.raises(SeedError, match="tokens: no name"):
        scaffold(str(OPENAPI), out, collections=["tokens"])

    collections, _ = analyse(load_openapi(str(OPENAPI)))
    by_name = {collection.name: collection for collection in collections}
    by_name["projects"].depends_on.add("posts")
    with pytest.raises(SeedError, match="cycle"):
        delete_order([by_name["projects"], by_name["posts"]])

    yaml_file = tmp_path / "openapi.yaml"
    yaml_file.write_text("openapi: 3.0.0\npaths: {}\n", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "yaml", None)
    with pytest.raises(SeedError, match="needs PyYAML"):
        load_openapi(str(yaml_file))


def test_rerun_is_idempotent_and_keeps_an_edited_module(tmp_path: Path) -> None:
    out = tmp_path / "conftest_seed.py"
    assert scaffold(str(OPENAPI), out)["status"] == "created"
    assert scaffold(str(OPENAPI), out)["status"] == "unchanged"
    assert scaffold(str(OPENAPI), out, marker="[tmp]")["status"] == "updated"
    out.write_text(out.read_text(encoding="utf-8") + "\n# local change\n", encoding="utf-8")
    assert scaffold(str(OPENAPI), out)["status"] == "kept"
    assert out.read_text(encoding="utf-8").endswith("# local change\n")
