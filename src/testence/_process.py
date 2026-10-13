"""Own a synchronous command and its descendants for its entire lifetime.

POSIX uses a new process group. Windows uses a non-inheritable kill-on-close
job and a gated launcher, assigned before it can start the requested command.
These are lifecycle controls for trusted project tests, not a security sandbox.
"""

from __future__ import annotations

import ctypes
import os
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class CommandResult:
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool


class _WindowsJob:
    def __init__(self) -> None:
        from ctypes import wintypes

        class BasicLimits(ctypes.Structure):
            _fields_ = [
                ("process_time", ctypes.c_int64),
                ("job_time", ctypes.c_int64),
                ("flags", wintypes.DWORD),
                ("min_working_set", ctypes.c_size_t),
                ("max_working_set", ctypes.c_size_t),
                ("active_process_limit", wintypes.DWORD),
                ("affinity", ctypes.c_size_t),
                ("priority", wintypes.DWORD),
                ("scheduling", wintypes.DWORD),
            ]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [
                ("basic", BasicLimits),
                ("io_counters", ctypes.c_uint64 * 6),
                ("process_memory", ctypes.c_size_t),
                ("job_memory", ctypes.c_size_t),
                ("peak_process_memory", ctypes.c_size_t),
                ("peak_job_memory", ctypes.c_size_t),
            ]

        self.api = getattr(ctypes, "WinDLL")("kernel32", use_last_error=True)
        for name, restype, argtypes in (
            ("CreateJobObjectW", wintypes.HANDLE, [ctypes.c_void_p, wintypes.LPCWSTR]),
            (
                "SetInformationJobObject",
                wintypes.BOOL,
                [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD],
            ),
            ("OpenProcess", wintypes.HANDLE, [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]),
            ("AssignProcessToJobObject", wintypes.BOOL, [wintypes.HANDLE, wintypes.HANDLE]),
            ("CloseHandle", wintypes.BOOL, [wintypes.HANDLE]),
        ):
            function = getattr(self.api, name)
            function.restype = restype
            function.argtypes = argtypes
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            self._error()
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(
            self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            error = getattr(ctypes, "get_last_error")()
            self.close()
            raise OSError(error, "cannot configure the run's process job")

    @staticmethod
    def _error() -> None:
        raise OSError(getattr(ctypes, "get_last_error")(), "cannot own the run's process job")

    def assign(self, pid: int) -> None:
        handle = self.api.OpenProcess(0x0101, False, pid)  # SET_QUOTA | TERMINATE
        if not handle:
            self._error()
        try:
            if not self.api.AssignProcessToJobObject(self.handle, handle):
                self._error()
        finally:
            self.api.CloseHandle(handle)

    def close(self) -> None:
        handle, self.handle = self.handle, None
        if handle and not self.api.CloseHandle(handle):
            self._error()


class _Output(Protocol):
    def seek(self, offset: int, whence: int = 0) -> int: ...
    def tell(self) -> int: ...
    def read(self, size: int = -1) -> bytes: ...


def _tail(stream: _Output, characters: int) -> str:
    stream.seek(0, os.SEEK_END)
    stream.seek(max(0, stream.tell() - characters * 4))
    return stream.read().decode("utf-8", errors="replace")[-characters:]


def run_owned(command: list[str], *, cwd: Path, timeout: float) -> CommandResult:
    """Run once; close the owned tree on timeout, interruption and normal exit.

    File-backed output avoids inherited pipe handles hanging timeout cleanup and
    bounds the memory used for returned diagnostics. Temporary output is removed.
    """
    deadline = time.monotonic() + timeout
    process: subprocess.Popen[bytes] | None = None
    with (
        tempfile.TemporaryFile() as stdout,
        tempfile.TemporaryFile() as stderr,
        tempfile.TemporaryDirectory(prefix="testence-gate-") as gate_dir,
    ):
        job = _WindowsJob() if os.name == "nt" else None
        ready = Path(gate_dir) / "ready"
        try:
            options: dict[str, Any] = {}
            if job is not None:
                command = [
                    sys.executable,
                    "-I",
                    "-S",
                    str(Path(__file__).with_name("_process_gate.py")),
                    str(ready),
                    *command,
                ]
                options = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW")}
            else:
                options = {"start_new_session": True}
            process = subprocess.Popen(
                command,
                cwd=cwd,
                stdin=subprocess.PIPE if job is not None else subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                **options,
            )
            try:
                if job is not None:
                    # The gate is isolated (-I -S) and cannot run project code
                    # while this readiness/ownership handshake is in progress.
                    while True:
                        if time.monotonic() >= deadline:
                            raise subprocess.TimeoutExpired("process gate", timeout)
                        try:
                            gate_pid = int(ready.read_text(encoding="ascii"))
                            break
                        except (FileNotFoundError, PermissionError):
                            # Publication is atomic, but Windows can briefly deny
                            # sharing the file. Observe within the original budget;
                            # never release project code without a verified PID.
                            pass
                        if process.poll() is not None:
                            raise OSError("the run's process gate exited before readiness")
                        time.sleep(0.01)
                    job.assign(gate_pid)
                    if gate_pid != process.pid:
                        job.assign(process.pid)
                    assert process.stdin is not None
                    process.stdin.write(b"1")
                    process.stdin.close()
                code = process.wait(timeout=max(0, deadline - time.monotonic()))
                timed_out = False
            except subprocess.TimeoutExpired:
                code, timed_out = None, True
        finally:
            if job is not None:
                job.close()
            elif process is not None:
                try:
                    getattr(os, "killpg")(process.pid, getattr(signal, "SIGKILL"))
                except ProcessLookupError:
                    pass
            if process is not None:
                if process.stdin is not None and not process.stdin.closed:
                    process.stdin.close()
                # Also covers a failed Windows assignment: the gate has never
                # been released, so killing it cannot orphan project children.
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=10)
        return CommandResult(code, _tail(stdout, 4_000), _tail(stderr, 2_000), timed_out)
