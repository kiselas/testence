"""Host description collected only when a run or visual profile needs it.

Loading the plugin into an unrelated suite must not start a native metadata query.
The first caller collects ``platform.uname()`` and later callers share its result.
Values remain exactly what ``platform`` reports; native provider faults are not
isolated by this cache.
"""

from __future__ import annotations

import platform
import threading

_UNAME: list[platform.uname_result] = []
_LOCK = threading.Lock()


def _uname() -> platform.uname_result:
    with _LOCK:
        if not _UNAME:
            _UNAME.append(platform.uname())
        return _UNAME[0]


def system() -> str:
    """``platform.system()``."""
    return _uname().system


def os_name() -> str:
    """``"<system> <release>"``, as recorded in the run fingerprint."""
    uname = _uname()
    return f"{uname.system} {uname.release}"


__all__ = ["os_name", "system"]
