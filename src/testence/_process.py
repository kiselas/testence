"""Own a synchronous command and its descendants for its entire lifetime.

POSIX uses a new process group. Windows uses a non-inheritable kill-on-close
job and a gated launcher, assigned before it can start the requested command.
These are lifecycle controls for trusted project tests, not a security sandbox.

``ProcessTree`` is the other direction: a process somebody else spawned (the
Playwright driver) is adopted right after it starts, and its tree can be killed
on a deadline. It never reaches a process other than the adopted PID and its
descendants.
"""

from __future__ import annotations

import ctypes
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Mapping
from contextlib import suppress
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
    def __init__(self, *, kill_on_close: bool = True) -> None:
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
            ("TerminateJobObject", wintypes.BOOL, [wintypes.HANDLE, wintypes.UINT]),
            ("TerminateProcess", wintypes.BOOL, [wintypes.HANDLE, wintypes.UINT]),
        ):
            function = getattr(self.api, name)
            function.restype = restype
            function.argtypes = argtypes
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            self._error()
        if not kill_on_close:
            return
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

    def open_process(self, pid: int) -> Any:
        """A handle that keeps the PID from being reused while it is held."""
        # TERMINATE | SYNCHRONIZE | QUERY_LIMITED_INFORMATION
        return self.api.OpenProcess(0x0001 | 0x00100000 | 0x1000, False, pid) or None

    def terminate(self) -> None:
        if self.handle:
            self.api.TerminateJobObject(self.handle, 1)

    def terminate_process(self, handle: Any) -> None:
        self.api.TerminateProcess(handle, 1)

    def close_handle(self, handle: Any) -> None:
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


def run_owned(
    command: list[str],
    *,
    cwd: Path,
    timeout: float,
    env: Mapping[str, str] | None = None,
    output_limit: int | None = None,
) -> CommandResult:
    """Run once; close the owned tree on timeout, interruption and normal exit.

    File-backed output avoids inherited pipe handles hanging timeout cleanup and
    bounds the memory used for returned diagnostics. Temporary output is removed.
    """
    if output_limit is not None and output_limit <= 0:
        raise ValueError("output_limit must be positive")
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
                env=env,
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
        return CommandResult(
            code,
            _tail(stdout, output_limit or 4_000),
            _tail(stderr, output_limit or 2_000),
            timed_out,
        )


def _ps(*args: str) -> str | None:
    try:
        done = subprocess.run(
            ["ps", *args], capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def _started_at(pid: int) -> str | None:
    """When the process began; differs if the PID was handed to another process."""
    text = _ps("-o", "lstart=", "-p", str(pid))
    return (text.strip() or None) if text is not None else None


def descendants(pid: int) -> list[int]:
    """PIDs below ``pid`` in the process tree (POSIX); empty when it cannot be read."""
    text = _ps("-A", "-o", "pid=,ppid=")
    if not text:
        return []
    children: dict[int, list[int]] = {}
    for line in text.splitlines():
        fields = line.split()
        if len(fields) == 2 and all(field.isdigit() for field in fields):
            children.setdefault(int(fields[1]), []).append(int(fields[0]))
    found: list[int] = []
    queue = [pid]
    while queue:
        for child in children.get(queue.pop(), []):
            if child not in found and child != pid:
                found.append(child)
                queue.append(child)
    return found


class ProcessTree:
    """A process this code did not spawn but learned the PID of when it started.

    Adopt it as soon as it starts: on Windows the process joins a job at that
    moment, so a browser it launches later is inside the job and ``kill`` reaches
    it (the mechanism ``run_owned`` uses). On POSIX the tree is read when ``kill``
    runs. ``descendants=False`` limits ``kill`` to the one process, for a driver
    whose children are not all ours (an attached browser is never one).

    ``kill`` is safe to call from another thread, after the process has exited and
    more than once. A PID that has since been handed to an unrelated process is
    left alone.
    """

    def __init__(self, pid: int, *, descendants: bool = True) -> None:
        self.pid = pid
        self._tree = descendants
        self._job: _WindowsJob | None = None
        self._handle: Any = None
        self._assigned = False
        self._started = None if os.name == "nt" else _started_at(pid)
        self._lock = threading.Lock()
        if os.name == "nt":
            self._job = _WindowsJob(kill_on_close=False)
            self._handle = self._job.open_process(pid)
            if self._handle and descendants:
                try:
                    self._job.assign(pid)
                    self._assigned = True
                except OSError:
                    # Already inside a job that forbids nesting; kill() then walks
                    # the tree with taskkill.
                    pass

    def kill(self) -> None:
        with self._lock:
            if os.name == "nt":
                self._kill_windows()
            else:
                self._kill_posix()

    def _kill_windows(self) -> None:
        job = self._job
        if job is None or not self._handle:
            return
        if self._tree and self._assigned:
            job.terminate()
        elif self._tree:
            with suppress(OSError, subprocess.SubprocessError):
                subprocess.run(
                    ["taskkill", "/PID", str(self.pid), "/T", "/F"],
                    capture_output=True,
                    timeout=10,
                    check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
        else:
            job.terminate_process(self._handle)

    def _kill_posix(self) -> None:
        if self._started is None or _started_at(self.pid) != self._started:
            return
        victims = [*descendants(self.pid), self.pid] if self._tree else [self.pid]
        for victim in victims:
            with suppress(ProcessLookupError, PermissionError):
                os.kill(victim, getattr(signal, "SIGKILL"))

    def close(self) -> None:
        """Release the handles without ending anything."""
        with self._lock:
            job, self._job = self._job, None
            handle, self._handle = self._handle, None
            if job is not None:
                if handle:
                    job.close_handle(handle)
                job.close()
