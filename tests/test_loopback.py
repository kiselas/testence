from __future__ import annotations

import re
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from testence.loopback import LoopbackHTTPServer

ROOT = Path(__file__).resolve().parents[1]


class _Hello(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Length", "5")
        self.end_headers()
        self.wfile.write(b"hello")


def _no_reverse_lookup(monkeypatch):
    # On a hosted macOS runner the first reverse lookup of 127.0.0.1 takes 35 s.
    def refuse(*_args):
        raise AssertionError("reverse DNS lookup during server bind")

    monkeypatch.setattr(socket, "getfqdn", refuse)


def test_loopback_server_binds_and_serves_without_a_reverse_lookup(monkeypatch):
    _no_reverse_lookup(monkeypatch)
    server = LoopbackHTTPServer(("127.0.0.1", 0), _Hello)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/", timeout=5) as r:
            assert r.read() == b"hello"
        assert server.server_name == "127.0.0.1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_the_stdlib_server_does_the_reverse_lookup_this_module_avoids(monkeypatch):
    _no_reverse_lookup(monkeypatch)
    with pytest.raises(AssertionError, match="reverse DNS lookup"):
        ThreadingHTTPServer(("127.0.0.1", 0), _Hello)  # loopback-exempt: the control case


def test_no_stdlib_server_is_constructed_in_repository_code():
    # A plain http.server bind costs 35 s per process on macOS; keep it out.
    pattern = re.compile(r"(?<![A-Za-z_])(?:Threading)?HTTPServer\(|\"-m\",\s*\"http\.server\"")
    offenders = [
        f"{path.relative_to(ROOT).as_posix()}:{number}"
        for folder in ("src", "tests", "bench", "scripts", "examples")
        for path in sorted((ROOT / folder).rglob("*.py"))
        if "node_modules" not in path.parts
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if pattern.search(line) and "loopback-exempt" not in line
    ]
    assert offenders == []


def test_module_entry_point_serves_a_directory(tmp_path: Path):
    (tmp_path / "index.html").write_bytes(b"<p>static</p>")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    process = subprocess.Popen(
        [sys.executable, "-m", "testence.loopback", str(port), "--directory", str(tmp_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 10
        while True:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/index.html", timeout=2) as r:
                    assert r.read() == b"<p>static</p>"
                break
            except OSError:
                if time.monotonic() > deadline or process.poll() is not None:
                    raise
                time.sleep(0.05)
    finally:
        process.terminate()
        process.wait(timeout=10)
