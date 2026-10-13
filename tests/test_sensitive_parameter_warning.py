"""The warning about secret test IDs must not repeat the secret itself."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "name,value,ids,expect_warning",
    [
        ("password", "SYNTH-CANARY-41", None, True),
        ("pin", 987321, None, True),
        ("password", "СИНТЕТИКА-'q'-41", None, True),
        ("password", "SYNTH-CANARY-41", ["safe-case"], False),
        ("city", "Lisbon", None, False),
    ],
)
def test_sensitive_parameter_warning_uses_safe_test_location(
    tmp_path, name, value, ids, expect_warning
):
    project = tmp_path / "project"
    project.mkdir()
    (project / "conftest.py").write_text(
        "import json\nfrom pathlib import Path\n"
        "def pytest_warning_recorded(warning_message, when, nodeid, location):\n"
        "    message = str(warning_message.message)\n"
        "    if 'puts its value into the test id' in message:\n"
        "        with Path('warnings.jsonl').open('a', encoding='utf-8') as output:\n"
        "            output.write(json.dumps(message) + '\\n')\n",
        encoding="utf-8",
    )
    (project / "test_example.py").write_text(
        "import pytest\n"
        f"@pytest.mark.parametrize({name!r}, [{value!r}], ids={ids!r})\n"
        f"def test_control({name}):\n    assert {name}\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["PYTHONPATH"] = str(ROOT / "src")
    env.pop("TESTENCE_RUN_ID", None)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "testence.pytest_plugin",
            "-q",
            "-p",
            "no:cacheprovider",
            "--testence-runs-root",
            str(tmp_path / "runs"),
        ],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    path = project / "warnings.jsonl"
    messages = (
        [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        if path.exists()
        else []
    )
    assert len(messages) == int(expect_warning)
    for message in messages:
        assert str(value) not in message
        assert "test_example.py::test_control" in message
        assert repr(name) in message
        assert "ids=..." in message
