"""Two tails of the first P1 items: ``ex.expect_request`` and ``testence auth export``.

``expect_request`` scopes a request and its response to the block that causes them (P1-1);
``auth export`` produces the file ``auth: "storage-state"`` reads (P1-8).
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from testence.dsl import Actions
from testence.engine import NetRecord
from testence.evidence import RUN_ID_ENV
from testence.oracle import RequestExpectation
from tests.mock_app import PASSWORD, USER, MockApp

ROOT = Path(__file__).parents[1]


class _Engine:
    """A network log a test can script; waits answer from it like the real engine."""

    def __init__(self, later: list[NetRecord] | None = None) -> None:
        self.log: list[NetRecord] = [NetRecord("GET", "http://x/api/w", 200, 0, 1)]
        self.later = later or []

    def capabilities(self) -> frozenset[str]:
        return frozenset({"browser.network"})

    def net_mark(self) -> int:
        return len(self.log)

    def occur(self) -> None:
        self.log.extend(self.later)

    def wait_for_response(self, fragment, *, method=None, since=0, timeout_ms=0, predicate=None):
        for record in self.log[since:]:
            if fragment in record.url and (method is None or record.method == method):
                if predicate is None or predicate(record):
                    if record.status is not None:
                        return record
        return None

    def wait_for_request(self, fragment, *, method=None, since=0, timeout_ms=0):
        return any(
            fragment in r.url and (method is None or r.method == method) for r in self.log[since:]
        )


def _actions(engine: _Engine) -> Actions:
    events: list[dict[str, Any]] = []
    writer = SimpleNamespace(emit=lambda kind, **payload: events.append({"kind": kind, **payload}))
    actions = Actions(engine, writer, "t")  # type: ignore[arg-type]
    actions.events = events  # type: ignore[attr-defined]
    return actions


def _post(status: int | None, body: str | None = None, **flags: Any) -> NetRecord:
    return NetRecord("POST", "http://x/api/widgets", status, 0, 1, None, body, **flags)


def test_the_block_yields_the_response_it_caused():
    engine = _Engine([_post(201, '{"id": "w1"}')])
    with _actions(engine).expect_request("/api/widgets", method="POST") as sent:
        engine.occur()
    assert sent.record is not None and sent.record.status == 201
    assert sent.response.json_body() == {"id": "w1"}


def test_an_earlier_request_cannot_satisfy_the_block():
    engine = _Engine()
    engine.log.append(_post(201))  # before the block
    with pytest.raises(AssertionError, match="sent no request matching POST /api/widgets"):
        with _actions(engine).expect_request("/api/widgets", method="POST"):
            pass


def test_a_request_without_a_response_says_the_server_may_have_applied_it():
    engine = _Engine([_post(None)])
    with pytest.raises(AssertionError, match="no response arrived.*ask an oracle"):
        with _actions(engine).expect_request("/api/widgets", method="POST"):
            engine.occur()


def test_a_request_expectation_fixes_the_method_and_binds_the_record():
    other = NetRecord("PATCH", "http://x/api/widgets", 200, 0, 1)
    engine = _Engine([other, _post(201)])
    expectation = RequestExpectation("/api/widgets", "POST")
    with _actions(engine).expect_request(expectation) as sent:
        engine.occur()
    assert sent.response.method == "POST"


def test_a_mocked_response_is_delivered_and_marked():
    engine = _Engine([_post(201, "{}", mocked=True)])
    with _actions(engine).expect_request("/api/widgets", method="POST") as sent:
        engine.occur()
    assert sent.response.mocked is True


def test_a_failure_inside_the_block_is_reported_and_the_wait_is_skipped():
    engine = _Engine()
    # Like every step, the block reports its own failure with the cause named.
    with pytest.raises(AssertionError, match="RuntimeError: the block failed"):
        with _actions(engine).expect_request("/api/widgets", method="POST"):
            raise RuntimeError("the block failed")


def test_the_response_is_unavailable_before_the_block_ends():
    engine = _Engine([_post(201)])
    with _actions(engine).expect_request("/api/widgets", method="POST") as sent:
        with pytest.raises(RuntimeError, match="read it after the block"):
            sent.response  # noqa: B018
        engine.occur()


def _run_cli(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop(RUN_ID_ENV, None)
    env.update(PYTHONPATH=str(ROOT / "src"), TESTENCE_USER=USER, TESTENCE_PASSWORD=PASSWORD)
    return subprocess.run(
        [sys.executable, "-m", "testence.cli", *args],
        cwd=project,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=300,
    )


def test_export_refuses_where_there_is_no_login(tmp_path):
    (tmp_path / "testence.json").write_text('{"auth": "none", "base_url": "http://x"}')
    result = _run_cli(tmp_path, "auth", "export")
    assert result.returncode == 2 and "no login to save" in result.stderr


def test_export_needs_a_base_url_and_will_not_overwrite(tmp_path):
    (tmp_path / "testence.json").write_text('{"auth": "form"}')
    assert "base_url is not set" in _run_cli(tmp_path, "auth", "export").stderr
    (tmp_path / "testence.json").write_text('{"auth": "form", "base_url": "http://x"}')
    (tmp_path / "auth.json").write_text("keep me")
    result = _run_cli(tmp_path, "auth", "export")
    assert result.returncode == 2 and "pass --force" in result.stderr
    assert (tmp_path / "auth.json").read_text() == "keep me"


SUITE = f"""
from testence.engine import Target


def test_it_starts_signed_in(ex):
    ex.goto("/app")
    ex.expect_text(Target("css", "#whoami"), "signed in as {USER}")
"""


def _env(app_url: str) -> dict[str, str]:
    env = os.environ.copy()
    env.pop(RUN_ID_ENV, None)
    env.update(
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
        PYTHONPATH=str(ROOT / "src"),
        TESTENCE_BASE_URL=app_url,
        TESTENCE_USER=USER,
        TESTENCE_PASSWORD=PASSWORD,
    )
    return env


def test_an_exported_session_starts_a_fresh_run_signed_in(tmp_path: Path):
    """The round trip: log in once with `auth export`, then run from the saved file."""
    project = tmp_path / "roundtrip"
    project.mkdir()
    (project / "test_signed_in.py").write_text(SUITE.lstrip(), encoding="utf-8")
    login = {"auth": "form", "login_path": "/login", "success_url_contains": "/app"}
    with MockApp() as app:
        (project / "testence.json").write_text(json.dumps(login), encoding="utf-8")
        exported = subprocess.run(
            [sys.executable, "-m", "testence.cli", "auth", "export", "--json"],
            cwd=project,
            env=_env(app.base_url),
            text=True,
            capture_output=True,
            check=False,
            timeout=300,
        )
        assert exported.returncode == 0, exported.stderr
        summary = json.loads(exported.stdout)
        assert summary["cookies"] == ["session_id"]
        state_file = project / "auth.json"
        state = json.loads(state_file.read_text(encoding="utf-8"))
        assert [cookie["name"] for cookie in state["cookies"]] == ["session_id"]
        assert PASSWORD not in state_file.read_text(encoding="utf-8")
        if os.name == "posix":
            assert stat.S_IMODE(state_file.stat().st_mode) == 0o600

        saved = {"auth": "storage-state", "storage_state": "auth.json"}
        (project / "testence.json").write_text(json.dumps(saved), encoding="utf-8")
        env = _env(app.base_url)
        env.pop("TESTENCE_USER")
        env.pop("TESTENCE_PASSWORD")
        run = subprocess.run(
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
    assert run.returncode == 0, run.stdout + run.stderr


def test_a_real_expect_request_in_a_browser(tmp_path: Path):
    project = tmp_path / "expect"
    project.mkdir()
    (project / "test_expect.py").write_text(
        """
from testence.engine import Target


def test_the_save_sends_one_post(ex):
    ex.goto("/widgets/new")
    ex.fill(Target("css", "#name"), "edge")
    ex.fill(Target("css", "#cidr"), "10.0.0.0/8")
    with ex.expect_request("/api/v1/widgets", method="POST") as sent:
        ex.click(Target("css", "#save-widget"))
    assert sent.response.status == 201 and not sent.response.mocked
""".lstrip(),
        encoding="utf-8",
    )
    (project / "testence.json").write_text(
        json.dumps({"auth": "form", "login_path": "/login", "success_url_contains": "/app"}),
        encoding="utf-8",
    )
    with MockApp() as app:
        run = subprocess.run(
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
            env=_env(app.base_url),
            text=True,
            capture_output=True,
            check=False,
            timeout=300,
        )
    assert run.returncode == 0, run.stdout + run.stderr
