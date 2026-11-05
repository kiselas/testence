"""Real stand-in processes for the close-deadline and process-tree tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from testence._process import ProcessTree

#: A stand-in driver: when released it starts one child (the "browser") and records its PID.
DRIVER = """
import json, subprocess, sys, time
from pathlib import Path
go, out = Path(sys.argv[1]), Path(sys.argv[2])
while not go.exists():
    time.sleep(0.01)
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
out.write_text(json.dumps(child.pid))
time.sleep(600)
"""


def is_alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes

        kernel32 = getattr(ctypes, "WinDLL")("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = ctypes.c_void_p
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            kernel32.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(ctypes.c_void_p(handle))
    done = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True)
    state = done.stdout.strip()
    return bool(state) and not state.startswith("Z")


def wait_dead(pid: int, timeout: float = 10.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if not is_alive(pid):
            return True
        time.sleep(0.02)
    return False


class Driver:
    """A started driver process with an adopted tree, and the child it starts on demand."""

    def __init__(self, tmp_path: Path, *, tree: bool = True) -> None:
        self.script = tmp_path / "driver.py"
        self.script.write_text(DRIVER, encoding="utf-8")
        self.go = tmp_path / "go"
        self.out = tmp_path / "child.json"
        self.process = subprocess.Popen(
            [sys.executable, str(self.script), str(self.go), str(self.out)]
        )
        self.tree = ProcessTree(self.process.pid, descendants=tree)

    def launch_browser(self) -> int:
        """The driver starts its browser, after the tree was adopted: as in real life."""
        self.go.write_text("go", encoding="utf-8")
        end = time.monotonic() + 15
        while not self.out.exists() or not self.out.read_text(encoding="utf-8"):
            assert time.monotonic() < end, "the stand-in driver never started its child"
            time.sleep(0.02)
        return int(json.loads(self.out.read_text(encoding="utf-8")))

    def cleanup(self) -> None:
        self.tree.kill()
        self.tree.close()
        self.process.kill()
        self.process.wait(timeout=10)


class Step:
    """A Playwright object whose ``close``/``stop`` blocks until the driver is gone."""

    def __init__(self, driver: Driver | None, calls: list[str], name: str) -> None:
        self.driver, self.calls, self.name = driver, calls, name

    def _run(self) -> None:
        self.calls.append(self.name)
        if self.driver is not None:
            self.driver.process.wait()  # what a sync call stuck on a dead driver does: raise
            raise RuntimeError("target closed")

    close = stop = _run
