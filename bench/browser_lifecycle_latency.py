"""Compare fresh browsers and explicit worker reuse with identical context assertions.

Diagnostic timings are not a host-independent budget. --check verifies execution,
fresh-context assertions and exact browser launch/close counts in both arms.
"""

from __future__ import annotations

import argparse
import json
import tempfile
import threading
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

from testence.debug import debug
from testence.evidence.reader import read_run_ledgers
from testence.loopback import LoopbackHTTPServer


def benchmark(cases: int, workers: int) -> dict[str, Any]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            pass

        def do_GET(self) -> None:
            body = b"<h1>Clean context</h1>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = LoopbackHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="testence-browser-lifecycle-") as directory:
            project = Path(directory)
            config = {
                "base_url": f"http://127.0.0.1:{server.server_port}",
                "auth": "none",
                "extra": {
                    "parallel": {
                        "enabled": True,
                        "accounts": "isolated",
                        "cleanup": "asserted-absence",
                    }
                },
            }
            (project / "testence.json").write_text(json.dumps(config), encoding="utf-8")
            (project / "test_context.py").write_text(
                """import pytest
from pathlib import Path
from testence.engine import Target
@pytest.mark.testence_parallel
@pytest.mark.parametrize('case',range(CASES))
def test_clean_context(case,ex,testence_namespace):
 ex.goto('/')
 assert ex.engine.eval_js("() => [document.cookie,localStorage.getItem('leak'),sessionStorage.getItem('leak'),window.leak || null]") == ['',None,None,None]
 ex.expect_text(Target('role','heading',name='Clean context'),'Clean context')
 ex.engine.eval_js("() => {document.cookie='leak=yes';localStorage.setItem('leak','yes');sessionStorage.setItem('leak','yes');window.leak='yes'}")
 marker=Path(testence_namespace.marker)
 marker.write_text(str(case))
 assert marker.read_text()==str(case)
 marker.unlink()
 assert not marker.exists()
""".replace("CASES", str(cases)),
                encoding="utf-8",
            )
            arms = {}
            for label, reuse in [("fresh", False), ("reuse", True)]:
                result = debug(
                    project,
                    "test_context.py",
                    allow_multiple=True,
                    workers=workers,
                    browser_reuse=reuse,
                    timeout_s=240,
                )
                events = read_run_ledgers(Path(result["run_dir"]))
                starts = sum(e.get("lifecycle_phase") == "browser.launch" for e in events)
                closes = sum(e.get("lifecycle_phase") == "browser.process_close" for e in events)
                expected = min(workers, cases) if reuse else cases
                arms[label] = {
                    "run_id": result["run_id"],
                    "elapsed_ms": result["elapsed_ms"],
                    "collection_ms": result["collection_ms"],
                    "exit_code": result["exit_code"],
                    "execution": result["summary"]["execution"],
                    "browser_launches": starts,
                    "browser_closes": closes,
                    "expected_browsers": expected,
                    "phases": result["phases"],
                    "verified": result["exit_code"] == 0
                    and result["summary"]["execution"] == {"passed": cases}
                    and starts == closes == expected,
                }
            return {
                "scenario": "identical fresh-context UI/storage/namespace checks",
                "cases": cases,
                "workers": workers,
                "arms": arms,
                "observed_wall_reduction_percent": round(
                    (1 - arms["reuse"]["elapsed_ms"] / arms["fresh"]["elapsed_ms"]) * 100, 1
                ),
                "note": "single-host diagnostic; no performance threshold or external pilot claim",
            }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=int, default=8)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.cases <= 64 or not 1 <= args.workers <= 16:
        parser.error("cases must be 1..64 and workers 1..16")
    result = benchmark(args.cases, args.workers)
    print(json.dumps(result, indent=2))
    if args.check and not all(arm["verified"] for arm in result["arms"].values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
