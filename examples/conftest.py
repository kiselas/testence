"""Fixtures for the runnable examples.

The examples read the shared synthetic application from ``tests/mock_app.py`` so that
one loopback app serves both the suite and the documentation. pytest puts only
``examples/`` on ``sys.path`` when this directory is collected on its own, so
``pytest examples`` from a fresh clone would fail to import it. Add the repository root
explicitly instead of asking every reader to remember ``PYTHONPATH=.``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "demo_failure: deliberately failing pack demo")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("-m", default=""):
        return
    skip = pytest.mark.skip(reason="pack demo; run with -m demo_failure")
    for item in items:
        if "demo_failure" in item.keywords:
            item.add_marker(skip)
