"""Failure tracebacks that start at the test.

A failed ``ex.*`` step used to print Playwright's stack, the engine's assertion and
the step machinery before the line of the test that failed: in a measured failure the
test line came 94th of 191 lines. ``StepFailed`` already carries its cause in its
message (and as ``.cause``), so the plugin hides what Testence and Playwright did
below the test's own last frame. ``--testence-full-trace``, ``TESTENCE_FULL_TRACE=1``
or pytest's ``--full-trace`` keep everything, for debugging Testence itself.
"""

from __future__ import annotations

import contextlib
import os
import sysconfig
import traceback
from importlib.util import find_spec
from pathlib import Path
from types import TracebackType
from typing import Any

FULL_TRACE_ENV = "TESTENCE_FULL_TRACE"
FULL_TRACE_HINT = (
    "frames of Testence and Playwright below the test are hidden; rerun with "
    "--testence-full-trace (or TESTENCE_FULL_TRACE=1) to see them"
)


def _directory(origin: str | None) -> str | None:
    return os.path.normcase(str(Path(origin).parent)) + os.sep if origin else None


def _package(name: str) -> str | None:
    spec = find_spec(name)
    return _directory(spec.origin if spec else None)


_TESTENCE = _directory(__file__)
_PLAYWRIGHT = _package("playwright")
# pytest and pluggy run the test; they are never the place a failure belongs to.
_RUNNER = tuple(path for path in (_package("_pytest"), _package("pluggy")) if path)
_STDLIB = tuple(
    {os.path.normcase(sysconfig.get_paths()[key]) + os.sep for key in ("stdlib", "platstdlib")}
)
_CONTEXTLIB = os.path.normcase(contextlib.__file__)


def _kind(path: Any) -> str:
    """``testence``, ``framework`` (Playwright, the standard library), ``runner`` or
    ``user``: everything else, including the project's own helpers."""
    text = os.path.normcase(str(path))
    if _TESTENCE and text.startswith(_TESTENCE):
        return "testence"
    if (_PLAYWRIGHT and text.startswith(_PLAYWRIGHT)) or text == _CONTEXTLIB:
        return "framework"
    if text.startswith(_RUNNER):
        return "runner"
    # ``<string>`` and ``<frozen ...>``: generated code such as a dataclass __init__.
    if text.startswith(_STDLIB) or text.startswith("<"):
        return "framework"
    return "user"


def shorten(excinfo: Any) -> int:
    """Cut the frames below the deepest user frame when Testence is among them.

    Returns how many frames were hidden, 0 when the traceback is left alone: a
    failure with no user frame (inside a Testence fixture) or one Testence took no
    part in (Playwright called directly) keeps its full trace. ``StepFailed`` also
    loses its displayed cause chain; the cause stays on ``.cause``.
    """
    from testence.dsl.steps import StepFailed

    # Walk the raw chain: pytest rebuilds its own traceback list from ``tb_next``,
    # so the cut has to be made there.
    frames: list[TracebackType] = []
    tb: TracebackType | None = excinfo.tb
    while tb is not None:
        frames.append(tb)
        tb = tb.tb_next
    kinds = [_kind(frame.tb_frame.f_code.co_filename) for frame in frames]
    users = [index for index, kind in enumerate(kinds) if kind == "user"]
    if not users or "testence" not in kinds[users[-1] + 1 :]:
        return 0
    frames[users[-1]].tb_next = None
    excinfo.traceback = excinfo.traceback[: users[-1] + 1]
    hidden = len(frames) - users[-1] - 1
    exc = excinfo.value
    if isinstance(exc, StepFailed) and exc.__cause__ is exc.cause:
        seen: set[int] = set()
        cause: BaseException | None = exc.cause
        while cause is not None and id(cause) not in seen:
            seen.add(id(cause))
            hidden += len(traceback.extract_tb(cause.__traceback__))
            cause = cause.__cause__ or (None if cause.__suppress_context__ else cause.__context__)
        exc.__cause__ = None
        exc.__suppress_context__ = True
    return hidden
