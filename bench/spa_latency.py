"""Latency probe for SPA behavior that punishes generic waits.

The synthetic page models three common React traits without downloading React:

- the root mounts asynchronously and initially renders only a controlled input;
- the input updates application state from the ``input`` event;
- background API polling means the page never reaches ``networkidle``.

The probe compares raw engine fill with the public Actions path, whose extra cost
includes evidence and fingerprint capture. It is a diagnostic snapshot, not a
cross-machine product claim.
"""

from __future__ import annotations

import json
import platform
import statistics
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from testence.dsl import Actions  # noqa: E402
from testence.engine import Target  # noqa: E402
from testence.engine.playwright_cdp import PlaywrightCdpEngine  # noqa: E402
from testence.evidence import EvidenceWriter  # noqa: E402
from testence.loopback import LoopbackHTTPServer  # noqa: E402

ITERATIONS = 20
NAME = Target("css", "#name")
SAVE = Target("role", "button", name="Save")

PAGE = """<!doctype html><html><body><div id="root"></div><script>
setTimeout(() => {
  root.innerHTML = '<input id="name" aria-label="Name"><output id="mirror"></output>'
    + '<button id="save">Save</button>';
  document.getElementById('name').addEventListener('input', event => {
    document.getElementById('mirror').textContent = event.target.value;
  });
  document.getElementById('save').addEventListener('click', () => {
    fetch('/api/save', {method: 'POST', body: document.getElementById('name').value});
  });
}, 20);
setInterval(() => fetch('/api/pulse').catch(() => {}), 100);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args: object) -> None:
        pass

    def do_GET(self) -> None:
        if self.path == "/":
            payload, content_type = PAGE.encode(), "text/html; charset=utf-8"
        else:
            payload, content_type = b"{}", "application/json"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        payload = b'{"saved":true}'
        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def distribution(values: list[float]) -> dict[str, float | int]:
    ordered = sorted(values)
    p95 = ordered[max(0, int(len(ordered) * 0.95) - 1)]
    return {"p50": round(statistics.median(ordered), 2), "p95": round(p95, 2), "n": len(values)}


def timed(call) -> float:
    started = time.perf_counter()
    call()
    return (time.perf_counter() - started) * 1000


def main() -> None:
    server = LoopbackHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    temp_root = ROOT / ".tmp"
    temp_root.mkdir(exist_ok=True)
    engine = PlaywrightCdpEngine(
        base_url=f"http://{host}:{port}",
        headed=False,
        api_prefix="/api/",
    )
    try:
        engine.start()
        goto_ms = timed(lambda: engine.goto("/"))
        raw = [timed(lambda i=i: engine.fill(NAME, f"raw-{i}")) for i in range(ITERATIONS)]
        raw_fast = [
            timed(lambda i=i: engine.fill(NAME, f"raw-fast-{i}", fast=True))
            for i in range(ITERATIONS)
        ]
        with tempfile.TemporaryDirectory(dir=temp_root) as directory:
            writer = EvidenceWriter(Path(directory), worker="")
            actions = Actions(engine, writer, "spa-latency")
            public = [
                timed(lambda i=i: actions.fill(NAME, f"public-{i}", intent="update name"))
                for i in range(ITERATIONS)
            ]
            public_fast = [
                timed(
                    lambda i=i: actions.fill(
                        NAME,
                        f"public-fast-{i}",
                        intent="update ready name",
                        fast=True,
                    )
                )
                for i in range(ITERATIONS)
            ]
            writer.close()
        mark = engine.net_mark()
        engine.click(SAVE)
        response_ms = timed(
            lambda: engine.wait_for_response("/api/save", method="POST", since=mark, timeout_ms=750)
        )
        settle_ms = timed(lambda: engine.settle(750))
        result = {
            "scenario": "async SPA root + controlled input + API polling",
            "environment": {
                "os": platform.platform(),
                "python": platform.python_version(),
                "playwright": version("playwright"),
            },
            "iterations": ITERATIONS,
            "goto_ms": round(goto_ms, 2),
            "engine_fill_ms": distribution(raw),
            "engine_fast_fill_ms": distribution(raw_fast),
            "actions_fill_ms": distribution(public),
            "actions_fast_fill_ms": distribution(public_fast),
            "mutation_response_ms": round(response_ms, 2),
            "settle_750_ms": round(settle_ms, 2),
            "note": "single-host diagnostic; compare before/after from the same environment",
        }
        print(json.dumps(result, indent=2))
    finally:
        engine.stop()
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
