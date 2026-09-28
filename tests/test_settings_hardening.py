"""Settings, readiness, seed namespaces and the session cache (audit cycle 2, A2-01..05)."""

from __future__ import annotations

import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler

import pytest

from testence import isolation
from testence.config import Settings, _parse_env_file
from testence.loopback import LoopbackHTTPServer
from testence.readiness import _run_check


def test_a_profile_keeps_the_base_redaction_rules_it_does_not_restate(tmp_path, monkeypatch):
    monkeypatch.setenv("THIRD_PARTY_API_KEY", "super-secret-value")
    (tmp_path / "testence.json").write_text(
        json.dumps(
            {
                "extra": {"evidence": {"redact": {"env": ["THIRD_PARTY_API_KEY"]}}, "a": 1},
                "profiles": {"staging": {"extra": {"session_probe_path": "/api/me", "a": 2}}},
            }
        ),
        encoding="utf-8",
    )

    staging = Settings.load(tmp_path, profile="staging")

    assert "super-secret-value" in staging.redaction_values()
    assert staging.extra["session_probe_path"] == "/api/me"
    assert staging.extra["a"] == 2


@pytest.mark.parametrize(
    ("line", "value"),
    [
        ("TESTENCE_PASSWORD=s3cr3t  # rotate before prod", "s3cr3t"),
        ("TESTENCE_PASSWORD=s3cr3t\t# tab before the comment", "s3cr3t"),
        ("TESTENCE_PASSWORD=a#b", "a#b"),
        ('TESTENCE_PASSWORD="with # inside"  # comment', "with # inside"),
        ("TESTENCE_PASSWORD='single # quoted'", "single # quoted"),
        ('TESTENCE_PASSWORD="=equals=in=value"', "=equals=in=value"),
        ("export TESTENCE_PASSWORD=plain", "plain"),
        ("TESTENCE_PASSWORD=", ""),
    ],
)
def test_dotenv_values_end_at_a_comment_outside_quotes(tmp_path, line, value):
    env = tmp_path / ".env"
    env.write_text(line + "\n", encoding="utf-8")

    assert _parse_env_file(env) == {"TESTENCE_PASSWORD": value}


@pytest.fixture
def two_origins():
    class Other(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - http.server API
            body = b'{"ready": true}'
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    other = LoopbackHTTPServer(("127.0.0.1", 0), Other)
    target_url = f"http://127.0.0.1:{other.server_port}/ready"

    class Redirecting(Other):
        def do_GET(self):  # noqa: N802 - http.server API
            self.send_response(302)
            self.send_header("location", target_url)
            self.end_headers()

    origin = LoopbackHTTPServer(("127.0.0.1", 0), Redirecting)
    servers = (origin, other)
    for server in servers:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{origin.server_port}"
    for server in servers:
        server.shutdown()


def test_a_readiness_check_is_not_answered_by_another_origin(tmp_path, two_origins):
    settings = Settings(base_url=two_origins)
    check = {
        "id": "seed",
        "type": "http",
        "path": "/start",
        "json_pointer": "/ready",
        "equals": True,
    }

    ok, detail = _run_check(check, project=tmp_path, settings=settings)

    assert not ok
    assert "redirected to another origin" in detail


def test_a_rerun_gets_its_own_seed_marker():
    first = isolation.TestNamespace("p", "r", "controller", "case", "admin", "attempt-controller-1")
    repeat = isolation.TestNamespace(
        "p", "r", "controller", "case", "admin", "attempt-controller-2"
    )

    assert first.marker != repeat.marker


@pytest.mark.skipif(os.name != "nt", reason="Windows ACLs")
def test_the_windows_session_cache_is_readable_by_its_owner_only(tmp_path, monkeypatch):
    from tests.test_auth import (
        _cached_auth,
        _CookieEngine,
        _CountingSessionAuth,
        _identity_response,
    )

    monkeypatch.setattr("testence.api.http_json", lambda *_args, **_kwargs: _identity_response())
    auth = _cached_auth(tmp_path, _CountingSessionAuth())

    auth.authenticate(_CookieEngine())

    cache = tmp_path / "session.json"
    listing = subprocess.run(
        ["icacls", str(cache)], capture_output=True, text=True, errors="replace"
    )
    grants = [line for line in listing.stdout.splitlines()[:-1] if ":(" in line]
    assert len(grants) == 1, listing.stdout
    assert os.environ.get("USERNAME", "").lower() in grants[0].lower()


@pytest.mark.parametrize("spelling", ["http://127.0.0.1:{port}", "http://127.0.0.1.:{port}"])
def test_a_redirect_that_respells_the_same_origin_is_accepted(spelling):
    from testence.readiness import _origin

    base = "http://127.0.0.1:8080/ready"
    assert _origin(spelling.format(port=8080) + "/x") == _origin(base)
    assert _origin("http://example.test/x") == _origin("http://example.test:80/y")
    assert _origin("https://example.test/x") != _origin("http://example.test/x")


def test_metrics_call_a_test_flaky_only_when_it_passed_after_a_rerun(tmp_path):
    """A rerun is one test, and a test that never passed is not flaky however its
    attempts failed (broken, then failed)."""
    from testence.evidence import EvidenceWriter
    from testence.metrics import aggregate

    writer = EvidenceWriter(tmp_path, run_id="r-rerun-metrics", worker="", project_id="p")
    writer.emit("run.start")
    attempts = {
        "c": [("failed", {"rerun": True}), ("passed", {"retries": 1, "flaky": True})],
        "d": [("broken", {"rerun": True}), ("failed", {"retries": 1})],
    }
    for case, outcomes in attempts.items():
        for number, (status, extra) in enumerate(outcomes, 1):
            ids = {
                "project_id": "p",
                "case_id": case,
                "variant_id": "default",
                "attempt_id": f"attempt-controller-{number}",
            }
            node = f"t.py::{case}"
            writer.emit("test.start", test=node, nodeid=node, code="abc", **ids)
            writer.emit(
                "test.end", test=node, nodeid=node, status=status, duration_ms=1.0, **ids, **extra
            )
    writer.emit("run.end", run_status="failed", exit_code=1, duration_ms=5.0)
    writer.close()

    assert aggregate([writer.run_dir])["flaky_tests"] == ["p/c/default"]
