from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

from testence import pytest_plugin
from testence.cli import _evict_project_modules, _pytest_args, _WarmPytestRunner
from testence.evidence import RUN_ID_ENV


def test_warm_runner_accepts_only_direct_pytest_commands():
    assert _pytest_args(["pytest", "tests", "-q"]) == ["tests", "-q"]
    assert _pytest_args([sys.executable, "-m", "pytest", "tests"]) == ["tests"]

    with pytest.raises(ValueError, match="only supports"):
        _pytest_args(["npm", "test"])


def test_project_module_eviction_makes_the_next_import_read_disk(tmp_path, monkeypatch):
    module_name = "warm_reload_probe"
    source = tmp_path / f"{module_name}.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    module = importlib.import_module(module_name)
    assert module.VALUE == 1

    source.write_text("VALUE = 22\n", encoding="utf-8")
    # Avoid a same-size, same-timestamp bytecode cache hit on coarse filesystems.
    cache = Path(importlib.util.cache_from_source(str(source)))
    cache.unlink(missing_ok=True)
    evicted = _evict_project_modules([tmp_path])
    reloaded = importlib.import_module(module_name)

    assert module_name in evicted
    assert reloaded.VALUE == 22
    sys.modules.pop(module_name, None)


def test_warm_runner_gives_each_session_a_new_run_and_restores_environment(monkeypatch):
    seen: list[tuple[list[str], str, str, object]] = []
    ids = iter(["r-warm-1", "r-warm-2"])
    monkeypatch.setattr("testence.evidence.new_run_id", lambda: next(ids))
    monkeypatch.setattr(
        pytest,
        "main",
        lambda args, **kwargs: (
            seen.append(
                (
                    list(args),
                    os.environ[RUN_ID_ENV],
                    os.environ["WARM_PROBE"],
                    kwargs.get("plugins"),
                )
            )
            or 0
        ),
    )
    monkeypatch.setenv("WARM_PROBE", "outside")
    monkeypatch.delenv(RUN_ID_ENV, raising=False)
    runner = _WarmPytestRunner(
        [sys.executable, "-m", "pytest", "tests", "-q"],
        [],
        env={"WARM_PROBE": "inside"},
    )

    assert runner.run() == 0
    assert runner.run() == 0

    assert seen == [
        (["tests", "-q"], "r-warm-1", "inside", None),
        (["tests", "-q"], "r-warm-2", "inside", None),
    ]
    assert os.environ["WARM_PROBE"] == "outside"
    assert RUN_ID_ENV not in os.environ


def test_wait_summary_state_is_scoped_to_one_pytest_session():
    pytest_plugin._RUN_WAITS.append({"test": "old"})

    pytest_plugin.pytest_sessionstart(None)

    assert pytest_plugin._RUN_WAITS == []


def test_warm_engine_is_reused_and_closed_once(monkeypatch):
    class FakeEngine:
        starts = 0
        stops: list[bool] = []

        def start(self):
            self.starts += 1

        def stop(self, *, keep_browser=False):
            self.stops.append(keep_browser)

    class FakeSettings:
        base_url = "https://example.test"
        api_prefix = "/api/"
        cdp_url = "http://127.0.0.1:9222"
        browser_channel = "chromium"
        headed = False
        timeout_ms = 1_000
        verify_tls = True
        ca_bundle = ""
        extra: dict[str, object] = {}

    engine = FakeEngine()
    pytest_plugin.close_warm_engine()
    monkeypatch.setattr(pytest_plugin, "create_engine", lambda settings: engine)

    first = pytest_plugin._acquire_warm_engine(FakeSettings())
    second = pytest_plugin._acquire_warm_engine(FakeSettings())
    pytest_plugin.close_warm_engine()

    assert first is second is engine
    assert engine.starts == 1
    assert engine.stops == [False]
