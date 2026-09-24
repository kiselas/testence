"""Run the transparent replay comparison: Testence against four code-first runners.

Every arm executes the same six intent-bearing steps against ``bench/target/index.html``
in a fresh runner process per sample (discovery, browser launch, the test, reporting
and shutdown; target startup excluded). Arms are measured in rounds: every round runs
each arm once, in an order shuffled by a fixed seed, so drift of the host during the
run spreads over all arms instead of landing on whichever ran last.

Each arm runs in its own documented environment with that tool's ordinary install
(see README.md): no arm pays for another's plugins.
"""

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
ARMS = ("testence", "playwright_test", "pytest_playwright", "cypress", "seleniumbase")
SEED = 20260924


def _venv_python(name: str) -> Path:
    base = ROOT / ".tmp" / f"bench-{name}"
    return base / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _listening(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.2)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def _start_target(port: int) -> subprocess.Popen[str] | None:
    if _listening(port):
        return None
    process = subprocess.Popen(
        [sys.executable, "-m", "testence.loopback", str(port)],
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


def _run(command: list[str], env: dict[str, str], cwd: Path) -> tuple[float, str]:
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    output = (completed.stdout + "\n" + completed.stderr).strip()
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(command)}\n{output[-2000:]}"
        )
    return elapsed_ms, output


def _python_versions(python: Path, packages: tuple[str, ...]) -> dict[str, str]:
    code = (
        "import importlib.metadata as m, json, sys\n"
        "print(json.dumps({p: m.version(p) for p in sys.argv[1:]}))\n"
    )
    output = subprocess.check_output(
        [str(python), "-c", code, *packages], text=True, encoding="utf-8"
    )
    return json.loads(output)


def _node_version(package: str) -> str:
    manifest = NODE_ROOT / "node_modules" / package / "package.json"
    return json.loads(manifest.read_text(encoding="utf-8"))["version"]


def _browser_version(channel: str) -> str:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel=channel, headless=True)
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


def _git_revision() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _arms(channel: str, scratch: Path, only: tuple[str, ...]) -> dict[str, dict[str, object]]:
    """Command, environment, source and browser of every arm, for one browser channel.

    ``chromium`` is Playwright's bundled browser. Cypress and SeleniumBase cannot drive
    that build; on ``chromium`` they use their own default Chromium (Electron, system
    Chrome), recorded per arm. ``msedge`` and ``chrome`` put every arm on one browser.
    """
    common = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    common.pop("TESTENCE_BROWSER_CHANNEL", None)
    cypress_browser = {"chromium": "electron", "msedge": "edge", "chrome": "chrome"}[channel]
    seleniumbase_flag = {"chromium": "--chrome", "msedge": "--edge", "chrome": "--chrome"}[channel]
    sources = {
        "testence": HERE / "testence" / "test_flow.py",
        "playwright_test": NODE_ROOT / "competitive" / "playwright_flow.spec.mjs",
        "pytest_playwright": HERE / "pytest_playwright_arm" / "test_flow.py",
        "cypress": NODE_ROOT / "cypress" / "flow.cy.mjs",
        "seleniumbase": HERE / "seleniumbase_arm" / "test_flow.py",
    }
    arms: dict[str, dict[str, object]] = {
        "testence": {
            "command": [
                sys.executable,
                "-m",
                "pytest",
                str(sources["testence"]),
                "--testence-headless",
                "-q",
                "-p",
                "no:cacheprovider",
                "--rootdir",
                str(sources["testence"].parent),
            ],
            "env": {
                **common,
                "TESTENCE_BASE_URL": URL,
                "TESTENCE_AUTH": "none",
                "TESTENCE_BROWSER_CHANNEL": channel,
                "TESTENCE_RUNS_ROOT": str(scratch / "testence-runs"),
            },
            "cwd": ROOT,
            "browser": f"Playwright {channel}",
        },
        "playwright_test": {
            "command": [
                str(NODE),
                str(NODE_ROOT / "node_modules" / "@playwright" / "test" / "cli.js"),
                "test",
                "--config",
                str(NODE_ROOT / "competitive" / "playwright.config.mjs"),
            ],
            "env": {
                **common,
                "BENCH_BASE_URL": URL,
                "BENCH_CHANNEL": channel,
                "BENCH_ARTIFACT_DIR": str(scratch / "playwright-results"),
            },
            "cwd": ROOT,
            "browser": f"Playwright {channel}",
        },
        "pytest_playwright": {
            "command": [
                str(_venv_python("pytest-playwright")),
                "-m",
                "pytest",
                str(sources["pytest_playwright"]),
                "-q",
                "-p",
                "no:cacheprovider",
                "--rootdir",
                str(sources["pytest_playwright"].parent),
                "--base-url",
                URL,
                "--browser-channel",
                channel,
            ],
            "env": {**common, "PYTHONPATH": ""},
            "cwd": sources["pytest_playwright"].parent,
            "browser": f"Playwright {channel}",
        },
        "cypress": {
            "command": [
                str(NODE),
                str(NODE_ROOT / "node_modules" / "cypress" / "bin" / "cypress"),
                "run",
                "--config-file",
                "cypress/cypress.config.mjs",
                "--browser",
                cypress_browser,
                "--headless",
            ],
            "env": {
                **common,
                "BENCH_BASE_URL": URL,
                "BENCH_ARTIFACT_DIR": str(scratch / "cypress-results"),
            },
            "cwd": NODE_ROOT,
            "browser": f"Cypress {cypress_browser}",
        },
        "seleniumbase": {
            "command": [
                str(_venv_python("seleniumbase")),
                "-m",
                "pytest",
                str(sources["seleniumbase"]),
                "-q",
                "-p",
                "no:cacheprovider",
                "--rootdir",
                str(sources["seleniumbase"].parent),
                seleniumbase_flag,
                "--headless",
            ],
            "env": {**common, "PYTHONPATH": "", "BENCH_BASE_URL": URL},
            "cwd": sources["seleniumbase"].parent,
            "browser": f"SeleniumBase {seleniumbase_flag.lstrip('-')}",
        },
    }
    for name, arm in arms.items():
        arm["source"] = sources[name]
    return {name: arms[name] for name in only}


def _tool_versions(only: tuple[str, ...]) -> dict[str, object]:
    versions: dict[str, object] = {}
    if "testence" in only:
        versions["testence"] = {
            "python_playwright": importlib.metadata.version("playwright"),
            "pytest": importlib.metadata.version("pytest"),
        }
    if "playwright_test" in only:
        versions["playwright_test"] = {"@playwright/test": _node_version("@playwright/test")}
    if "pytest_playwright" in only:
        versions["pytest_playwright"] = _python_versions(
            _venv_python("pytest-playwright"), ("pytest", "pytest-playwright", "playwright")
        )
    if "cypress" in only:
        versions["cypress"] = {"cypress": _node_version("cypress")}
    if "seleniumbase" in only:
        versions["seleniumbase"] = _python_versions(
            _venv_python("seleniumbase"), ("pytest", "seleniumbase", "selenium")
        )
    return versions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=30)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--arms", default=",".join(ARMS), help="comma-separated subset")
    parser.add_argument(
        "--channel",
        choices=("chromium", "msedge", "chrome"),
        default="chromium",
        help="browser for every arm that can use it (see README)",
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "bench" / "results" / "competitive-replay.json"
    )
    args = parser.parse_args()
    if args.repeats < 3:
        raise SystemExit("use at least three measured repeats")
    only = tuple(arm.strip() for arm in args.arms.split(",") if arm.strip())
    unknown = sorted(set(only) - set(ARMS))
    if unknown or "testence" not in only:
        raise SystemExit(f"arms must include testence and come from {', '.join(ARMS)}")

    target = _start_target(PORT)
    try:
        with tempfile.TemporaryDirectory(prefix="testence-competitive-") as temp:
            arms = _arms(args.channel, Path(temp), only)
            for name, arm in arms.items():
                executable = Path(str(arm["command"][0]))  # type: ignore[index]
                if name in {"pytest_playwright", "seleniumbase"} and not executable.exists():
                    raise SystemExit(f"{name}: create {executable} as README.md describes")
            for name, arm in arms.items():
                for _ in range(args.warmups):
                    _run(arm["command"], arm["env"], arm["cwd"])  # type: ignore[arg-type]
            samples: dict[str, list[float]] = {name: [] for name in arms}
            order_log: list[list[str]] = []
            generator = random.Random(SEED)
            for round_number in range(1, args.repeats + 1):
                order = list(arms)
                generator.shuffle(order)
                order_log.append(order)
                for name in order:
                    arm = arms[name]
                    elapsed, _ = _run(arm["command"], arm["env"], arm["cwd"])  # type: ignore[arg-type]
                    samples[name].append(elapsed)
                print(
                    f"round {round_number}/{args.repeats}: "
                    + ", ".join(f"{name} {samples[name][-1]:.0f} ms" for name in order),
                    flush=True,
                )
            results = {
                name: {
                    **_summary(samples[name]),
                    "browser": arms[name]["browser"],
                    "source": _source_stats(arms[name]["source"]),  # type: ignore[arg-type]
                }
                for name in arms
            }
    finally:
        if target is not None:
            target.terminate()

    testence_median = float(results["testence"]["median_ms"])  # type: ignore[arg-type]
    derived = {
        f"testence_vs_{name}_median_ratio": round(
            testence_median / float(results[name]["median_ms"]),  # type: ignore[arg-type]
            3,
        )
        for name in results
        if name != "testence"
    }
    playwright_channel = "chromium" if args.channel == "chromium" else args.channel
    payload = {
        "schema": "testence/competitive-replay/2",
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "revision": _git_revision(),
        "scenario": "six intent-bearing steps on bench/target/index.html",
        "timing_boundary": (
            "fresh runner process; discovery, browser launch, test, reporting and shutdown; "
            "target startup excluded"
        ),
        "policy": {
            "warmups_per_arm": args.warmups,
            "measured_repeats_per_arm": args.repeats,
            "order": f"rounds, each arm once per round, shuffled with seed {SEED}",
            "workers": 1,
            "retries": 0,
            "tracing": "off",
            "video": "off",
            "channel": args.channel,
        },
        "environment": {
            "os": platform.platform(),
            "machine": platform.machine(),
            "logical_cpu_count": os.cpu_count(),
            "python": platform.python_version(),
            "node": subprocess.check_output([str(NODE), "--version"], text=True).strip(),
            "playwright_browser": f"{playwright_channel} {_browser_version(playwright_channel)}",
            "tools": _tool_versions(tuple(results)),
            "benchmark_revision": _fingerprint(
                [
                    Path(__file__),
                    ROOT / "bench" / "target" / "index.html",
                    NODE_ROOT / "competitive" / "playwright.config.mjs",
                    NODE_ROOT / "cypress" / "cypress.config.mjs",
                    *[Path(str(arm["source"])) for arm in arms.values()],
                ]
            ),
        },
        "rounds": order_log,
        "arms": results,
        "derived": derived,
        "authoring_note": (
            "source size is a transparent proxy only; elapsed authoring and review time are "
            "measured separately (docs/en/benchmark/competitive.md, authoring protocol)"
        ),
    }
    args.output.parent.mkdir(exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"arms": {k: v["median_ms"] for k, v in results.items()}, **derived}))


if __name__ == "__main__":
    main()
