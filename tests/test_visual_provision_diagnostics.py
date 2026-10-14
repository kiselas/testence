import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest
from playwright.sync_api import TimeoutError as CaptureTimeout

from testence import visual
from testence.config import Settings

Image = pytest.importorskip("PIL.Image")
PROVISION = Path(__file__).parents[1] / "bench/client_simulation/provision.py"


def run_provision(monkeypatch, tmp_path, *, capture_fault=None, metadata_fault=None, sink=None):
    error = CaptureTimeout("synthetic capture deadline")

    class Engine:
        def __init__(self):
            self.captures = 0
            self.stops = 0
            self.metadata_reads = 0

        def start(self):
            pass

        def goto(self, _url):
            pass

        def click(self, _target):
            pass

        def expect_visible(self, _target):
            pass

        def eval_js(self, _expression):
            self.metadata_reads += 1
            if metadata_fault == "exception":
                raise RuntimeError("synthetic observer unavailable")
            if metadata_fault == "invalid":
                return {"readyState": object(), "width": "private value", "url": "secret"}
            return {
                "readyState": "complete",
                "fonts": "loaded",
                "width": 40,
                "height": 30,
                "resources": 0,
                "incompleteResources": 0,
            }

        def screenshot(self, path):
            self.captures += 1
            if self.captures == capture_fault:
                raise error
            Image.new("RGB", (40, 30), "white").save(path)

        def stop(self):
            self.stops += 1

    engine = Engine()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Settings, "load", lambda _root: SimpleNamespace())
    monkeypatch.setattr("testence.engine.create_engine", lambda _settings: engine)
    monkeypatch.setattr(visual, "_profile", lambda _engine: {"width": 40, "height": 30})
    globals_ = {"print": sink} if sink is not None else None
    return (
        engine,
        error,
        lambda: runpy.run_path(str(PROVISION), run_name="__main__", init_globals=globals_),
    )


def records(capsys):
    return [
        json.loads(line.removeprefix("PROVISION "))
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("PROVISION ")
    ]


@pytest.mark.parametrize("fault", [1, 2])
def test_authoring_capture_failure_keeps_state_error_identity_and_no_retry(
    monkeypatch, tmp_path, capsys, fault
):
    engine, error, run = run_provision(monkeypatch, tmp_path, capture_fault=fault)
    with pytest.raises(CaptureTimeout) as failure:
        run()
    assert failure.value is error
    assert engine.captures == fault and engine.stops == 1
    assert not (tmp_path / "baselines/overview/baseline.json").exists()
    assert not (tmp_path / "baselines.json").exists()
    rows = records(capsys)
    errors = [row for row in rows if row["stage"] == "screenshot" and row["outcome"] == "error"]
    assert len(errors) == 1
    assert errors[0]["state"] == "overview" and errors[0]["capture"] == fault
    assert errors[0]["error_type"] == "TimeoutError"
    assert errors[0]["elapsed_ms"] >= 0


@pytest.mark.parametrize("metadata", [None, "exception", "invalid"])
def test_authoring_observer_cannot_replace_two_capture_stability_or_leak_data(
    monkeypatch, tmp_path, capsys, metadata
):
    engine, _error, run = run_provision(monkeypatch, tmp_path, metadata_fault=metadata)
    run()
    assert engine.captures == 4 and engine.stops == 1 and engine.metadata_reads == 2
    bindings = json.loads((tmp_path / "baselines.json").read_text())
    assert set(bindings) == {"overview", "dialog"}
    rows = records(capsys)
    done = [row for row in rows if row["stage"] == "screenshot" and row["outcome"] == "returned"]
    assert [(row["state"], row["capture"]) for row in done] == [
        ("overview", 1),
        ("overview", 2),
        ("dialog", 1),
        ("dialog", 2),
    ]
    assert "secret" not in json.dumps(rows) and "private value" not in json.dumps(rows)
    assert all(row["schema"] == "testence/provision-diagnostic/1" for row in rows)
    assert len(rows) <= 64
    snapshots = [row for row in rows if row["stage"] == "snapshot"]
    assert len(snapshots) == 2
    expected = {None: "observed", "exception": "unavailable", "invalid": "incomplete"}[metadata]
    assert all(row["outcome"] == expected for row in snapshots)


def test_authoring_log_sink_failure_preserves_capture_exception_and_cleanup(monkeypatch, tmp_path):
    def broken_sink(*_args, **_kwargs):
        raise BrokenPipeError("synthetic sink closed")

    engine, error, run = run_provision(monkeypatch, tmp_path, capture_fault=1, sink=broken_sink)
    with pytest.raises(CaptureTimeout) as failure:
        run()
    assert failure.value is error
    assert engine.captures == 1 and engine.stops == 1
