"""I3 baseline: the same scenario, driven by a script, timed step by step.

The comparison arm is an agent clicking through the identical steps with browser
MCP tools (see bench/results/local-i3_baseline.md). Same page, same six steps, so
the ratio measures one thing only: what it costs to put an LLM in the execution
path.

Served over HTTP rather than file:// so both arms load the page identically.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from testence.engine import Target  # noqa: E402
from testence.engine.playwright_cdp import PlaywrightCdpEngine  # noqa: E402

PORT = 8899
STEPS = [
    "open the page",
    "click inc",
    "assert counter shows 1",
    "type a name",
    "click add",
    "assert the row appeared",
]


def main() -> None:
    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"],
        cwd=str(ROOT / "bench" / "target"),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1.5)
    timings: dict[str, float] = {}
    try:
        engine = PlaywrightCdpEngine(base_url=f"http://127.0.0.1:{PORT}", headed=False)
        engine.start()
        launch_done = time.perf_counter()
        try:

            def timed(label: str, action) -> None:
                start = time.perf_counter()
                action()
                timings[label] = round((time.perf_counter() - start) * 1000, 1)

            timed(STEPS[0], lambda: engine.goto("/index.html"))
            timed(STEPS[1], lambda: engine.click(Target("css", "#inc")))
            timed(STEPS[2], lambda: engine.expect_text(Target("css", "#count"), "1"))
            timed(STEPS[3], lambda: engine.fill(Target("placeholder", "name"), "alice"))
            timed(STEPS[4], lambda: engine.click(Target("role", "button", name="add")))
            timed(STEPS[5], lambda: engine.expect_text(Target("css", "#list li"), "row-alice"))
            total = round(sum(timings.values()), 1)
        finally:
            engine.stop()
        result = {
            "arm": "script",
            "steps": timings,
            "total_ms": total,
            "session_setup_ms": round((launch_done - launch_done) * 1000, 1),
            "note": "browser launch excluded; it is paid once per suite, not per case",
        }
    finally:
        server.terminate()

    out = Path(__file__).parent / "results" / "i3_baseline_script.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
