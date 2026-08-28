"""E1 (Python arm): per-step driver latency over the synthetic target page.

Symmetric to e1_node.mjs — same page, same steps, same sample counts, headless
system Chrome (channel="chrome") in both arms. Steps are grouped into:
- "instant": DOM reacts synchronously -> measures pure driver round-trip overhead
- "async":   DOM reacts after 250 ms  -> measures auto-wait correctness (floor 250 ms)

E1 acceptance criterion: Python stays if instant-step p50 overhead versus Node is
below 15%.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ITERATIONS = 30
TARGET = (Path(__file__).parent / "target" / "index.html").resolve().as_uri()


def pctl(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    k = (len(ordered) - 1) * pct / 100
    lower = int(k)
    upper = min(lower + 1, len(ordered) - 1)
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * (k - lower), 2)


def main() -> None:
    samples: dict[str, list[float]] = {}

    def timed(label: str, fn) -> None:
        start = time.perf_counter()
        fn()
        samples.setdefault(label, []).append((time.perf_counter() - start) * 1000)

    with sync_playwright() as pw:
        t0 = time.perf_counter()
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        launch_ms = round((time.perf_counter() - t0) * 1000, 1)
        page.goto(TARGET)

        for i in range(1, ITERATIONS + 1):
            timed("click_instant", lambda: page.click("#inc"))
            timed("assert_instant",
                  lambda: expect(page.locator("#count")).to_have_text(str(i)))
            timed("fill_instant", lambda: page.fill("#name", f"user-{i}"))
            timed("click_add", lambda: page.click("#add"))
            timed("assert_row",
                  lambda: expect(page.locator("#list li").last).to_have_text(f"row-user-{i}"))
            timed("click_async", lambda: page.click("#load"))
            timed("assert_async",
                  lambda: expect(page.locator("#asyncout")).to_have_text(f"loaded-{i}",
                                                                         timeout=5000))
        browser.close()

    instant_labels = ["click_instant", "assert_instant", "fill_instant", "click_add",
                      "assert_row", "click_async"]
    instant = [v for label in instant_labels for v in samples[label]]
    result = {
        "arm": "python",
        "python": sys.version.split()[0],
        "iterations": ITERATIONS,
        "launch_ms": launch_ms,
        "per_step": {label: {"p50": pctl(vals, 50), "p95": pctl(vals, 95), "n": len(vals)}
                     for label, vals in samples.items()},
        "instant_all": {"p50": pctl(instant, 50), "p95": pctl(instant, 95), "n": len(instant)},
    }
    out = Path(__file__).parent / "results" / "e1_python.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
