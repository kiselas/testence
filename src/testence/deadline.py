"""A deadline per test: a test that hangs fails with where it hung, the process lives.

A hung test used to cost the whole worker: nothing in pytest ends a call that never
returns, pytest-timeout's ``thread`` method (the only one on Windows) ends the
process, and the rest of the worker's tests became ``broken``. The deadline instead
works in two stages:

1. At the deadline the watchdog records the stack of the thread running the test.
   When that thread is in Python code (a poll loop, a sleep, a fixture), it raises
   :class:`DeadlineExceeded` there (``PyThreadState_SetAsyncExc``).
2. When the thread is inside the browser driver's client (Playwright), an exception
   raised in the middle of its dispatcher would leave the client unable to close
   anything. The watchdog instead kills the browser and driver processes Testence
   started in this process, never an attached browser; the stuck call then raises
   and the test fails. The same kill follows a grace period when an exception raised
   in Python code is not taken, because the thread is blocked in another C call.

Either way the report says that the deadline passed and where the test was. Setup and
call share one deadline; teardown gets one of its own, so a fixture that hangs while
cleaning up is reported as such. Nothing is retried.
"""

from __future__ import annotations

import ctypes
import os
import sys
import threading
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable

#: How long a stuck driver call gets to take the exception before the kill.
GRACE_ENV = "TESTENCE_DEADLINE_GRACE_S"
DEFAULT_GRACE_S = 5.0
TIMEOUT_ENV = "TESTENCE_TEST_TIMEOUT"
#: The longest deadline accepted: a day. Anything longer is a typo.
MAX_TIMEOUT_S = 86_400.0


class DeadlineExceeded(BaseException):
    """Raised in a test that ran past its deadline.

    A ``BaseException``, like pytest's own outcomes, so an ``except Exception`` in
    the code under the deadline does not swallow it and hang on.
    """


def parse_timeout(value: Any, source: str) -> float | None:
    """A deadline in seconds from a setting, an option or a marker; None for none."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError(f"{source} must be a number of seconds")
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{source} must be a number of seconds, not {value!r}") from None
    if seconds == 0:
        return None
    if not 0 < seconds <= MAX_TIMEOUT_S:
        raise ValueError(f"{source} must be between 0 and {MAX_TIMEOUT_S:.0f} seconds")
    return seconds


def grace_s() -> float:
    raw = os.environ.get(GRACE_ENV, "")
    try:
        value = float(raw) if raw else DEFAULT_GRACE_S
    except ValueError:
        value = DEFAULT_GRACE_S
    return max(0.1, value)


def _raise_in(thread_id: int, exc: type[BaseException] | None) -> bool:
    """Schedule ``exc`` in another thread (None clears a scheduled one)."""
    api = getattr(ctypes, "pythonapi", None)
    setter = getattr(api, "PyThreadState_SetAsyncExc", None)
    if setter is None:  # not CPython: only the kill stage works
        return False
    target = ctypes.py_object(exc) if exc is not None else None
    return int(setter(ctypes.c_ulong(thread_id), target)) == 1


#: Where a frame of the browser driver's client lives: an exception must not be
#: raised in it (see the module docstring).
_DRIVER_PARTS = (f"{os.sep}playwright{os.sep}", f"{os.sep}greenlet{os.sep}")


def _in_driver(thread_id: int) -> bool:
    frame = sys._current_frames().get(thread_id)
    while frame is not None:
        filename = frame.f_code.co_filename
        if any(part in filename for part in _DRIVER_PARTS):
            return True
        frame = frame.f_back
    return False


def _stack_of(thread_id: int, limit: int = 40) -> list[str]:
    frame = sys._current_frames().get(thread_id)
    if frame is None:
        return []
    lines: list[str] = []
    for entry in traceback.format_stack(frame)[-limit:]:
        lines.extend(line for line in entry.rstrip("\n").splitlines() if line.strip())
    return lines


@dataclass
class Expiry:
    """What the watchdog saw when a deadline passed."""

    phase: str
    deadline_s: float
    stack: list[str]
    killed: int = 0
    #: The thread was inside the driver's client: ``stack`` is then the client's
    #: dispatcher until the caller replaces it with the stuck call's traceback.
    in_driver: bool = False
    #: When the exception was scheduled, on the monotonic clock.
    fired_at: float = field(default_factory=time.monotonic)

    def use_traceback(self, tb: Any) -> None:
        """Take the place the test was from the traceback the stuck call raised with."""
        lines: list[str] = []
        for entry in traceback.format_tb(tb)[-40:]:
            lines.extend(line for line in entry.rstrip().splitlines() if line.strip())
        if lines:
            self.stack = lines

    def message(self) -> str:
        where = "\n".join(f"  {line}" for line in self.stack[-12:]) or "  (stack unavailable)"
        killed = (
            f"; the test was stuck in the browser driver, so the {self.killed} browser "
            "process tree(s) Testence started were killed"
            if self.killed
            else ""
        )
        return (
            f"the test ran past its {self.deadline_s:g} s deadline in {self.phase}{killed}. "
            f"It was here:\n{where}"
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "deadline_s": self.deadline_s,
            "killed": self.killed,
            "in_driver": self.in_driver,
            "stack": self.stack,
        }


class Watchdog:
    """One running deadline for the thread that created it."""

    def __init__(
        self,
        deadline_s: float,
        phase: str,
        *,
        kill: Callable[[], int],
        grace: float | None = None,
    ) -> None:
        self.deadline_s = deadline_s
        self.phase = phase
        self.expiry: Expiry | None = None
        self._kill = kill
        self._grace = grace_s() if grace is None else grace
        self._thread_id = threading.get_ident()
        self._lock = threading.Lock()
        self._active = True
        self._timer = threading.Timer(deadline_s, self._expire)
        self._timer.daemon = True
        self._second: threading.Timer | None = None
        self._timer.start()

    def _expire(self) -> None:
        with self._lock:
            if not self._active:
                return
            self.expiry = Expiry(self.phase, self.deadline_s, _stack_of(self._thread_id))
            if _in_driver(self._thread_id):
                kill_now = True
                self.expiry.in_driver = True
            else:
                kill_now = False
                _raise_in(self._thread_id, DeadlineExceeded)
                second = threading.Timer(self._grace, self._kill_stuck)
                second.daemon = True
                self._second = second
                second.start()
        if kill_now:
            self._kill_stuck()

    def _kill_stuck(self) -> None:
        with self._lock:
            if not self._active or self.expiry is None:
                return
            expiry = self.expiry
        try:
            killed = self._kill()
        except Exception:  # noqa: BLE001 - a failed kill leaves the report as it is
            killed = 0
        with self._lock:
            expiry.killed = killed

    def stop(self) -> Expiry | None:
        """End the watch from the test's own thread; return the expiry, if any.

        A scheduled exception that has not reached the thread yet is cleared, so it
        cannot surface later inside pytest or the next test.
        """
        with self._lock:
            self._active = False
            self._timer.cancel()
            if self._second is not None:
                self._second.cancel()
            if self.expiry is not None and threading.get_ident() == self._thread_id:
                _raise_in(self._thread_id, None)
            return self.expiry
