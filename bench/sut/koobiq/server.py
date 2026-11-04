"""Serve the built Koobiq conformance stand on 127.0.0.1.

``python bench/sut/koobiq/server.py --port 8810`` serves ``dist/``; tests and
``bench/kits_latency.py`` use :func:`serve`, which picks a free port.

``TESTENCE_KOOBIQ_STAND=<dir>`` serves another build of the same stand instead, such
as one made against a newer Koobiq release (see README.md, "Checking a new release").
"""

from __future__ import annotations

import argparse
import functools
import os
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
REPO = ROOT.parent.parent.parent
sys.path.insert(0, str(REPO / "src"))

from testence.loopback import LoopbackHTTPServer  # noqa: E402


class _Quiet(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return


def build_dir() -> Path:
    """The build to serve: ``TESTENCE_KOOBIQ_STAND`` when set, else ``dist/``."""
    override = os.environ.get("TESTENCE_KOOBIQ_STAND", "").strip()
    return Path(override) if override else DIST


def _require_build() -> Path:
    directory = build_dir()
    if (directory / "index.html").is_file():
        return directory
    raise SystemExit(
        f"no Koobiq stand build in {directory}. Run:\n"
        "  npm ci --prefix bench/sut/koobiq && npm run build --prefix bench/sut/koobiq"
    )


@contextmanager
def serve(port: int = 0) -> Iterator[str]:
    """Serve ``dist/`` in a background thread; yields the base URL."""
    directory = _require_build()
    handler = functools.partial(_Quiet, directory=str(directory))
    server = LoopbackHTTPServer(("127.0.0.1", port), handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, bound = server.server_address[:2]
        yield f"http://{host}:{bound}"
    finally:
        server.shutdown()
        server.server_close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8810)
    args = parser.parse_args(argv)
    with serve(args.port) as url:
        print(url, flush=True)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
