"""A cached session makes every login after the first one cheap in a real run.

The probe of an ordinary application answers with who is signed in and nothing
about a role. Such a probe is enough to reuse the session, so the ``auth`` phase of
each test after the first is one probe request instead of a login.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from testence.evidence import RUN_ID_ENV
from tests.mock_app import PASSWORD, USER, MockApp
from tests.owned_pytest import run_pytest

ROOT = Path(__file__).parents[1]

SUITE = """
def test_first(ex):
    pass


def test_second(ex):
    pass


def test_third(ex):
    pass
"""


def test_auth_phase_after_the_first_test_is_a_cache_hit(tmp_path):
    project = tmp_path / "cache"
    project.mkdir()
    (project / "test_cache.py").write_text(SUITE.lstrip(), encoding="utf-8")
    (project / "testence.json").write_text(
        json.dumps(
            {
                "auth": "api-session",
                "session_probe_path": "/api/v1/auth/me",
                "session_identity_field": "email",
            }
        ),
        encoding="utf-8",
    )
    with MockApp() as app:
        env = os.environ.copy()
        env.pop(RUN_ID_ENV, None)
        env.update(
            PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
            PYTHONPATH=str(ROOT / "src"),
            TESTENCE_BASE_URL=app.base_url,
            TESTENCE_USER=USER,
            TESTENCE_PASSWORD=PASSWORD,
            TESTENCE_DEBUG_PORT="0",
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
                "-p",
                "no:randomly",
                "--testence-headless",
                "-q",
            ],
            cwd=project,
            env=env,
            timeout=300,
        )
    assert result.returncode == 0, result.stdout + result.stderr

    ledger = next((project / "runs").glob("*/run.jsonl")).read_text(encoding="utf-8")
    events = [json.loads(line) for line in ledger.splitlines()]
    schemes = [e["auth"]["scheme"] for e in events if e.get("text") == "authenticated"]
    assert schemes == ["api-session", "api-session+cached", "api-session+cached"]
    phases = [e for e in events if e.get("lifecycle_phase") == "auth" and "test" in e]
    assert len(phases) == 3
    later = [phase["duration_ms"] for phase in phases[1:]]
    assert all(duration <= 50 for duration in later), later
