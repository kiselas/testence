"""A narrow MCP server: what an agent needs to write and prove a Testence test.

``testence mcp --project .`` speaks the Model Context Protocol over stdio (JSON-RPC 2.0,
one message per line). It exposes the loop an agent runs, not the whole framework:

- ``testence_doctor``: is the runtime and the target app reachable;
- ``testence_snapshot``: open a page and list what is on it, each element with the
  ``Target`` that addresses it and whether that Target is unique;
- ``testence_click`` / ``testence_fill``: try an interaction before writing it down;
- ``testence_run``: run pytest through ``testence run`` and get the run back;
- ``testence_inspect``: the outcome of a run;
- ``testence_oracle_suggest``: the API checks a finished run implies.

Nothing here calls a model, and the tests an agent writes still run without one
(ADR-0006). Page text goes through the project's redaction policy before it reaches the
agent, and a filled value is never echoed. stdout carries protocol messages only.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, TextIO

from testence import __version__

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
_TEXT_LIMIT = 20_000
_MAX_ELEMENTS = 200
_RUN_TIMEOUT_S = 900

_TARGET_SCHEMA = {
    "type": "object",
    "description": "Element address, as testence_snapshot returns it.",
    "properties": {
        "kind": {"enum": ["role", "label", "text", "testid", "placeholder", "css"]},
        "value": {"type": "string"},
        "name": {"type": "string", "description": "accessible name, for kind=role"},
        "nth": {"type": "integer", "description": "which of several matches, from 0"},
    },
    "required": ["kind", "value"],
}

TOOLS: list[dict[str, Any]] = [
    {
        "name": "testence_doctor",
        "description": "Check the Testence runtime. With target=true also reach the app's "
        "base_url, check the credentials and try the login once.",
        "inputSchema": {
            "type": "object",
            "properties": {"target": {"type": "boolean", "default": False}},
        },
    },
    {
        "name": "testence_snapshot",
        "description": "Open a page (a path on base_url or an absolute URL; omit to keep the "
        "current one) and list its interactive elements. Each element carries the Target "
        "that addresses it, the Python that spells it, and how many elements it matches "
        "(unique=true means it can be used as is).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "limit": {"type": "integer", "default": 60, "maximum": _MAX_ELEMENTS},
            },
        },
    },
    {
        "name": "testence_click",
        "description": "Click an element in the exploration browser, to see what happens "
        "before writing the step.",
        "inputSchema": {
            "type": "object",
            "properties": {"target": _TARGET_SCHEMA},
            "required": ["target"],
        },
    },
    {
        "name": "testence_fill",
        "description": "Fill a field in the exploration browser. The value is not echoed back.",
        "inputSchema": {
            "type": "object",
            "properties": {"target": _TARGET_SCHEMA, "value": {"type": "string"}},
            "required": ["target", "value"],
        },
    },
    {
        "name": "testence_run",
        "description": "Run pytest through `testence run` in the project and return the run: "
        "exit code, run directory and its summary. Arguments go to pytest unchanged.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pytest_args": {"type": "array", "items": {"type": "string"}, "default": []},
                "timeout_s": {"type": "integer", "default": 300, "maximum": _RUN_TIMEOUT_S},
            },
        },
    },
    {
        "name": "testence_inspect",
        "description": "The outcome of a run directory: execution and assurance counts, "
        "integrity errors, evidence packs of failures, flaky tests.",
        "inputSchema": {
            "type": "object",
            "properties": {"run_dir": {"type": "string"}},
            "required": ["run_dir"],
        },
    },
    {
        "name": "testence_oracle_suggest",
        "description": "The API checks a finished run implies: per successful mutation the "
        "read that proves it and a save_and_verify_state call to complete.",
        "inputSchema": {
            "type": "object",
            "properties": {"run_dir": {"type": "string"}},
            "required": ["run_dir"],
        },
    },
]


class ToolError(Exception):
    """A tool failed in a way the agent should read; it is a result, not a crash."""


def _python(target: dict[str, Any]) -> str:
    parts = [repr(target["kind"]), repr(target["value"])]
    if target.get("name"):
        parts.append(f"name={target['name']!r}")
    if target.get("nth") is not None:
        parts.append(f"nth={target['nth']}")
    return f"Target({', '.join(parts)})"


class McpServer:
    """One project, one lazily started exploration browser."""

    def __init__(
        self,
        project: Path | str = ".",
        *,
        headed: bool = False,
        engine_factory: Callable[[Any], Any] | None = None,
    ) -> None:
        self.project = Path(project).resolve()
        self.headed = headed
        self._engine_factory = engine_factory
        self._engine: Any = None
        self._settings: Any = None
        self._initialized = False

    # -- protocol ---------------------------------------------------------------------

    def handle(self, message: Any) -> dict[str, Any] | None:
        """One JSON-RPC message in, its response out (``None`` for a notification)."""
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return self._error(None, -32600, "invalid request")
        method = message.get("method")
        request_id = message.get("id")
        if not isinstance(method, str):
            return self._error(request_id, -32600, "invalid request")
        if request_id is None:  # a notification is never answered
            if method == "notifications/initialized":
                self._initialized = True
            return None
        params = message.get("params") or {}
        try:
            if method == "initialize":
                return self._result(request_id, self._initialize(params))
            if method == "ping":
                return self._result(request_id, {})
            if method == "tools/list":
                return self._result(request_id, {"tools": TOOLS})
            if method == "tools/call":
                return self._result(request_id, self._call(params))
        except ToolError as exc:
            return self._result(request_id, self._tool_result(str(exc), error=True))
        return self._error(request_id, -32601, f"method not found: {method}")

    def serve(self, reader: TextIO, writer: TextIO) -> None:
        """Answer one message per line until the client closes the input."""
        try:
            for line in reader:
                if not line.strip():
                    continue
                reply: dict[str, Any] | None
                try:
                    message = json.loads(line)
                except ValueError:
                    reply = self._error(None, -32700, "parse error")
                else:
                    reply = self.handle(message)
                if reply is not None:
                    writer.write(json.dumps(reply, separators=(",", ":")))
                    writer.write("\n")
                    writer.flush()
        finally:
            self.close()

    def close(self) -> None:
        engine, self._engine = self._engine, None
        if engine is not None:
            try:
                engine.stop()
            except Exception:  # noqa: BLE001 - shutdown is best effort
                pass

    @staticmethod
    def _result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

    def _initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        asked = params.get("protocolVersion")
        return {
            "protocolVersion": asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "testence", "version": __version__},
            "instructions": (
                "Explore with testence_snapshot, try steps with testence_click and "
                "testence_fill, write ordinary pytest with the `ex` fixture, run it with "
                "testence_run, read it with testence_inspect, and turn what the app sent "
                "into API checks with testence_oracle_suggest."
            ),
        }

    def _call(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        handlers: dict[str, Callable[[dict[str, Any]], Any]] = {
            "testence_doctor": self._doctor,
            "testence_snapshot": self._snapshot,
            "testence_click": self._click,
            "testence_fill": self._fill,
            "testence_run": self._run,
            "testence_inspect": self._inspect,
            "testence_oracle_suggest": self._oracle_suggest,
        }
        handler = handlers.get(str(name))
        if handler is None:
            raise ToolError(f"unknown tool {name!r}; known: {', '.join(sorted(handlers))}")
        if not isinstance(arguments, dict):
            raise ToolError("tool arguments must be an object")
        try:
            payload = handler(arguments)
        except ToolError:
            raise
        except Exception as exc:  # noqa: BLE001 - the agent reads the reason
            first = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
            raise ToolError(f"{type(exc).__name__}: {first}") from exc
        return self._tool_result(json.dumps(payload, ensure_ascii=False, indent=1))

    @staticmethod
    def _tool_result(text: str, *, error: bool = False) -> dict[str, Any]:
        return {"content": [{"type": "text", "text": text}], "isError": error}

    # -- tools ------------------------------------------------------------------------

    def _load_settings(self) -> Any:
        if self._settings is None:
            from testence.config import Settings

            settings = Settings.load(self.project)
            settings.headed = self.headed
            self._settings = settings
        return self._settings

    def _clean(self, text: str, limit: int = _TEXT_LIMIT) -> str:
        """Page text as the agent may see it: the project's redaction, bounded."""
        from testence.evidence.sanitize import sanitize_text

        settings = self._load_settings()
        return sanitize_text(
            text,
            secrets=settings.redaction_values(),
            policy=settings.redaction_policy(),
            limit=limit,
        )

    def _session(self) -> Any:
        """The exploration browser: started and signed in on first use."""
        if self._engine is not None:
            return self._engine
        from testence.auth import from_settings
        from testence.engine import create_engine

        settings = self._load_settings()
        engine = (self._engine_factory or create_engine)(settings)
        engine.start()
        try:
            if str(settings.auth or "none").strip().lower() != "none":
                from_settings(settings).authenticate(engine)
        except BaseException:
            engine.stop()
            raise
        self._engine = engine
        return engine

    @staticmethod
    def _target(raw: Any) -> Any:
        from testence.engine import Target
        from testence.engine.protocol import TARGET_KINDS

        if not isinstance(raw, dict):
            raise ToolError("target must be an object with kind and value")
        if raw.get("kind") not in TARGET_KINDS:
            raise ToolError(f"target.kind must be one of: {', '.join(TARGET_KINDS)}")
        if not isinstance(raw.get("value"), str) or not raw["value"]:
            raise ToolError("target.value must be a non-empty string")
        nth = raw.get("nth")
        return Target(
            raw["kind"],
            raw["value"],
            name=raw.get("name") or None,
            nth=nth if isinstance(nth, int) else None,
        )

    def _doctor(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from testence.application import doctor

        return doctor(self.project, target=bool(arguments.get("target")))

    def _snapshot(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from testence.engine import Target

        engine = self._session()
        url = arguments.get("url")
        if url:
            engine.goto(str(url))
        engine.settle(1_500)
        limit = min(int(arguments.get("limit") or 60), _MAX_ELEMENTS)
        elements: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for candidate in engine.candidate_elements():
            target = candidate["target"]
            key = (target["kind"], target["value"], target.get("name") or "")
            if key in seen:
                continue
            seen.add(key)
            spec = {k: target[k] for k in ("kind", "value", "name") if target.get(k)}
            count = engine.count(Target(spec["kind"], spec["value"], name=spec.get("name")))
            elements.append(
                {
                    "target": spec,
                    "python": _python(spec),
                    "matches": count,
                    "unique": count == 1,
                }
            )
            if len(elements) >= limit:
                break
        for element in elements:
            for field in ("value", "name"):
                if field in element["target"]:
                    element["target"][field] = self._clean(str(element["target"][field]), 300)
            element["python"] = _python(element["target"])
        return {
            "url": engine.current_url(),
            "aria": self._clean(engine.aria_snapshot()),
            "elements": elements,
        }

    def _click(self, arguments: dict[str, Any]) -> dict[str, Any]:
        target = self._target(arguments.get("target"))
        engine = self._session()
        engine.click(target)
        engine.settle(1_500)
        return {"clicked": target.describe(), "url": engine.current_url()}

    def _fill(self, arguments: dict[str, Any]) -> dict[str, Any]:
        value = arguments.get("value")
        if not isinstance(value, str):
            raise ToolError("value must be a string")
        target = self._target(arguments.get("target"))
        engine = self._session()
        engine.fill(target, value)
        return {"filled": target.describe(), "characters": len(value)}

    def _run_dir(self, raw: Any) -> Path:
        if not isinstance(raw, str) or not raw:
            raise ToolError("run_dir must be a path such as runs/r-123")
        path = (self.project / raw).resolve() if not Path(raw).is_absolute() else Path(raw)
        try:
            path.relative_to(self.project)
        except ValueError as exc:
            raise ToolError("run_dir must be inside the project") from exc
        return path

    def _run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from testence.application import inspect_run
        from testence.evidence import new_run_id

        args = arguments.get("pytest_args") or []
        if not isinstance(args, list) or not all(isinstance(item, str) for item in args):
            raise ToolError("pytest_args must be a list of strings")
        timeout = min(int(arguments.get("timeout_s") or 300), _RUN_TIMEOUT_S)
        run_id = new_run_id()
        command = [
            sys.executable,
            "-m",
            "testence.cli",
            "run",
            "--project",
            str(self.project),
            "--run-id",
            run_id,
            "--",
            *args,
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=self.project,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ToolError(f"the run did not finish within {timeout} s") from exc
        run_dir = self.project / "runs" / run_id
        summary: Any = None
        if run_dir.is_dir():
            try:
                summary = inspect_run(run_dir)
            except Exception as exc:  # noqa: BLE001 - reported next to the output
                summary = {"error": f"{type(exc).__name__}: {exc}"}
        return {
            "exit_code": completed.returncode,
            "run_dir": f"runs/{run_id}" if run_dir.is_dir() else None,
            "summary": summary,
            "output_tail": self._clean(completed.stdout[-4_000:] + completed.stderr[-2_000:]),
        }

    def _inspect(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from testence.application import ApplicationError, inspect_run

        try:
            return inspect_run(self._run_dir(arguments.get("run_dir")))
        except ApplicationError as exc:
            raise ToolError(str(exc)) from exc

    def _oracle_suggest(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from testence.oracle_suggest import suggest_run

        try:
            return suggest_run(self._run_dir(arguments.get("run_dir")))
        except (OSError, ValueError) as exc:
            raise ToolError(str(exc)) from exc


def main(project: Path | str = ".", *, headed: bool = False) -> int:
    server = McpServer(project, headed=headed)
    for stream in (sys.stdin, sys.stdout):
        # The protocol is UTF-8 whatever the console's code page is.
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    stream_in = sys.stdin
    stream_out = sys.stdout
    # Anything a library prints must not corrupt the protocol channel.
    sys.stdout = sys.stderr
    try:
        server.serve(stream_in, stream_out)
    finally:
        sys.stdout = stream_out
    return 0
