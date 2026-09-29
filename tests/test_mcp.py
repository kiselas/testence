"""The narrow MCP server (product review 2026-09-28, P1-3).

An agent that could not drive Testence from its own tool loop had to shell out and parse
text. ``testence mcp`` gives it the seven calls the write-and-prove loop needs, over
stdio, with page text redacted and nothing but protocol on stdout.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from testence.evidence import RUN_ID_ENV
from testence.mcp import PROTOCOL_VERSIONS, TOOLS, McpServer
from tests.mock_app import MockApp

ROOT = Path(__file__).parents[1]


def _call(server: McpServer, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    reply = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        }
    )
    assert reply is not None and "result" in reply, reply
    return reply["result"]


def _payload(result: dict[str, Any]) -> Any:
    assert not result["isError"], result["content"][0]["text"]
    return json.loads(result["content"][0]["text"])


def test_initialize_negotiates_a_known_protocol_version(tmp_path):
    server = McpServer(tmp_path)
    for asked, expected in (("2024-11-05", "2024-11-05"), ("1999-01-01", PROTOCOL_VERSIONS[0])):
        reply = server.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": asked},
            }
        )
        assert reply is not None
        assert reply["result"]["protocolVersion"] == expected
        assert reply["result"]["serverInfo"]["name"] == "testence"
        assert "tools" in reply["result"]["capabilities"]


def test_notifications_are_never_answered_and_bad_requests_are_errors(tmp_path):
    server = McpServer(tmp_path)
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert server.handle({"jsonrpc": "2.0", "id": 2, "method": "ping"})["result"] == {}  # type: ignore[index]
    unknown = server.handle({"jsonrpc": "2.0", "id": 3, "method": "resources/list"})
    assert unknown is not None and unknown["error"]["code"] == -32601
    invalid = server.handle({"id": 4, "method": "ping"})
    assert invalid is not None and invalid["error"]["code"] == -32600


def test_the_seven_tools_have_schemas(tmp_path):
    reply = McpServer(tmp_path).handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert reply is not None
    names = [tool["name"] for tool in reply["result"]["tools"]]
    assert names == [tool["name"] for tool in TOOLS]
    assert len(names) == 7 and all(name.startswith("testence_") for name in names)
    for tool in TOOLS:
        assert tool["description"] and tool["inputSchema"]["type"] == "object"


def test_serve_answers_line_by_line_and_survives_garbage(tmp_path):
    lines = [
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}),
        "",
        "{this is not json",
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
    ]
    out = io.StringIO()
    McpServer(tmp_path).serve(io.StringIO("\n".join(lines) + "\n"), out)
    replies = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [reply.get("id") for reply in replies] == [1, None, 2]
    assert replies[1]["error"]["code"] == -32700


def test_tool_failures_are_results_the_agent_can_read(tmp_path):
    def no_browser(_settings: Any) -> Any:
        pytest.fail("a rejected call must not start a browser")

    server = McpServer(tmp_path, engine_factory=no_browser)
    unknown = _call(server, "testence_nothing")
    assert unknown["isError"] and "unknown tool" in unknown["content"][0]["text"]
    outside = _call(server, "testence_inspect", {"run_dir": str(tmp_path.parent)})
    assert outside["isError"] and "inside the project" in outside["content"][0]["text"]
    missing = _call(server, "testence_inspect", {"run_dir": "runs/r-none"})
    assert missing["isError"] and "cannot inspect" in missing["content"][0]["text"]
    bad = _call(server, "testence_click", {"target": {"kind": "xpath", "value": "//a"}})
    assert bad["isError"] and "target.kind must be one of" in bad["content"][0]["text"]
    args = _call(server, "testence_run", {"pytest_args": "-q"})
    assert args["isError"] and "list of strings" in args["content"][0]["text"]


class _FakeEngine:
    def __init__(self, _settings: Any) -> None:
        self.calls: list[tuple[str, Any]] = []

    def start(self) -> None:
        self.calls.append(("start", None))

    def stop(self) -> None:
        self.calls.append(("stop", None))

    def goto(self, url: str) -> None:
        self.calls.append(("goto", url))

    def settle(self, _timeout_ms: int = 0) -> bool:
        return True

    def current_url(self) -> str:
        return "http://app.test/widgets"

    def aria_snapshot(self) -> str:
        return '- heading "Widgets"\n- text: api key sk-live-abcdef1234567890abcdef'

    def candidate_elements(self) -> list[dict[str, Any]]:
        role = {"kind": "role", "value": "button", "name": "Save"}
        return [
            {"target": role},
            {"target": dict(role)},  # a duplicate is listed once
            {"target": {"kind": "role", "value": "button", "name": "Delete"}},
            {"target": {"kind": "css", "value": "#name", "name": None}},
        ]

    def count(self, target: Any) -> int:
        return 2 if target.name == "Delete" else 1

    def click(self, target: Any) -> None:
        self.calls.append(("click", target.describe()))

    def fill(self, target: Any, value: str) -> None:
        self.calls.append(("fill", (target.describe(), value)))


@pytest.fixture
def explorer(tmp_path):
    engines: list[_FakeEngine] = []

    def factory(settings: Any) -> _FakeEngine:
        engines.append(_FakeEngine(settings))
        return engines[-1]

    server = McpServer(tmp_path, engine_factory=factory)
    yield server, engines
    server.close()


def test_a_snapshot_lists_targets_with_their_uniqueness(explorer):
    server, engines = explorer
    result = _payload(_call(server, "testence_snapshot", {"url": "/widgets"}))
    assert ("goto", "/widgets") in engines[0].calls
    assert result["url"] == "http://app.test/widgets"
    by_python = {element["python"]: element for element in result["elements"]}
    assert set(by_python) == {
        "Target('role', 'button', name='Save')",
        "Target('role', 'button', name='Delete')",
        "Target('css', '#name')",
    }
    assert by_python["Target('role', 'button', name='Save')"]["unique"] is True
    assert by_python["Target('role', 'button', name='Delete')"]["unique"] is False
    assert by_python["Target('role', 'button', name='Delete')"]["matches"] == 2


def test_page_text_is_redacted_before_the_agent_sees_it(explorer):
    server, _ = explorer
    result = _payload(_call(server, "testence_snapshot"))
    assert "sk-live-abcdef1234567890abcdef" not in result["aria"]
    assert "Widgets" in result["aria"]


def test_click_and_fill_drive_one_browser_and_do_not_echo_values(explorer):
    server, engines = explorer
    fill = _call(
        server,
        "testence_fill",
        {"target": {"kind": "label", "value": "Name"}, "value": "hunter2-secret"},
    )
    assert "hunter2-secret" not in fill["content"][0]["text"]
    assert _payload(fill)["characters"] == 14
    clicked = _payload(
        _call(
            server,
            "testence_click",
            {"target": {"kind": "role", "value": "button", "name": "Save"}},
        )
    )
    assert "role='button'" in clicked["clicked"]
    assert len(engines) == 1 and [c[0] for c in engines[0].calls].count("start") == 1


def test_closing_stops_the_browser(explorer):
    server, engines = explorer
    _call(server, "testence_snapshot")
    server.close()
    assert engines[0].calls[-1] == ("stop", None)


SUITE = """
def test_it_runs(testence_writer):
    assert testence_writer.run_id
"""


def test_run_inspect_and_suggest_work_on_a_real_run(tmp_path):
    (tmp_path / "test_tiny.py").write_text(SUITE.lstrip(), encoding="utf-8")
    (tmp_path / "testence.json").write_text("{}", encoding="utf-8")
    server = McpServer(tmp_path)
    ran = _payload(_call(server, "testence_run", {"pytest_args": ["test_tiny.py", "-q"]}))
    assert ran["exit_code"] == 0 and ran["run_dir"].startswith("runs/r-")
    assert ran["summary"]["execution"] == {"passed": 1}
    inspected = _payload(_call(server, "testence_inspect", {"run_dir": ran["run_dir"]}))
    assert inspected["tests"] == 1
    suggested = _payload(_call(server, "testence_oracle_suggest", {"run_dir": ran["run_dir"]}))
    assert suggested["candidates"] == [] and suggested["warnings"]


def test_the_cli_speaks_only_protocol_on_stdout(tmp_path):
    env = os.environ.copy()
    env.pop(RUN_ID_ENV, None)
    env["PYTHONPATH"] = str(ROOT / "src")
    requests = "\n".join(
        json.dumps(message)
        for message in (
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "testence_inspect", "arguments": {"run_dir": "runs/none"}},
            },
        )
    )
    completed = subprocess.run(
        [sys.executable, "-m", "testence.cli", "mcp", "--project", str(tmp_path)],
        input=requests + "\n",
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    replies = [json.loads(line) for line in completed.stdout.splitlines()]
    assert [reply["id"] for reply in replies] == [1, 2, 3]
    assert len(replies[1]["result"]["tools"]) == 7
    assert replies[2]["result"]["isError"] is True


def test_exploring_a_real_page(tmp_path, monkeypatch):
    """A real browser: the login page's controls come back as Targets that work."""
    (tmp_path / "testence.json").write_text('{"auth": "none"}', encoding="utf-8")
    monkeypatch.setenv("TESTENCE_DEBUG_PORT", "0")
    with MockApp() as app:
        monkeypatch.setenv("TESTENCE_BASE_URL", app.base_url)
        server = McpServer(tmp_path)
        try:
            page = _payload(_call(server, "testence_snapshot", {"url": "/login"}))
            targets = {element["python"]: element for element in page["elements"]}
            button = targets["Target('role', 'button', name='Sign in')"]
            assert button["unique"] is True
            assert "Sign in" in page["aria"]
            _payload(
                _call(
                    server,
                    "testence_fill",
                    {"target": {"kind": "label", "value": "Email"}, "value": "demo@example.test"},
                )
            )
            _payload(
                _call(
                    server,
                    "testence_click",
                    {"target": {"kind": "role", "value": "button", "name": "Sign in"}},
                )
            )
        finally:
            server.close()
