"""Host description for run fingerprints, computed off the start-up path.

``platform.release()`` is a WMI query on Windows with Python 3.12 (77 ms measured on
Windows 11) and ``platform.system()`` pays for it too, because both read
``platform.uname()``. That was most of the plugin's session start. The query releases
the GIL, so it runs in a thread started when this module is imported — at plugin
load — and overlaps pytest's own start-up; a caller blocks only while it is still
running. The values are exactly what ``platform`` returns.
"""

from __future__ import annotations

import platform
import threading

_UNAME: list[platform.uname_result] = []


def _query() -> None:
    _UNAME.append(platform.uname())


_THREAD = threading.Thread(target=_query, name="testence-host", daemon=True)
_THREAD.start()


def _uname() -> platform.uname_result:
    _THREAD.join()
    return _UNAME[0] if _UNAME else platform.uname()


def system() -> str:
    """``platform.system()``."""
    return _uname().system


def os_name() -> str:
    """``"<system> <release>"``, as recorded in the run fingerprint."""
    uname = _uname()
    return f"{uname.system} {uname.release}"


__all__ = ["os_name", "system"]
