"""The Koobiq conformance stand for kit tests: one server and one browser per module.

The stand (``bench/sut/koobiq``) is the real ``@koobiq/react-components``,
``react-select`` and ``@xyflow/react`` built into ``dist/``; every test reloads it, so
no state crosses tests. The stand writes what each control did to ``#log``: tests
check that log, which is what the component reported, not only what is drawn.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from testence.dsl import Actions
from testence.engine import Target
from testence.engine.playwright_cdp import PlaywrightCdpEngine
from testence.evidence import EvidenceWriter

STAND = Path(__file__).resolve().parent.parent / "bench" / "sut" / "koobiq"
LOG = Target("css", "#log")
#: Step budget of every test. A test that shortens it for a negative case changes the
#: shared engine; each test starts from this again, so no budget leaks into the next.
TIMEOUT_MS = 5_000
#: How long the stand may take to render its first heading: a cold page loads the
#: Koobiq bundle, which a loaded CI runner has taken more than five seconds to do. The
#: step budget above stays for every kit step.
STAND_LOAD_MS = 30_000


def _server_module() -> Any:
    spec = importlib.util.spec_from_file_location("koobiq_stand_server", STAND / "server.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def stand() -> Iterator[str]:
    with _server_module().serve() as url:
        yield url


@pytest.fixture(scope="module")
def stand_engine(stand: str) -> Iterator[PlaywrightCdpEngine]:
    engine = PlaywrightCdpEngine(stand, headed=False, timeout_ms=TIMEOUT_MS)
    engine.start()
    try:
        yield engine
    finally:
        engine.stop()


def open_stand(engine: PlaywrightCdpEngine, tmp_path: Path, locale: str = "en-US") -> Actions:
    engine.timeout_ms = TIMEOUT_MS
    engine.reset_taps()
    engine.goto(f"/index.html?locale={locale}")
    engine.wait_for_count(
        Target("role", "heading", name="Koobiq conformance stand"), timeout_ms=STAND_LOAD_MS
    )
    return Actions(engine, EvidenceWriter(tmp_path / "evidence"), "kit-conformance")


def logged(ex: Actions, text: str) -> None:
    """The stand's event log has the entry ``text``."""
    ex.expect_visible(Target("text", text, exact=True, within=LOG), intent=f"logged {text!r}")


def not_logged(ex: Actions, text: str) -> None:
    ex.expect_count(Target("text", text, exact=True, within=LOG), 0, intent=f"not {text!r}")
