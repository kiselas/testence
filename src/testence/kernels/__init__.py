"""Kernel dispatch: pure-Python by default, native backend when one is installed.

Usage from the rest of the framework::

    from testence import kernels
    events = kernels.parse_ledger(data)

Backend selection (``TESTENCE_KERNELS`` env var):

- ``auto`` (default) — use the native backend if importable, else reference.
- ``reference`` — force pure Python (CI conformance runs, differential testing).
- ``native`` — force native; raise if unavailable (so benchmarks cannot silently
  measure the wrong arm — a "native" number that was actually Python is worse than
  no number).

A native backend is any importable module named ``testence_kernels`` exposing the
:class:`~testence.kernels.contracts.KernelBackend` surface plus ``name``/``abi``.
It will ship as a separate optional wheel and is never imported by callers directly.
Until that wheel is published, the reserved ``testence[native]`` extra remains empty;
Testence stays fully functional with zero native artifacts.
"""

from __future__ import annotations

import importlib
import os
from typing import Any

from . import reference
from .contracts import KERNEL_ABI, KernelBackend

_NATIVE_MODULE = "testence_kernels"


def _load_backend() -> Any:
    mode = os.environ.get("TESTENCE_KERNELS", "auto").strip().lower()
    if mode == "reference":
        return reference
    try:
        native = importlib.import_module(_NATIVE_MODULE)
    except ImportError:
        if mode == "native":
            raise RuntimeError(
                f"TESTENCE_KERNELS=native but {_NATIVE_MODULE!r} is not installed"
            ) from None
        return reference
    declared = getattr(native, "abi", None)
    if declared != KERNEL_ABI:
        message = (
            f"{_NATIVE_MODULE} implements kernel ABI {declared!r}, "
            f"this Testence needs {KERNEL_ABI}"
        )
        if mode == "native":
            raise RuntimeError(message)
        import warnings

        warnings.warn(f"{message}; falling back to reference kernels", stacklevel=2)
        return reference
    return native


backend: Any = _load_backend()


def active_backend() -> dict[str, Any]:
    """Which backend is in use — recorded in every run's fingerprint, so a
    benchmark result can never be misattributed to the wrong implementation."""
    return {"name": backend.name, "abi": backend.abi}


def use_backend(module: Any) -> Any:
    """Swap the active backend (differential tests and benchmarks). Returns the
    previous one so callers can restore it."""
    global backend
    previous, backend = backend, module
    return previous


def parse_ledger(data: bytes) -> list[dict[str, Any]]:
    return backend.parse_ledger(data)


def estimate_tokens(text: str) -> int:
    return backend.estimate_tokens(text)


def percentiles(values: list[float], pcts: list[float]) -> list[float | None]:
    return backend.percentiles(values, pcts)


def diff_aria(before: str, after: str) -> dict[str, Any]:
    return backend.diff_aria(before, after)


def score_candidates(target: dict[str, Any], candidates: list[dict[str, Any]]) -> list[float]:
    return backend.score_candidates(target, candidates)


__all__ = [
    "KERNEL_ABI",
    "KernelBackend",
    "active_backend",
    "use_backend",
    "reference",
    "parse_ledger",
    "estimate_tokens",
    "percentiles",
    "diff_aria",
    "score_candidates",
]
