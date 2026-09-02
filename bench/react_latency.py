"""Measure Testence against the repository's production-built React SUT.

The default one-repeat run is a quick local profile. ``--check`` is the stable CI
gate: it requires at least three fresh pytest processes and applies deliberately
broad ceilings from ``bench/budgets/react_latency.json``. Those ceilings catch
algorithmic regressions (a hidden 2-5 second wait) without pretending two different
CI hosts have identical microsecond performance.

``--shared-browser`` launches one persistent Chromium context, then makes every
fresh pytest process attach over CDP. That isolates browser-reuse savings from
Python/pytest startup and exercises the same path used during agent authoring.

    .venv/Scripts/python bench/react_latency.py
    .venv/Scripts/python bench/react_latency.py --repeats 5 --check
    .venv/Scripts/python bench/react_latency.py --shared-browser --repeats 5 --check
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import shutil
import socket
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING, Any

ROOT = Path(__file__).resolve().parent.parent
SUT = ROOT / "bench" / "sut"
CORPUS = ROOT / "bench" / "corpus"
SPEC = CORPUS / "spec_latency.py"
DEFAULT_BUDGET = ROOT / "bench" / "budgets" / "react_latency.json"
ATTACHED_BUDGET = ROOT / "bench" / "budgets" / "react_latency_attached.json"

sys.path.insert(0, str(ROOT / "src"))

if TYPE_CHECKING:
    from testence.engine.playwright_cdp import PlaywrightCdpEngine


def distribution(values: list[float]) -> dict[str, float | int]:
    """Nearest-rank p95 plus median; explicit and dependency-free."""
    if not values:
        return {"p50": 0.0, "p95": 0.0, "min": 0.0, "max": 0.0, "n": 0}
    ordered = sorted(values)
    p95 = ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]
    return {
        "p50": round(statistics.median(ordered), 2),
        "p95": round(p95, 2),
        "min": round(ordered[0], 2),
        "max": round(ordered[-1], 2),
        "n": len(ordered),
    }


def _listening(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.3)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def start_target(port: int) -> subprocess.Popen[str] | None:
    """Reuse an existing target, otherwise start and own one."""
    if _listening(port):
        return None
    if not (SUT / "static" / "index.html").exists():
        raise SystemExit(
            "the React SUT bundle is not built. Run:\n"
            "  npm ci --prefix bench/sut/app && npm run build --prefix bench/sut/app"
        )
    process = subprocess.Popen(
        [sys.executable, str(SUT / "server.py"), "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    for _ in range(50):
        if _listening(port):
            return process
        time.sleep(0.1)
    process.kill()
    raise SystemExit("the React SUT did not start")


def start_shared_browser(
    base_url: str, port: int, runs_root: Path
) -> tuple[PlaywrightCdpEngine, float]:
    """Launch the browser once; child pytest processes only borrow its context."""
    from testence.engine.playwright_cdp import PlaywrightCdpEngine

    if _listening(port):
        raise SystemExit(f"CDP port {port} is already in use; pass --cdp-port with a free port")
    engine = PlaywrightCdpEngine(
        base_url=base_url,
        headed=False,
        debug_port=port,
        browser_channel="chromium",
        api_prefix="/api/",
        user_data_dir=str(runs_root / ".shared-browser-profile"),
        reduce_motion=True,
    )
    started = time.perf_counter()
    engine.start()
    return engine, (time.perf_counter() - started) * 1000


def _events(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def run_once(
    port: int,
    attempt: int,
    runs_root: Path,
    *,
    cdp_url: str | None = None,
) -> dict[str, Any]:
    mode = "attached" if cdp_url else "launch"
    run_id = f"react-latency-{mode}-{attempt}"
    run_dir = runs_root / run_id
    shutil.rmtree(run_dir, ignore_errors=True)
    env = {
        **os.environ,
        "TESTENCE_BASE_URL": f"http://127.0.0.1:{port}",
        "TESTENCE_AUTH": "none",
        "TESTENCE_CDP_URL": cdp_url or "",
        "TESTENCE_HEADED": "false",
        "TESTENCE_RUNS_ROOT": str(runs_root),
        "TESTENCE_RUN_ID": run_id,
        "TESTENCE_SUT_DEFECTS": "",
        "TESTENCE_SUT_RUN": f"{run_id}-{time.time_ns()}",
        "PYTHONPATH": str(ROOT / "src"),
    }
    started = time.perf_counter()
    process = subprocess.run(
        [
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
        ],
        cwd=str(CORPUS),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    fresh_process_ms = (time.perf_counter() - started) * 1000
    if process.returncode != 0:
        detail = (process.stdout + "\n" + process.stderr)[-4_000:]
        raise RuntimeError(f"React latency attempt {attempt} failed:\n{detail}")

    events = _events(run_dir / "run.jsonl")
    run_end = next(event for event in events if event["kind"] == "run.end")
    test_end = next(event for event in events if event["kind"] == "test.end")
    sample_note = next(
        event
        for event in events
        if event["kind"] == "note" and event.get("benchmark") == "react_latency"
    )
    intents = {
        event["step"]: event.get("intent", "") for event in events if event["kind"] == "step.start"
    }
    steps = [
        {**event, "intent": intents.get(event["step"], "")}
        for event in events
        if event["kind"] == "step.end"
    ]
    session_ms = float(run_end["duration_ms"])
    return {
        "fresh_process_ms": fresh_process_ms,
        "bootstrap_ms": max(0.0, fresh_process_ms - session_ms),
        "session_ms": session_ms,
        "test_ms": float(test_end["duration_ms"]),
        "steps": steps,
        "engine": sample_note["samples"],
    }


def _step_samples(runs: list[dict[str, Any]], prefix: str) -> list[float]:
    return [
        float(step["duration_ms"])
        for run in runs
        for step in run["steps"]
        if str(step.get("intent", "")).startswith(prefix)
    ]


def _engine_samples(runs: list[dict[str, Any]], op: str) -> list[float]:
    return [
        float(sample["ms"]) for run in runs for sample in run["engine"] if sample.get("op") == op
    ]


def aggregate(
    runs: list[dict[str, Any]],
    *,
    browser_mode: str = "launch",
    shared_browser_start_ms: float | None = None,
) -> dict[str, Any]:
    engine_names = {
        "goto": "goto_ms",
        "wait_until_rendered": "wait_until_rendered_ms",
        "fill": "fill_ms",
        "fill(fast)": "fill_fast_ms",
        "click(fast)": "click_fast_ms",
        "wait_for_response": "wait_for_response_ms",
        "expect_text": "expect_text_ms",
        "wait_while_visible": "wait_while_visible_ms",
    }
    return {
        "schema": "testence/react-latency/2",
        "scenario": "production-built React controlled input and POST mutation",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "os": platform.platform(),
            "python": platform.python_version(),
            "playwright": version("playwright"),
        },
        "browser_mode": browser_mode,
        "shared_browser_start_ms": (
            round(shared_browser_start_ms, 2) if shared_browser_start_ms is not None else None
        ),
        "repeats": len(runs),
        "fresh_process_ms": distribution([run["fresh_process_ms"] for run in runs]),
        "bootstrap_ms": distribution([run["bootstrap_ms"] for run in runs]),
        "session_ms": distribution([run["session_ms"] for run in runs]),
        "test_ms": distribution([run["test_ms"] for run in runs]),
        "steps": {
            "controlled_fill_safe_ms": distribution(_step_samples(runs, "controlled fill safe")),
            "controlled_fill_fast_ms": distribution(_step_samples(runs, "controlled fill fast")),
            "mutation_round_trip_ms": distribution(_step_samples(runs, "mutation round trip")),
        },
        "engine": {
            public_name: distribution(_engine_samples(runs, op))
            for op, public_name in engine_names.items()
        },
        "note": (
            "Fresh pytest processes on one host; broad budgets detect hidden waits, "
            "not cross-machine microbenchmarks. Browser mode is explicit so launch "
            "and CDP-attach results are never mixed."
        ),
    }


def _at_path(document: dict[str, Any], path: str) -> Any:
    value: Any = document
    for part in path.split("."):
        value = value[part]
    return value


def evaluate_budget(result: dict[str, Any], budget: dict[str, Any]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    minimum_repeats = int(budget.get("minimum_repeats", 1))
    if int(result.get("repeats", 0)) < minimum_repeats:
        violations.append(
            {
                "metric": "repeats",
                "actual": result.get("repeats", 0),
                "minimum": minimum_repeats,
            }
        )
    for path, rule in budget.get("limits", {}).items():
        try:
            actual = float(_at_path(result, path))
            parent = _at_path(result, path.rsplit(".", 1)[0])
        except (KeyError, TypeError, ValueError):
            violations.append({"metric": path, "error": "metric missing"})
            continue
        samples = int(parent.get("n", 0)) if isinstance(parent, dict) else 0
        minimum_samples = int(rule.get("min_samples", 0))
        if minimum_samples and samples < minimum_samples:
            violations.append(
                {
                    "metric": path,
                    "samples": samples,
                    "minimum_samples": minimum_samples,
                }
            )
        if "max" in rule and actual > float(rule["max"]):
            violations.append({"metric": path, "actual": actual, "maximum": float(rule["max"])})
        if "min" in rule and actual < float(rule["min"]):
            violations.append({"metric": path, "actual": actual, "minimum": float(rule["min"])})
    return violations


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--port", type=int, default=8800)
    parser.add_argument(
        "--shared-browser",
        action="store_true",
        help="launch one persistent browser and attach every pytest process over CDP",
    )
    parser.add_argument("--cdp-port", type=int, default=9333)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--budget", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be at least 1")

    runs_root = ROOT / "runs" / "react-latency"
    runs_root.mkdir(parents=True, exist_ok=True)
    target = start_target(args.port)
    shared_browser: PlaywrightCdpEngine | None = None
    shared_browser_start_ms: float | None = None
    try:
        cdp_url = None
        if args.shared_browser:
            shared_browser, shared_browser_start_ms = start_shared_browser(
                f"http://127.0.0.1:{args.port}", args.cdp_port, runs_root
            )
            cdp_url = f"http://127.0.0.1:{args.cdp_port}"
        runs = []
        for attempt in range(1, args.repeats + 1):
            mode = "attach" if cdp_url else "launch"
            print(
                f"[{attempt}/{args.repeats}] fresh React run ({mode})",
                file=sys.stderr,
                flush=True,
            )
            runs.append(run_once(args.port, attempt, runs_root, cdp_url=cdp_url))
    finally:
        if shared_browser is not None:
            shared_browser.stop()
        if target is not None:
            target.terminate()
            try:
                target.wait(timeout=5)
            except subprocess.TimeoutExpired:
                target.kill()

    result = aggregate(
        runs,
        browser_mode="attached" if args.shared_browser else "launch",
        shared_browser_start_ms=shared_browser_start_ms,
    )
    budget_path = args.budget or (ATTACHED_BUDGET if args.shared_browser else DEFAULT_BUDGET)
    budget = json.loads(budget_path.read_text(encoding="utf-8"))
    violations = evaluate_budget(result, budget) if args.check else []
    try:
        budget_source = budget_path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        budget_source = str(budget_path.resolve())
    result["budget"] = {
        "checked": args.check,
        "source": budget_source,
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
