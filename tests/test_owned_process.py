"""Real process-tree controls, including inherited output and detached parents."""

import json
import os
import socket
import subprocess
import sys
import time

import pytest

from testence._process import run_owned

TREE = """
import json, os, socket, subprocess, sys, time
from pathlib import Path
depth = int(sys.argv[1])
if depth:
    subprocess.Popen([sys.executable, __file__, str(depth - 1), sys.argv[2]])
listener = socket.socket()
listener.bind(('127.0.0.1', 0))
listener.listen()
Path(f'port-{depth}.json').write_text(json.dumps([listener.getsockname()[1], os.getpid()]))
if depth == 2:
    deadline = time.monotonic() + 10
    while not all(Path(f'port-{i}.json').exists() for i in range(3)):
        assert time.monotonic() < deadline
        time.sleep(.01)
    print('three processes ready', flush=True)
    if sys.argv[2] == 'exit':
        sys.exit(7)
time.sleep(600)
"""


def assert_listener_stopped(port):
    deadline = time.monotonic() + 5
    while True:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                pass
        except OSError:
            return
        assert time.monotonic() < deadline, f"owned descendant still listening on {port}"
        time.sleep(0.01)


@pytest.mark.parametrize("mode", ["timeout", "exit"])
def test_owned_tree_ends_without_killing_an_unrelated_process(tmp_path, mode):
    script = tmp_path / "tree.py"
    script.write_text(TREE, encoding="utf-8")
    unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
    try:
        started = time.monotonic()
        result = run_owned([sys.executable, str(script), "2", mode], cwd=tmp_path, timeout=3)
        elapsed = time.monotonic() - started
        assert result.timed_out == (mode == "timeout")
        assert result.returncode == (None if mode == "timeout" else 7)
        assert "three processes ready" in result.stdout
        assert elapsed < 8, f"deadline/output cleanup stalled: {elapsed:.3f}s"
        for depth in range(3):
            port, _pid = json.loads((tmp_path / f"port-{depth}.json").read_text())
            assert_listener_stopped(port)
        assert unrelated.poll() is None
    finally:
        unrelated.kill()
        unrelated.wait(timeout=10)


def test_output_tails_are_bounded_and_keep_both_channels(tmp_path):
    result = run_owned(
        [sys.executable, "-c", "import sys; print('x'*100000+'END'); print('ERR',file=sys.stderr)"],
        cwd=tmp_path,
        timeout=10,
    )
    assert result.returncode == 0 and not result.timed_out
    assert len(result.stdout) == 4000 and result.stdout.rstrip().endswith("END")
    assert result.stderr.rstrip() == "ERR"


@pytest.mark.skipif(os.name != "nt", reason="Windows job assignment boundary")
def test_failed_assignment_cannot_start_project_code(tmp_path, monkeypatch):
    def fail(*args):
        raise OSError("synthetic assignment denied")

    monkeypatch.setattr("testence._process._WindowsJob.assign", fail)
    with pytest.raises(OSError, match="synthetic assignment denied"):
        run_owned(
            [sys.executable, "-c", "from pathlib import Path; Path('unsafe').write_text('ran')"],
            cwd=tmp_path,
            timeout=10,
        )
    assert not (tmp_path / "unsafe").exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows venv redirector ownership")
def test_gate_assignment_tolerates_a_launcher_spawning_the_interpreter_first(tmp_path, monkeypatch):
    from testence._process import _WindowsJob

    assigned = []
    original = _WindowsJob.assign

    def assign(job, pid):
        time.sleep(0.2)  # Let the venv redirector spawn its actual interpreter.
        original(job, pid)
        assigned.append(pid)

    monkeypatch.setattr(_WindowsJob, "assign", assign)
    (tmp_path / "tree.py").write_text(TREE, encoding="utf-8")
    result = run_owned([sys.executable, "tree.py", "2", "exit"], cwd=tmp_path, timeout=5)
    assert result.returncode == 7 and assigned
    for depth in range(3):
        port, _pid = json.loads((tmp_path / f"port-{depth}.json").read_text())
        assert_listener_stopped(port)
