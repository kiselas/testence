"""Compare fresh runs with warm pytest sessions and a retained CDP client.

Both arms borrow the same persistent Chromium context. A fresh run creates a Python
process and CDP client every time. The warm arm creates a new pytest session, run id,
fixtures and writer per iteration while retaining its Playwright/CDP engine connection.
The first warm call is reported separately because it still pays cold setup costs.

    .venv/Scripts/python bench/warm_runner_latency.py --repeats 5 --check
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from react_latency import (
    CORPUS,
    ROOT,
    SPEC,
    _events,
    distribution,
    evaluate_budget,
    run_once,
    start_target,
)

from testence.cli import _WarmPytestRunner

DEFAULT_BUDGET = ROOT / "bench" / "budgets" / "warm_runner_latency.json"


class SharedBrowserThread:
    """Own a sync Playwright launcher on a dedicated thread."""

    def __init__(self, base_url: str, port: int, profile_dir: Path) -> None:
        self.base_url = base_url
        self.port = port
        self.profile_dir = profile_dir
        self.start_ms = 0.0
        self._ready = threading.Event()
        self._stop = threading.Event()
        self._error: BaseException | None = None
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def _serve(self) -> None:
        from testence.engine.playwright_cdp import PlaywrightCdpEngine

        engine = PlaywrightCdpEngine(
            base_url=self.base_url,
            headed=False,
            debug_port=self.port,
            browser_channel="chromium",
            api_prefix="/api/",
            user_data_dir=str(self.profile_dir),
            reduce_motion=True,
        )
        started = time.perf_counter()
        try:
            engine.start()
            self.start_ms = (time.perf_counter() - started) * 1000
        except Exception as exc:  # noqa: BLE001 - transport errors cross the thread boundary
            self._error = exc
            self._ready.set()
            return
        self._ready.set()
        self._stop.wait()
        engine.stop()

    def start(self) -> None:
        self._thread.start()
        if not self._ready.wait(timeout=20):
            raise RuntimeError("shared browser did not start within 20 seconds")
        if self._error is not None:
            raise RuntimeError(f"shared browser failed: {self._error}") from self._error

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=10)
        if self._thread.is_alive():
            raise RuntimeError("shared browser thread did not stop")


def _read_session(run_dir: Path, elapsed_ms: float) -> dict[str, float]:
    events = _events(run_dir / "run.jsonl")
    run_end = next(event for event in events if event["kind"] == "run.end")
    test_end = next(event for event in events if event["kind"] == "test.end")
    session_ms = float(run_end["duration_ms"])
    return {
        "run_ms": elapsed_ms,
        "bootstrap_ms": max(0.0, elapsed_ms - session_ms),
        "session_ms": session_ms,
        "test_ms": float(test_end["duration_ms"]),
    }


def _pct_reduction(before: float, after: float) -> float:
    return round((before - after) / before * 100, 2) if before else 0.0


def run_benchmark(repeats: int, port: int, cdp_port: int) -> dict[str, Any]:
    root = ROOT / "runs" / "warm-runner-latency"
    fresh_root = root / "fresh"
    warm_root = root / "warm"
    fresh_root.mkdir(parents=True, exist_ok=True)
    warm_root.mkdir(parents=True, exist_ok=True)
    base_url = f"http://127.0.0.1:{port}"
    cdp_url = f"http://127.0.0.1:{cdp_port}"

    target = start_target(port)
    browser = SharedBrowserThread(base_url, cdp_port, root / ".shared-browser-profile")
    runner: _WarmPytestRunner | None = None
    try:
        browser.start()
        fresh = []
        for attempt in range(1, repeats + 1):
            print(f"[{attempt}/{repeats}] fresh attached process", file=sys.stderr, flush=True)
            fresh.append(run_once(port, attempt, fresh_root, cdp_url=cdp_url))

        cmd = [
            sys.executable,
            "-m",
            "pytest",
            str(SPEC),
            "--testence-headless",
            "-q",
            "-p",
            "no:cacheprovider",
            "--rootdir",
            str(CORPUS),
            "-c",
            str(CORPUS / "pytest.ini"),
        ]
        env = {
            "TESTENCE_BASE_URL": base_url,
            "TESTENCE_AUTH": "none",
            "TESTENCE_CDP_URL": cdp_url,
            "TESTENCE_HEADED": "false",
            "TESTENCE_RUNS_ROOT": str(warm_root),
            "PYTHONPATH": str(ROOT / "src"),
        }
        runner = _WarmPytestRunner(cmd, [CORPUS], env=env)
        warm = []
        for attempt in range(1, repeats + 1):
            print(f"[{attempt}/{repeats}] warm retained engine", file=sys.stderr, flush=True)
            run_id = f"react-latency-warm-{attempt}"
            run_dir = warm_root / run_id
            shutil.rmtree(run_dir, ignore_errors=True)
            started = time.perf_counter()
            code = runner.run(
                run_id=run_id,
                extra_env={"TESTENCE_SUT_RUN": f"{run_id}-{time.time_ns()}"},
            )
            elapsed_ms = (time.perf_counter() - started) * 1000
            if code:
                raise RuntimeError(f"warm React latency attempt {attempt} exited {code}")
            warm.append(_read_session(run_dir, elapsed_ms))
    finally:
        if runner is not None:
            runner.close()
        browser.close()
        if target is not None:
            target.terminate()
            try:
                target.wait(timeout=5)
            except subprocess.TimeoutExpired:
                target.kill()

    steady = warm[1:]
    fresh_run = distribution([run["fresh_process_ms"] for run in fresh])
    fresh_bootstrap = distribution([run["bootstrap_ms"] for run in fresh])
    warm_run = distribution([run["run_ms"] for run in steady])
    warm_bootstrap = distribution([run["bootstrap_ms"] for run in steady])
    return {
        "schema": "testence/warm-runner-latency/2",
        "scenario": "fresh process versus warm pytest sessions with retained CDP client",
        "environment": {"os": os.name, "python": sys.version.split()[0]},
        "repeats": repeats,
        "shared_browser_start_ms": round(browser.start_ms, 2),
        "fresh_attached_run_ms": fresh_run,
        "fresh_attached_bootstrap_ms": fresh_bootstrap,
        "warm_cold_run_ms": distribution([warm[0]["run_ms"]]),
        "warm_steady_run_ms": warm_run,
        "warm_steady_bootstrap_ms": warm_bootstrap,
        "warm_steady_session_ms": distribution([run["session_ms"] for run in steady]),
        "warm_steady_test_ms": distribution([run["test_ms"] for run in steady]),
        "comparison": {
            "run_reduction_percent": _pct_reduction(
                float(fresh_run["p50"]), float(warm_run["p50"])
            ),
            "bootstrap_reduction_percent": _pct_reduction(
                float(fresh_bootstrap["p50"]), float(warm_bootstrap["p50"])
            ),
        },
        "note": (
            "The cold warm call is excluded. Project modules, pytest sessions, fixtures, "
            "run ids and writers are renewed; only the Playwright/CDP engine is retained."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--port", type=int, default=8800)
    parser.add_argument("--cdp-port", type=int, default=9333)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--budget", type=Path, default=DEFAULT_BUDGET)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.repeats < 2:
        parser.error("--repeats must be at least 2 (one cold and one steady warm run)")

    result = run_benchmark(args.repeats, args.port, args.cdp_port)
    budget = json.loads(args.budget.read_text(encoding="utf-8"))
    violations = evaluate_budget(result, budget) if args.check else []
    result["budget"] = {
        "checked": args.check,
        "source": args.budget.resolve().relative_to(ROOT.resolve()).as_posix(),
        "passed": not violations if args.check else None,
        "violations": violations,
    }
    rendered = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8", newline="\n")
    print(rendered)
    if violations:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
