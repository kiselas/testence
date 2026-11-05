"""Measure the kit methods against the real Koobiq conformance stand.

One browser, one fresh page load per repeat, every kit method timed around its call.
The question is the one ``bench/react_latency.py`` answers for primitives: does a kit
method cost what its steps cost, or does it hide a wait? ``--check`` applies the broad
ceilings in ``bench/budgets/kits_latency.json``; they catch timeout-shaped regressions
(a method that waits out a budget), not millisecond noise.

    .venv/Scripts/python bench/kits_latency.py
    .venv/Scripts/python bench/kits_latency.py --repeats 5 --check
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import tempfile
import time
from collections.abc import Callable
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
STAND = ROOT / "bench" / "sut" / "koobiq"
DEFAULT_BUDGET = ROOT / "bench" / "budgets" / "kits_latency.json"

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "bench"))
sys.path.insert(0, str(STAND))

from react_latency import distribution, evaluate_budget  # noqa: E402
from server import serve  # noqa: E402

from testence.dsl import Actions  # noqa: E402
from testence.engine import Target  # noqa: E402
from testence.engine.playwright_cdp import PlaywrightCdpEngine  # noqa: E402
from testence.evidence import EvidenceWriter  # noqa: E402
from testence.kits import koobiq, react_aria, react_select, recognize, xyflow  # noqa: E402


def _scenario(ex: Actions) -> list[tuple[str, Callable[[], Any]]]:
    """Each kit method once, in an order that leaves the page usable for the next."""
    panel = koobiq.side_panel(ex, "Edit router")
    toasts = koobiq.toasts(ex)
    targets = react_select.multi(ex, "Targets")
    routers = koobiq.table(ex, "Routers")
    marks: dict[str, koobiq.ToastMark] = {}

    def toast_round_trip() -> None:
        marks["before"] = toasts.mark()
        ex.click(react_aria.button("Show toast"), intent="save")
        toasts.expect_new(marks["before"], "Router saved", status="success").dismiss()

    def open_panel() -> None:
        ex.click(react_aria.button("Open panel"), intent="open the side panel")
        panel.wait_open()

    return [
        ("recognize_components", lambda: ex.engine.eval_js(recognize.script())),
        ("koobiq.select.choose", lambda: koobiq.select(ex, "Mode").choose("Safe")),
        ("koobiq.checkbox.check", lambda: koobiq.checkbox(ex, "Accept terms").check()),
        ("koobiq.tabs.select", lambda: koobiq.tabs(ex, "Router views").select("Routes")),
        ("react_aria.tooltip.open", lambda: koobiq.tooltip(ex, react_aria.button("Help")).open()),
        ("koobiq.table.select_row", lambda: routers.select_row("router-two")),
        (
            "koobiq.table.row_menu.choose",
            lambda: routers.row_menu("router-one", "Actions of router-one").choose("Edit"),
        ),
        ("react_select.multi.state", targets.state),
        ("react_select.multi.pick", lambda: targets.pick("alpha.example.test")),
        ("react_select.multi.remove", lambda: targets.remove("alpha.example.test")),
        ("koobiq.toast.new_and_dismiss", toast_round_trip),
        ("koobiq.side_panel.open_and_wait", open_panel),
        (
            "koobiq.number_field.set",
            lambda: panel.number_field("VLAN", hint="from 1 to 4094").set(42),
        ),
        ("koobiq.side_panel.close", panel.close),
        ("xyflow.node.open", lambda: xyflow.node(ex, "h1", kind="host").open()),
        ("xyflow.node.action", lambda: xyflow.node(ex, "h2", kind="host").action("Copy")),
    ]


def run(repeats: int) -> dict[str, Any]:
    samples: dict[str, list[float]] = {}
    with serve() as url, tempfile.TemporaryDirectory(prefix="kits-latency-") as scratch:
        engine = PlaywrightCdpEngine(url, headed=False, timeout_ms=5_000)
        started = time.perf_counter()
        engine.start()
        launch_ms = (time.perf_counter() - started) * 1000
        try:
            for repeat in range(repeats):
                engine.reset_taps()
                engine.goto("/index.html")
                engine.wait_for_count(Target("role", "heading", name="Koobiq conformance stand"))
                writer = EvidenceWriter(Path(scratch) / f"r{repeat}")
                ex = Actions(engine, writer, f"kits-latency-{repeat}")
                for name, method in _scenario(ex):
                    began = time.perf_counter()
                    method()
                    samples.setdefault(name.replace(".", "_"), []).append(
                        (time.perf_counter() - began) * 1000
                    )
                writer.close()
        finally:
            engine.stop()
    built = json.loads((STAND / "dist" / "stand.json").read_text(encoding="utf-8"))
    return {
        "schema": "testence/kits-latency/1",
        "scenario": "kit methods on the Koobiq conformance stand, one page load per repeat",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "os": platform.platform(),
            "python": platform.python_version(),
            "playwright": version("playwright"),
            "browser_channel": engine.browser_channel,
            "stand": built["packages"],
        },
        "repeats": repeats,
        "launch_ms": round(launch_ms, 2),
        # Keys are method paths with "_" for ".": a budget addresses them by dotted path.
        "methods": {name: distribution(values) for name, values in samples.items()},
        "samples_ms": {name: [round(v, 1) for v in values] for name, values in samples.items()},
        "note": (
            "In-process wall time of each kit method, including its own checks. "
            "Broad budgets detect hidden waits, not cross-machine microbenchmarks."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--budget", type=Path, default=DEFAULT_BUDGET)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.repeats < 1:
        raise SystemExit("--repeats must be at least 1")
    result = run(args.repeats)
    if args.check:
        budget = json.loads(args.budget.read_text(encoding="utf-8"))
        result["budget"] = {
            "path": str(args.budget.relative_to(ROOT)) if args.budget.is_relative_to(ROOT) else "",
            "violations": evaluate_budget(result, budget),
        }
    rendered = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    if args.check and result["budget"]["violations"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
