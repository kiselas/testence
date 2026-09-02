"""Reporting exporters: ledger → integration formats (ADR-0013).

``run.jsonl`` is the only source of truth; every reporting system is a *sink*, fed
after the run by a pure function of the ledger. Nothing in the framework or in a
test suite imports a reporting library — capture is ambient, so a call site cannot
forget to record, and there is no second version of what happened.

**No format is special.** Allure is one module behind the same seam as everything
else; an exporter is a module exposing exactly two symbols::

    name: str
    export(run: LoadedRun, out_dir: Path) -> list[Path]

It receives the parsed, merged ledger (never raw files) and returns the files it
wrote. That is the whole contract, deliberately: an exporter that needs more
framework API means the *ledger* is missing data — extend schema ``testence/1`` by
appending a field, never by instrumenting test code.

Two ways to register one:

- in-tree, listed in :data:`BUILTIN_EXPORTERS` and stdlib-only (ADR-0007);
- out-of-tree, via the ``testence.exporters`` entry-point group — the mechanism the
  pytest plugin already uses for ``pytest11``. A third party ships its own
  distribution, with its own dependencies, and never touches this tree.

Modules are imported only when their name is requested, so a run that exports
nothing pays nothing, and deleting one exporter breaks exactly its own goldens.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, Protocol

from ._model import LoadedRun, Step, Test

__all__ = [
    "BUILTIN_EXPORTERS",
    "ENTRY_POINT_GROUP",
    "Exporter",
    "ExporterError",
    "LoadedRun",
    "Step",
    "Test",
    "available",
    "export_run",
    "load",
]

#: In-tree exporters. One line per format is the entire cost of shipping one.
BUILTIN_EXPORTERS: dict[str, str] = {
    "allure": "testence.export.allure",
    "ctrf": "testence.export.ctrf",
}

#: Entry-point group third-party exporters register under.
ENTRY_POINT_GROUP = "testence.exporters"


class Exporter(Protocol):
    """Structural type of an exporter module (documentation, and what tests check)."""

    name: str

    def export(self, run: LoadedRun, out_dir: Path) -> list[Path]: ...


class ExporterError(RuntimeError):
    """Raised for an unknown or malformed exporter — never for a bad ledger."""


def _discovered() -> dict[str, Any]:
    """Third-party exporters, by name. Discovery never breaks the CLI: a broken
    distribution in the environment must not stop a built-in export."""
    try:
        from importlib.metadata import entry_points

        return {entry.name: entry for entry in entry_points(group=ENTRY_POINT_GROUP)}
    except Exception:  # noqa: BLE001  # pragma: no cover - environment-dependent
        return {}


def available() -> dict[str, str]:
    """Every registered exporter, name → where it came from."""
    found = {name: "built-in" for name in BUILTIN_EXPORTERS}
    for name, entry in _discovered().items():
        if name in found:
            continue
        dist = getattr(getattr(entry, "dist", None), "name", None)
        found[name] = f"entry point ({dist})" if dist else "entry point"
    return found


def load(name: str) -> Exporter:
    """Resolve an exporter by name, built-ins first.

    Built-ins win on purpose: an installed package must not silently redefine what
    ``--to allure`` means in a pipeline that has been green for a year.
    """
    module: Any
    if name in BUILTIN_EXPORTERS:
        module = importlib.import_module(BUILTIN_EXPORTERS[name])
    else:
        entry = _discovered().get(name)
        if entry is None:
            known = ", ".join(sorted(available())) or "none"
            raise ExporterError(f"unknown exporter {name!r}; available: {known}")
        try:
            module = entry.load()
        except Exception as exc:  # a third party's import error, reported as theirs
            raise ExporterError(f"exporter {name!r} failed to import: {exc}") from exc

    missing = [symbol for symbol in ("name", "export") if not hasattr(module, symbol)]
    if missing:
        raise ExporterError(
            f"exporter {name!r} ({getattr(module, '__name__', module)}) is missing "
            f"{', '.join(missing)}; an exporter must expose `name: str` and "
            "`export(run, out_dir) -> list[Path]`"
        )
    if not callable(module.export):
        raise ExporterError(f"exporter {name!r} has a non-callable `export`")
    return module


def default_out_dir(run_dir: Path, name: str) -> Path:
    """Where an export lands unless asked otherwise: ``<run-dir>/<name>-results``.

    Uniform across formats, and for Allure it is the directory ``allurectl`` already
    expects to be handed.
    """
    return Path(run_dir) / f"{name}-results"


def export_run(run_dir: Path | str, name: str, out_dir: Path | str | None = None) -> list[Path]:
    """Render one integration format from a finished run.

    The ledger is read through :func:`testence.metrics.load_run`, so shard merging
    (ADR-0012) applies here exactly as it does for metrics and the HTML report.
    """
    from testence.metrics import load_run

    run_path = Path(run_dir)
    exporter = load(name)
    target = Path(out_dir) if out_dir is not None else default_out_dir(run_path, name)
    run = LoadedRun.from_events(load_run(run_path), run_path)
    target.mkdir(parents=True, exist_ok=True)
    return exporter.export(run, target)
