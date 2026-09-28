"""``ex`` runs in a logged-in browser (product review 2026-09-28, P0-2).

``auth.md`` says the browser is authenticated first, but ``ex`` depended only on the
engine: a test that asked for ``ex`` alone ran anonymous, landed on a blank page and
failed on its first target. Only tests that also requested ``testence_api`` logged in.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from testence.evidence import RUN_ID_ENV
from tests.mock_app import PASSWORD, USER, MockApp

ROOT = Path(__file__).parents[1]

SUITE = f"""
import pytest

from testence.engine import Target

WHOAMI = Target("css", "#whoami")


def test_ex_alone_is_signed_in(ex):
    ex.goto("/app")
    ex.expect_text(WHOAMI, "signed in as {USER}")


@pytest.mark.testence(anonymous=True)
def test_an_anonymous_test_is_not(ex):
    ex.goto("/app")
    ex.expect_text(WHOAMI, "not signed in")
"""


def test_ex_logs_in_unless_the_test_is_anonymous(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "test_app.py").write_text(SUITE.lstrip(), encoding="utf-8")
    with MockApp() as app:
        env = os.environ.copy()
        env.pop(RUN_ID_ENV, None)
        env.update(
            PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
            PYTHONPATH=str(ROOT / "src"),
            TESTENCE_BASE_URL=app.base_url,
            TESTENCE_AUTH="form",
            TESTENCE_USER=USER,
            TESTENCE_PASSWORD=PASSWORD,
        )
        result = subprocess.run(
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
    assert result.returncode == 0, result.stdout + result.stderr
    assert "2 passed" in result.stdout
