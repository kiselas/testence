"""Oracle discovery: ``testence oracle suggest`` turns the API traffic of a run into checks.

Writing the first API oracle for an application used to mean reading its network tab by
hand. The run already saw the mutation, the read that follows it and the shape of the
data (product review 2026-09-28, P1-1).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from testence.engine import NetRecord
from testence.evidence import RUN_ID_ENV
from testence.oracle_suggest import net_digest, render, suggest
from tests.mock_app import PASSWORD, USER, MockApp

ROOT = Path(__file__).parents[1]

BODY = '{"id": "w7", "name": "edge", "cidr": "10.0.0.0/8", "state": "saved"}'


def _widgets(*extra: NetRecord) -> list[NetRecord]:
    return [
        NetRecord(
            "POST",
            "http://app.test/api/v1/widgets",
            201,
            0,
            5,
            '{"name": "edge", "cidr": "10.0.0.0/8"}',
            BODY,
        ),
        NetRecord("GET", "http://app.test/api/v1/widgets/w7", 200, 1, 5),
        *extra,
    ]


def _candidates(records: list[NetRecord], *, bodies: bool = True) -> dict[str, Any]:
    digest = net_digest(records, bodies=bodies)
    assert digest is not None
    return suggest([{"kind": "net", "test": "t::create", **digest}])


def test_a_create_is_proved_by_the_read_the_app_made_itself():
    result = _candidates(_widgets())
    (candidate,) = result["candidates"]
    assert candidate["mutation"] == "POST /api/v1/widgets"
    assert candidate["read"] == "GET /api/v1/widgets/{id}"
    assert candidate["read_source"] == "traffic"
    assert candidate["fields"] == ["cidr", "name"]
    assert candidate["strength"] == "strong"
    assert result["warnings"] == []


def test_the_identifier_never_reaches_the_ledger():
    digest = net_digest(_widgets(), bodies=True)
    assert "w7" not in json.dumps(digest)
    assert "edge" not in json.dumps(digest)


def test_a_delete_is_proved_absent_not_by_a_predicate():
    result = _candidates(
        _widgets(NetRecord("DELETE", "http://app.test/api/v1/widgets/w7", 204, 2, 5))
    )
    delete = next(c for c in result["candidates"] if c["mutation"].startswith("DELETE"))
    assert delete["expect"] == "absent"
    assert "ExpectedState.absent(" in delete["snippet"]
    assert 'RequestExpectation(f"/api/v1/widgets/{entity_id}", "DELETE"' in delete["snippet"]


def test_a_failed_mutation_proves_nothing():
    failed = NetRecord("POST", "http://app.test/api/v1/widgets", 422, 0, 5, "{}", '{"detail": "x"}')
    result = _candidates([failed])
    assert result["candidates"] == []
    assert "no successful mutation" in result["warnings"][0]


def test_a_run_without_captured_bodies_says_how_to_get_them():
    bare = NetRecord("POST", "http://app.test/api/v1/widgets", 201, 0, 5)
    result = _candidates([bare], bodies=False)
    (candidate,) = result["candidates"]
    assert candidate["fields"] == []
    assert any("request body was not captured" in note for note in candidate["notes"])
    assert any("network_bodies" in warning for warning in result["warnings"])


def test_a_ledger_without_traffic_is_explained_not_empty():
    result = suggest([{"kind": "test.end", "test": "t"}])
    assert result["candidates"] == []
    assert "no API traffic" in result["warnings"][0]


def test_every_snippet_is_valid_python():
    records = _widgets(NetRecord("DELETE", "http://app.test/api/v1/widgets/w7", 204, 2, 5))
    for candidate in _candidates(records)["candidates"]:
        compile(candidate["snippet"], "<suggestion>", "eval")
    assert "save_and_verify_state(" in render(_candidates(records))


def test_a_polling_page_cannot_grow_the_ledger():
    polling = [NetRecord("GET", f"http://app.test/api/v1/poll/{n}", 200, n, 1) for n in range(500)]
    digest = net_digest(polling, bodies=False)
    assert digest is not None and len(json.dumps(digest)) < 8_000


FORM = {"auth": "form", "login_path": "/login", "success_url_contains": "/app"}

SUITE = """
from testence.engine import Target


def test_save_a_widget(ex):
    ex.goto("/widgets/new")
    ex.fill(Target("css", "#name"), "edge")
    ex.fill(Target("css", "#cidr"), "10.0.0.0/8")
    ex.click(Target("css", "#save-widget"))
    ex.expect_visible(Target("css", "#saved[data-id]"))
"""


def _record(project: Path, settings: dict[str, Any]) -> Path:
    (project / "test_widgets.py").write_text(SUITE.lstrip(), encoding="utf-8")
    (project / "testence.json").write_text(json.dumps(settings), encoding="utf-8")
    with MockApp() as app:
        env = os.environ.copy()
        env.pop(RUN_ID_ENV, None)
        env.update(
            PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
            PYTHONPATH=str(ROOT / "src"),
            TESTENCE_BASE_URL=app.base_url,
            TESTENCE_USER=USER,
            TESTENCE_PASSWORD=PASSWORD,
        )
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-p",
                "testence.pytest_plugin",
                "--rootdir",
                str(project),
                "-p",
                "no:cacheprovider",
                "--testence-headless",
                "-q",
            ],
            cwd=project,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=300,
        )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return next((project / "runs").iterdir())


def _suggest(run: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    return subprocess.run(
        [sys.executable, "-m", "testence.cli", "oracle", "suggest", str(run), "--json"],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def test_a_real_run_yields_the_oracle_for_the_save(tmp_path: Path):
    project = tmp_path / "recorded"
    project.mkdir()
    settings = {**FORM, "extra": {"capture_policy": {"network_bodies": True}}}
    run = _record(project, settings)
    completed = _suggest(run)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    (candidate,) = result["candidates"]
    assert candidate["mutation"] == "POST /api/v1/widgets"
    assert candidate["fields"] == ["cidr", "name"]
    assert result["warnings"] == []
    assert "edge" not in (run / "run.jsonl").read_text(encoding="utf-8").split('"kind":"net"')[1]


def test_without_body_capture_the_run_still_yields_the_endpoint(tmp_path: Path):
    project = tmp_path / "bare"
    project.mkdir()
    run = _record(project, FORM)
    result = json.loads(_suggest(run).stdout)
    (candidate,) = result["candidates"]
    assert candidate["mutation"] == "POST /api/v1/widgets"
    assert any("network_bodies" in warning for warning in result["warnings"])


def test_a_mistyped_run_directory_is_an_error_not_an_empty_answer(tmp_path: Path):
    completed = _suggest(tmp_path / "no-such-run")
    assert completed.returncode == 2
    assert "oracle suggest failed" in completed.stderr
