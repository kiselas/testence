"""Every call of a test's API client is evidence (PROD-11, slice 1).

The client seeds data and reads the API for oracles. When a seed fails, the test fails
before the behaviour under test, and the only useful question is what was sent and what
came back. Each call is an ``api.request`` event: in the ledger, in the failure pack's
history and as an Allure step with request and response attachments. Headers are never
recorded; bodies are redacted before they are clipped.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
import urllib.error
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

import pytest

from testence.actors import Actor
from testence.api import BODY_LIMIT, ApiClient, evidence_recorder, polling
from testence.auth.base import AuthContext
from testence.config import Settings
from testence.contracts import validate_document
from testence.evidence import RUN_ID_ENV, EvidenceWriter
from testence.export import allure
from testence.export._model import LoadedRun, Step
from testence.export.junit import _leaves
from testence.loopback import LoopbackHTTPServer
from testence.triage import assemble_pack
from tests.mock_app import PASSWORD, USER, MockApp
from tests.owned_pytest import run_pytest

ROOT = Path(__file__).parents[1]
BEARER = "Bearer bearer-secret-0123456789"
HUGE = [{"n": index, "label": "x" * 40} for index in range(400)]


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args: Any) -> None:
        pass

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, doc: Any) -> None:
        self._send(status, json.dumps(doc).encode(), "application/json")

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/items/"):
            self._json(200, {"id": self.path.rsplit("/", 1)[-1], "name": "seeded"})
        elif self.path == "/session":
            self._json(200, {"user": "u", "access_token": "issued-token-0123456789"})
        elif self.path == "/huge":
            self._json(200, {"items": HUGE, "api_key": "late-key-0123456789"})
        elif self.path == "/export.zip":
            self._send(200, b"PK\x03\x04" + bytes(range(256)), "application/zip")
        elif self.path == "/slow":
            time.sleep(1.0)
            self._json(200, {})
        else:
            self._send(500, b"upstream exploded", "text/plain")

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        self._json(422, {"detail": "name is required"})


@pytest.fixture
def server() -> Iterator[str]:
    httpd = LoopbackHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def _events(writer: EvidenceWriter, kind: str = "api.request") -> list[dict[str, Any]]:
    lines = writer.path.read_text(encoding="utf-8").splitlines()
    return [doc for doc in map(json.loads, lines) if doc["kind"] == kind]


def _client(server: str, writer: EvidenceWriter, **kw: Any) -> ApiClient:
    auth = AuthContext()
    auth.headers["Authorization"] = BEARER
    return ApiClient(server, auth, recorder=evidence_recorder(writer, "test_seed"), **kw)


def test_each_call_is_an_api_request_event(tmp_path, server):
    writer = EvidenceWriter(tmp_path, worker="")
    client = _client(server, writer)
    assert client.get("/items/42").status == 200
    assert client.post("/items", {"name": ""}).status == 422

    read, seed = _events(writer)
    assert (read["method"], read["status"]) == ("GET", 200)
    assert read["url"] == f"{server}/items/42"
    assert read["request"] == {"body": None}
    assert read["response"]["body"] == {"id": "42", "name": "seeded"}
    assert read["response"]["content_type"] == "application/json"
    assert read["duration_ms"] >= 0 and read["test"] == "test_seed"
    assert (seed["method"], seed["status"]) == ("POST", 422)
    assert seed["request"]["body"] == {"name": ""}
    assert seed["response"]["body"] == {"detail": "name is required"}
    for event in (read, seed):
        validate_document(event, "evidence.schema.json")


def test_a_server_error_keeps_its_text_body(tmp_path, server):
    writer = EvidenceWriter(tmp_path, worker="")
    assert _client(server, writer).get("/boom").status == 500
    (event,) = _events(writer)
    assert event["status"] == 500
    assert event["response"]["body"] == "upstream exploded"


@pytest.mark.parametrize("target", ["refused", "timeout"])
def test_a_call_without_an_answer_is_recorded_and_still_raises(tmp_path, server, target):
    writer = EvidenceWriter(tmp_path, worker="")
    if target == "refused":
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            closed = f"http://127.0.0.1:{probe.getsockname()[1]}"
        client = _client(closed, writer)
        path = "/items/1"
    else:
        client = _client(server, writer, timeout_s=0.2)
        path = "/slow"
    with pytest.raises((urllib.error.URLError, TimeoutError, OSError)):
        client.get(path)
    (event,) = _events(writer)
    assert "status" not in event and "response" not in event
    assert event["error"].split(":", 1)[0] in {"URLError", "TimeoutError", "timeout"}
    validate_document(event, "evidence.schema.json")


def test_headers_and_secrets_never_reach_the_ledger(tmp_path, server):
    writer = EvidenceWriter(tmp_path, worker="")
    client = _client(server, writer)
    client.post("/users", {"name": "n", "password": "hunter2-password-value"})
    client.get("/session")
    raw = writer.path.read_text(encoding="utf-8")
    for secret in ("bearer-secret-0123456789", "hunter2-password-value", "issued-token-0123456789"):
        assert secret not in raw
    assert "Authorization" not in raw
    seed, session = _events(writer)
    assert seed["request"]["body"]["name"] == "n"
    assert session["response"]["body"]["user"] == "u"


def test_bodies_are_redacted_before_they_are_clipped(tmp_path, server):
    writer = EvidenceWriter(tmp_path, worker="")
    _client(server, writer).get("/huge")
    (event,) = _events(writer)
    body = event["response"]["body"]
    assert isinstance(body, str) and "<truncated:" in body
    assert len(body) <= BODY_LIMIT + 40
    assert "late-key-0123456789" not in writer.path.read_text(encoding="utf-8")


def test_a_binary_answer_is_described_not_recorded(tmp_path, server):
    writer = EvidenceWriter(tmp_path, worker="")
    _client(server, writer).get("/export.zip")
    (event,) = _events(writer)
    assert event["response"]["body"] is None
    assert event["response"]["omitted"] == "binary"
    assert event["response"]["bytes"] > 0
    validate_document(event, "evidence.schema.json")


def test_a_client_outside_a_test_records_nothing(server):
    client = ApiClient(server)
    assert client.recorder is None
    assert client.get("/items/1").status == 200


def test_an_actor_api_records_with_its_role(tmp_path, server):
    writer = EvidenceWriter(tmp_path, worker="")
    settings = Settings.load(tmp_path, auth="form")
    settings.base_url = server
    actor = Actor(
        "viewer",
        settings,
        AuthContext(),
        None,
        open_browser=lambda: pytest.fail("no browser expected"),
        make_actions=lambda _e: pytest.fail("no actions expected"),
        api_recorder=evidence_recorder(writer, "test_seed", role="viewer"),
    )
    actor.api.get("/items/7")
    (event,) = _events(writer)
    assert event["role"] == "viewer"


class _PagelessEngine:
    def settle(self, timeout_ms: int = 1_500) -> bool:
        return True

    def aria_snapshot(self) -> str:
        return ""

    def network_log(self) -> list[Any]:
        return []

    def console_log(self) -> list[dict[str, Any]]:
        return []

    def screenshot(self, path: str) -> None:
        open(path, "wb").close()

    def browser_manifest(self) -> dict[str, Any]:
        return {}


def test_the_failure_pack_history_carries_the_calls(tmp_path, server):
    writer = EvidenceWriter(tmp_path, worker="")
    _client(server, writer).post("/items", {"name": ""})
    pack = assemble_pack(_PagelessEngine(), writer, "test_seed", error="seed failed")
    history = json.loads((pack / "events.json").read_text(encoding="utf-8"))
    validate_document(history, "pack-events.schema.json")
    (record,) = [item["event"] for item in history["events"]]
    assert record["kind"] == "api.request"
    assert (record["method"], record["status"]) == ("POST", 422)
    assert record["response"]["body"] == {"detail": "name is required"}
    assert "api.request" in (pack / "TRIAGE.md").read_text(encoding="utf-8")


def test_seed_bodies_cannot_push_the_failing_step_out_of_the_pack(tmp_path):
    writer = EvidenceWriter(tmp_path, worker="")
    record = evidence_recorder(writer, "test_seed")
    writer.emit("step.start", test="test_seed", step="s0", intent="open the page")
    writer.emit("step.end", test="test_seed", step="s0", status="ok", duration_ms=1)
    for index in range(10):
        record(
            method="POST",
            url=f"http://app/api/items/{index}",
            duration_ms=3.0,
            request={"body": {"name": "x" * 1_500}},
            status=201,
            response={"content_type": "application/json", "bytes": 1_500, "body": "y" * 1_500},
        )
    writer.emit("step.start", test="test_seed", step="s1", intent="click Save")
    writer.emit("step.end", test="test_seed", step="s1", status="failed", duration_ms=1)
    pack = assemble_pack(_PagelessEngine(), writer, "test_seed", error="failed")
    history = json.loads((pack / "events.json").read_text(encoding="utf-8"))
    assert history["status"] == "complete" and len(history["events"]) == 14
    call = history["events"][2]["event"]
    assert call["response"]["body"].endswith("<truncated:1200 chars>")
    full = [doc for doc in _events(writer)][0]
    assert full["response"]["body"] == "y" * 1_500


@pytest.mark.parametrize("calls", [1, 2, 6])
def test_a_polling_loop_records_its_first_and_last_call(tmp_path, server, calls):
    writer = EvidenceWriter(tmp_path, worker="")
    client = _client(server, writer)
    with polling():
        for _ in range(calls):
            client.get("/items/9")
    events = _events(writer)
    assert len(events) == min(calls, 2)
    assert "attempts" not in events[0]
    if calls > 1:
        assert events[-1]["attempts"] == calls
        validate_document(events[-1], "evidence.schema.json")


def test_an_oracle_that_polls_does_not_flood_the_evidence(tmp_path, server):
    from testence.oracle import ExpectedState, observe_expected_state

    writer = EvidenceWriter(tmp_path, worker="")
    client = _client(server, writer)
    observation = observe_expected_state(
        lambda: client.get_fresh("/items/9"),
        ExpectedState.fields("renamed", {"name": "never"}),
        deadline_ms=400,
        poll_ms=20,
    )
    assert observation.outcome == "failed" and observation.attempts > 2
    first, last = _events(writer)
    assert "attempts" not in first and last["attempts"] == observation.attempts
    exported = LoadedRun.from_events(
        [json.loads(line) for line in writer.path.read_text(encoding="utf-8").splitlines()],
        tmp_path,
    )
    names = [step.intent for step in exported.tests[0].steps]
    assert names[-1] == f"GET /items/9 → 200 (last of {observation.attempts} reads)"


def _exported(tmp_path: Path, server: str, attachments: str = "full") -> dict[str, Any]:
    writer = EvidenceWriter(tmp_path / "run", worker="")
    client = _client(server, writer)
    writer.emit("test.start", test="test_seed", display_name="test_seed")
    writer.emit("step.start", test="test_seed", step="s1", intent="create the widget")
    client.post("/items", {"name": ""})
    writer.emit("step.end", test="test_seed", step="s1", status="ok", duration_ms=5)
    client.get("/items/42")
    writer.emit("test.end", test="test_seed", status="failed", error="seed failed")
    events = [json.loads(line) for line in writer.path.read_text(encoding="utf-8").splitlines()]
    run = LoadedRun.from_events(events, tmp_path / "run")
    run.attachments = attachments
    out = tmp_path / f"allure-{attachments}"
    out.mkdir()
    allure.write_test(run, run.tests[0], out)
    (result,) = out.glob("*-result.json")
    return {"out": out, "result": json.loads(result.read_text(encoding="utf-8"))}


def test_allure_shows_each_call_as_a_step_with_request_and_response(tmp_path, server):
    exported = _exported(tmp_path, server)
    action, read = exported["result"]["steps"]
    (seed,) = action["steps"]
    assert action["name"] == "create the widget"
    assert seed["name"] == "POST /items → 422" and seed["status"] == "passed"
    assert read["name"] == "GET /items/42 → 200"
    assert {"name": "url", "value": f"{server}/items/42"} in read["parameters"]
    names = [item["name"] for item in seed["attachments"]]
    assert names == ["request.json", "response.json"]
    request, response = (
        json.loads((exported["out"] / item["source"]).read_text(encoding="utf-8"))
        for item in seed["attachments"]
    )
    assert request == {"body": {"name": ""}, "method": "POST", "url": f"{server}/items"}
    assert response["status"] == 422 and response["body"] == {"detail": "name is required"}
    assert "bearer-secret" not in json.dumps(exported["result"])


def test_allure_ships_no_call_files_when_attachments_are_off(tmp_path, server):
    exported = _exported(tmp_path, server, attachments="none")
    action, read = exported["result"]["steps"]
    assert "attachments" not in read and "attachments" not in action["steps"][0]
    assert not list(exported["out"].glob("*-attachment.json"))


def test_a_call_is_evidence_inside_a_step_not_a_step_of_the_case():
    seed = Step(step="api.request", intent="POST /items → 201", http={"method": "POST"})
    action = Step(step="s1", intent="create the widget", substeps=[seed])
    click = Step(step="s2", intent="open the list")
    assert _leaves([action, seed, click]) == [action, click]


SUITE = """
def test_a_failed_seed_shows_what_was_sent(testence_api):
    created = testence_api.post(
        "/api/v1/widgets", {"name": "seed", "cidr": "10.0.0.0/8", "password": "hunter2-seed"}
    )
    assert created.status == 201
    lookup = testence_api.get("/api/v1/no-such-thing")
    assert lookup.status == 200, "seed lookup failed"
"""


def test_a_real_run_records_the_calls_in_ledger_pack_and_live_allure(tmp_path):
    project = tmp_path / "seed"
    project.mkdir()
    (project / "test_seed.py").write_text(SUITE.lstrip(), encoding="utf-8")
    (project / "testence.json").write_text(
        json.dumps({"auth": "form", "login_path": "/login", "success_url_contains": "/app"}),
        encoding="utf-8",
    )
    results = project / "allure-results"
    with MockApp() as app:
        env = os.environ.copy()
        env.pop(RUN_ID_ENV, None)
        env.update(
            PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
            PYTHONPATH=str(ROOT / "src"),
            TESTENCE_BASE_URL=app.base_url,
            TESTENCE_USER=USER,
            TESTENCE_PASSWORD=PASSWORD,
            TESTENCE_ALLURE_RESULTS=str(results),
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
                "-p",
                "no:cacheprovider",
                "--testence-headless",
                "-q",
            ],
            cwd=project,
            env=env,
            timeout=300,
        )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "1 failed" in result.stdout

    run_dir = next((project / "runs").glob("*/run.jsonl")).parent
    ledger = "".join(path.read_text(encoding="utf-8") for path in run_dir.glob("run*.jsonl"))
    calls = [doc for doc in map(json.loads, ledger.splitlines()) if doc["kind"] == "api.request"]
    assert [(call["method"], call["status"]) for call in calls] == [("POST", 201), ("GET", 404)]
    assert all(call["test"].endswith("test_a_failed_seed_shows_what_was_sent") for call in calls)
    assert calls[0]["response"]["body"]["name"] == "seed"
    assert "hunter2-seed" not in ledger and "session_id=" not in ledger

    (pack,) = [path.parent for path in run_dir.rglob("events.json")]
    history = json.loads((pack / "events.json").read_text(encoding="utf-8"))
    kinds = [item["event"]["kind"] for item in history["events"]]
    assert kinds.count("api.request") == 2

    (allure_result,) = [
        json.loads(path.read_text(encoding="utf-8")) for path in results.glob("*-result.json")
    ]
    names = [step["name"] for step in allure_result["steps"]]
    assert "POST /api/v1/widgets → 201" in names and "GET /api/v1/no-such-thing → 404" in names
    files = [
        item["source"]
        for step in allure_result["steps"]
        if step["name"].startswith(("POST", "GET"))
        for item in step["attachments"]
    ]
    assert len(files) == 4 and all((results / name).is_file() for name in files)
    assert all("hunter2-seed" not in (results / name).read_text(encoding="utf-8") for name in files)
