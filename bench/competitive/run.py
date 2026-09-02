"""Run the transparent Testence vs Playwright Test replay comparison."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import random
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
NODE_ROOT = ROOT / "bench" / "node"
NODE = Path(os.environ.get("TESTENCE_BENCH_NODE", "node"))
PORT = 8898
URL = f"http://127.0.0.1:{PORT}"


def _listening(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.2)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def _start_target(port: int) -> subprocess.Popen[str] | None:
    if _listening(port):
        return None
    process = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        cwd=ROOT / "bench" / "target",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    for _ in range(50):
        if _listening(port):
            return process
        time.sleep(0.1)
    process.kill()
    raise RuntimeError("benchmark target did not start")


def _percentile(samples: list[float], pct: float) -> float:
    ordered = sorted(samples)
    index = (len(ordered) - 1) * pct / 100
    lower = math.floor(index)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def _summary(samples: list[float]) -> dict[str, float | int | list[float]]:
    generator = random.Random(20260828)
    bootstrap_medians = sorted(
        statistics.median(generator.choices(samples, k=len(samples))) for _ in range(10_000)
    )
    return {
        "n": len(samples),
        "median_ms": round(statistics.median(samples), 1),
        "median_ci95_ms": [
            round(_percentile(bootstrap_medians, 2.5), 1),
            round(_percentile(bootstrap_medians, 97.5), 1),
        ],
        "p95_ms": round(_percentile(samples, 95), 1),
        "min_ms": round(min(samples), 1),
        "max_ms": round(max(samples), 1),
        "samples_ms": [round(sample, 1) for sample in samples],
    }


def _source_stats(path: Path) -> dict[str, int | str]:
    text = path.read_text(encoding="utf-8")
    meaningful = [
        line
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith(("#", "//"))
    ]
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "bytes": len(text.encode("utf-8")),
        "nonblank_noncomment_lines": len(meaningful),
    }


def _run(command: list[str], env: dict[str, str]) -> tuple[float, str]:
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    output = (completed.stdout + "\n" + completed.stderr).strip()
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(command)}\n{output[-2000:]}"
        )
    return elapsed_ms, output


def _browser_version() -> str:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chromium", headless=True)
        try:
            return browser.version
        finally:
            browser.close()


def _fingerprint(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--warmups", type=int, default=1)
    args = parser.parse_args()
    if args.repeats < 3:
        raise SystemExit("use at least three measured repeats")

    testence_source = HERE / "testence" / "test_flow.py"
    playwright_source = NODE_ROOT / "competitive" / "playwright_flow.spec.mjs"
    config_source = NODE_ROOT / "competitive" / "playwright.config.mjs"
    sut_source = ROOT / "bench" / "target" / "index.html"
    cli = NODE_ROOT / "node_modules" / "@playwright" / "test" / "cli.js"
    if not cli.exists():
        raise SystemExit("run npm ci --prefix bench/node first")

    target = _start_target(PORT)
    try:
        with tempfile.TemporaryDirectory(prefix="testence-competitive-") as temp:
            scratch = Path(temp)
            common = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
            commands = {
                "testence": [
                    sys.executable,
                    "-m",
                    "pytest",
                    str(testence_source),
                    "--testence-headless",
                    "-q",
                    "-p",
                    "no:cacheprovider",
                    "--rootdir",
                    str(testence_source.parent),
                ],
                "playwright_test": [
                    str(NODE),
                    str(cli),
                    "test",
                    "--config",
                    str(config_source),
                ],
            }
            environments = {
                "testence": {
                    **common,
                    "TESTENCE_BASE_URL": URL,
                    "TESTENCE_AUTH": "none",
                    "TESTENCE_BROWSER_CHANNEL": "chromium",
                    "TESTENCE_RUNS_ROOT": str(scratch / "testence-runs"),
                },
                "playwright_test": {
                    **common,
                    "BENCH_BASE_URL": URL,
                    "BENCH_ARTIFACT_DIR": str(scratch / "playwright-results"),
                },
            }

            results: dict[str, dict[str, object]] = {}
            for arm in ("testence", "playwright_test"):
                for _ in range(args.warmups):
                    _run(commands[arm], environments[arm])
                samples = []
                for attempt in range(1, args.repeats + 1):
                    elapsed, _ = _run(commands[arm], environments[arm])
                    samples.append(elapsed)
                    print(f"{arm} {attempt}/{args.repeats}: {elapsed:.1f} ms", flush=True)
                source = testence_source if arm == "testence" else playwright_source
                results[arm] = {**_summary(samples), "source": _source_stats(source)}
    finally:
        if target is not None:
            target.terminate()

    testence_median = float(results["testence"]["median_ms"])
    playwright_median = float(results["playwright_test"]["median_ms"])
    payload = {
        "schema": "testence/competitive-replay/1",
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "scenario": "six intent-bearing steps on bench/target/index.html",
        "timing_boundary": (
            "fresh runner process; discovery, browser launch, test, reporting and shutdown; "
            "SUT startup excluded"
        ),
        "policy": {
            "warmups_per_arm": args.warmups,
            "measured_repeats_per_arm": args.repeats,
            "workers": 1,
            "retries": 0,
            "tracing": "off",
            "video": "off",
            "arms_run": "serial",
        },
        "environment": {
            "os": platform.platform(),
            "machine": platform.machine(),
            "logical_cpu_count": os.cpu_count(),
            "python": platform.python_version(),
            "node": subprocess.check_output([str(NODE), "--version"], text=True).strip(),
            "browser": f"Playwright Chromium {_browser_version()}",
            "python_playwright": importlib.metadata.version("playwright"),
            "pytest": importlib.metadata.version("pytest"),
            "node_playwright_test": json.loads(
                (NODE_ROOT / "node_modules" / "@playwright" / "test" / "package.json").read_text(
                    encoding="utf-8"
                )
            )["version"],
            "benchmark_revision": _fingerprint(
                [Path(__file__), testence_source, playwright_source, config_source, sut_source]
            ),
        },
        "arms": results,
        "derived": {
            "testence_vs_playwright_median_ratio": round(testence_median / playwright_median, 3),
            "testence_median_overhead_pct": round(
                (testence_median / playwright_median - 1) * 100, 1
            ),
        },
        "authoring_note": (
            "source size is a transparent proxy only; elapsed authoring and review time were "
            "not measured in this replay experiment"
        ),
    }
    output = ROOT / "bench" / "results" / "competitive-replay.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(payload, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps(payload, indent=1))


if __name__ == "__main__":
    main()
