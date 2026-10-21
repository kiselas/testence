"""Real Windows gate reads must fail closed before any project code is released."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from testence import _process

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows ready/assignment handshake")
COMMAND = [sys.executable, "-c", "from pathlib import Path; Path('ran').write_text('once')"]


@pytest.mark.parametrize("error", [PermissionError, FileNotFoundError])
def test_transient_ready_read_preserves_assignment_before_release(tmp_path, monkeypatch, error):
    original_read = Path.read_text
    original_assign = _process._WindowsJob.assign
    injected = False
    validated = False
    assigned = []

    def read(path, *args, **kwargs):
        nonlocal injected, validated
        contents = original_read(path, *args, **kwargs)
        if path.name == "ready":
            if not injected:
                injected = True
                raise error("synthetic transient ready read")
            validated = True
        return contents

    def assign(job, pid):
        original_assign(job, pid)
        assigned.append(pid)
        assert validated and not (tmp_path / "ran").exists()

    monkeypatch.setattr(Path, "read_text", read)
    monkeypatch.setattr(_process._WindowsJob, "assign", assign)
    result = _process.run_owned(COMMAND, cwd=tmp_path, timeout=5)
    assert injected and assigned
    assert result.returncode == 0 and not result.timed_out
    assert (tmp_path / "ran").read_text() == "once"


def test_permanent_ready_denial_uses_original_deadline_without_release(tmp_path, monkeypatch):
    original = Path.read_text
    original_assign = _process._WindowsJob.assign
    assigned = []
    reads = []

    def read(path, *args, **kwargs):
        if path.name == "ready":
            reads.append(time.monotonic())
            raise PermissionError("synthetic permanent ready denial")
        return original(path, *args, **kwargs)

    def assign(job, pid):
        original_assign(job, pid)
        assigned.append(pid)

    monkeypatch.setattr(Path, "read_text", read)
    monkeypatch.setattr(_process._WindowsJob, "assign", assign)
    started = time.monotonic()
    result = _process.run_owned(COMMAND, cwd=tmp_path, timeout=1)
    assert result.timed_out and result.returncode is None
    assert reads and not assigned and not (tmp_path / "ran").exists()
    assert time.monotonic() - started < 4


@pytest.mark.parametrize("value", ["", "not-a-pid"])
def test_invalid_ready_pid_never_assigns_or_releases(tmp_path, monkeypatch, value):
    original = Path.read_text
    original_assign = _process._WindowsJob.assign
    assigned = []
    injected = False

    def read(path, *args, **kwargs):
        nonlocal injected
        contents = original(path, *args, **kwargs)
        if path.name == "ready":
            injected = True
            return value
        return contents

    def assign(job, pid):
        original_assign(job, pid)
        assigned.append(pid)

    monkeypatch.setattr(Path, "read_text", read)
    monkeypatch.setattr(_process._WindowsJob, "assign", assign)
    with pytest.raises(ValueError):
        _process.run_owned(COMMAND, cwd=tmp_path, timeout=5)
    assert injected and not assigned and not (tmp_path / "ran").exists()


def test_gate_exit_before_ready_cannot_release_project_code(tmp_path, monkeypatch):
    gate = tmp_path / "early_gate.py"
    gate.write_text("raise SystemExit(7)\n", encoding="utf-8")
    original = subprocess.Popen
    original_assign = _process._WindowsJob.assign
    assigned = []

    def popen(command, **kwargs):
        assert str(command[3]).endswith("_process_gate.py")
        return original([*command[:3], str(gate), *command[4:]], **kwargs)

    def assign(job, pid):
        original_assign(job, pid)
        assigned.append(pid)

    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr(_process._WindowsJob, "assign", assign)
    with pytest.raises(OSError, match="gate exited before readiness"):
        _process.run_owned(COMMAND, cwd=tmp_path, timeout=5)
    assert not assigned and not (tmp_path / "ran").exists()
