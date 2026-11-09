"""The target's build at the start and end of a run (stage 7, T04).

A shared environment is rebuilt while suites run against it. A run that does not
know which build it saw cannot tell a product failure from a stale environment, and a
run that saw two builds mixes results nobody can compare.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import pytest

from testence import target_info
from testence.application import inspect_run
from testence.evidence import RUN_ID_ENV
from testence.export import export_run
from testence.loopback import LoopbackHTTPServer
from testence.metrics import load_run
from testence.summary import render_summary
from tests.owned_pytest import run_pytest

ROOT = Path(__file__).parents[1]


class _Builds(BaseHTTPRequestHandler):
    """Answers the first read with one commit and every later read with another."""

    reads = 0

    def do_GET(self) -> None:  # noqa: N802 - http.server's name
        if self.path != "/api/info":
            self.send_response(404)
            self.end_headers()
            return
        type(self).reads += 1
        commit = "aaa111" if type(self).reads == 1 else "bbb222"
        body = json.dumps(
            [
                {"name": "backend", "git": {"commit": commit}},
                {"name": "frontend", "git": {"commit": "fff"}},
            ]
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass


@pytest.fixture(scope="module")
def target() -> Iterator[str]:
    server = LoopbackHTTPServer(("127.0.0.1", 0), _Builds)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def _run(project: Path) -> tuple[subprocess.CompletedProcess[str], Path]:
    env = os.environ.copy()
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env.pop(RUN_ID_ENV, None)
    env.pop("PYTEST_XDIST_WORKER", None)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "src"), value] if (value := env.get("PYTHONPATH")) else [str(ROOT / "src")]
    )
    result = run_pytest(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "testence.pytest_plugin",
            "--rootdir",
            str(project),
            "--basetemp",
            str(project / ".pytest-tmp"),
            "--testence-headless",
            "-q",
        ],
        cwd=project,
        env=env,
    )
    (run_dir,) = (project / "runs").iterdir()
    return result, run_dir


def _project(tmp_path: Path, settings: dict) -> Path:
    (tmp_path / "test_plain.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    (tmp_path / "testence.json").write_text(json.dumps(settings), encoding="utf-8")
    return tmp_path


def test_a_build_replaced_during_the_run_is_reported_everywhere(
    target: str, tmp_path: Path
) -> None:
    _Builds.reads = 0
    project = _project(
        tmp_path,
        {
            "base_url": target,
            "target_info": {
                "path": "/api/info",
                "fields": {"backend": "/0/git/commit", "frontend": "/1/git/commit"},
            },
        },
    )
    result, run_dir = _run(project)
    assert result.returncode == 0, result.stdout + result.stderr
    events = [e for e in load_run(run_dir) if e["kind"] == "target.info"]
    assert [(e["phase"], e["fields"]["backend"]) for e in events] == [
        ("start", "aaa111"),
        ("end", "bbb222"),
    ]
    assert events[1]["changed"] is True

    inspected = inspect_run(run_dir)["target"]
    assert inspected["changed"] is True
    assert inspected["start"]["fields"] == {"backend": "aaa111", "frontend": "fff"}

    summary = render_summary(run_dir)
    assert "| Target | backend=aaa111, frontend=fff |" in summary
    assert "the target changed during the run" in summary

    allure = export_run(run_dir, "allure", tmp_path / "allure")
    environment = next(p for p in allure if p.name == "environment.properties").read_text()
    assert "target.backend=aaa111" in environment and "target.changed=true" in environment

    junit = export_run(run_dir, "junit", tmp_path / "junit")
    xml = next(p for p in junit if p.suffix == ".xml").read_text(encoding="utf-8")
    assert 'name="testence.target.backend" value="aaa111"' in xml

    from testence.report import render_report

    html = render_report(run_dir, tmp_path / "report.html").read_text(encoding="utf-8")
    # The page reads target.info from the events it embeds.
    assert "bbb222" in html and "aaa111" in html and "targetEnd?.changed" in html


def test_an_unreadable_endpoint_is_recorded_and_the_run_goes_on(tmp_path: Path) -> None:
    project = _project(
        tmp_path,
        {"base_url": "http://127.0.0.1:9", "target_info": {"path": "/info", "timeout_ms": 500}},
    )
    result, run_dir = _run(project)
    assert result.returncode == 0, result.stdout + result.stderr
    start, end = [e for e in load_run(run_dir) if e["kind"] == "target.info"]
    assert "error" in start and end["changed"] is False
    assert "could not be read" in target_info.describe(start)


def test_parse_spec_accepts_a_path_or_an_object_and_refuses_the_rest() -> None:
    assert target_info.parse_spec("/info") == target_info.TargetInfoSpec("/info")
    assert target_info.parse_spec(None) is None
    spec = target_info.parse_spec({"path": "/i", "fields": {"v": "/version"}, "timeout_ms": 900})
    assert spec == target_info.TargetInfoSpec("/i", {"v": "/version"}, 900)
    for wrong in (
        42,
        {"path": ""},
        {"path": "/i", "fields": {"v": "version"}},
        {"path": "/i", "timeout_ms": 10},
        {"path": "/i", "auth": True},
    ):
        with pytest.raises(ValueError):
            target_info.parse_spec(wrong)


def test_pointer_reads_lists_maps_and_escapes() -> None:
    document = {"a/b": [{"~c": 1}]}
    assert target_info._pointer(document, "/a~1b/0/~0c") == 1
    assert target_info._pointer(document, "/a~1b/5") is None
    assert target_info._pointer(document, "/missing") is None
    assert not target_info.changed({"fields": {"v": "1"}}, {"error": "HTTP 500"})
    assert target_info.changed({"fields": {"v": "1"}}, {"fields": {"v": "2"}})
