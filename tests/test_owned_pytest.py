"""Exercise nested pytest with a descendant that inherits its output handles."""

import json
import os
import subprocess
import sys
import time

import pytest

from tests.owned_pytest import run_pytest
from tests.test_owned_process import assert_listener_stopped


@pytest.mark.parametrize("hang", [False, True])
def test_nested_pytest_releases_descendants_and_keeps_diagnostics(tmp_path, hang):
    (tmp_path / "child.py").write_text(
        "import json, socket, time\n"
        "from pathlib import Path\n"
        "listener = socket.socket()\n"
        "listener.bind(('127.0.0.1', 0))\n"
        "listener.listen()\n"
        "Path('port.json').write_text(json.dumps(listener.getsockname()[1]))\n"
        "time.sleep(600)\n",
        encoding="utf-8",
    )
    (tmp_path / "test_child.py").write_text(
        "import os, subprocess, sys, time\n"
        "from pathlib import Path\n"
        "def test_child():\n"
        "    assert os.environ['TESTENCE_SYNTHETIC_VALUE'] == 'inherited'\n"
        "    subprocess.Popen([sys.executable, 'child.py'])\n"
        "    deadline = time.monotonic() + 10\n"
        "    while not Path('port.json').exists():\n"
        "        assert time.monotonic() < deadline\n"
        "        time.sleep(.01)\n"
        "    print('nested stdout ready', flush=True)\n"
        "    print('nested stderr ready', file=sys.stderr, flush=True)\n"
        + ("    time.sleep(600)\n" if hang else ""),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update(PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", TESTENCE_SYNTHETIC_VALUE="inherited")
    env.pop("PYTEST_ADDOPTS", None)
    command = [sys.executable, "-m", "pytest", "test_child.py", "-s", "-q"]
    started = time.monotonic()
    if hang:
        with pytest.raises(subprocess.TimeoutExpired) as failure:
            run_pytest(command, cwd=tmp_path, env=env, timeout=5)
        assert "nested stdout ready" in failure.value.stdout
        assert "nested stderr ready" in failure.value.stderr
        assert failure.value.cmd == command and failure.value.timeout == 5
    else:
        result = run_pytest(command, cwd=tmp_path, env=env, timeout=15)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "1 passed" in result.stdout
    assert time.monotonic() - started < 20
    assert_listener_stopped(json.loads((tmp_path / "port.json").read_text()))
