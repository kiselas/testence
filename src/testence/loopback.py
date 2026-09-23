"""Loopback HTTP servers that start without a reverse DNS lookup.

``http.server.HTTPServer.server_bind`` resolves the bound address back to a host name
with ``socket.getfqdn`` only to fill ``server_name``, which nothing but CGI reads. On a
hosted macOS runner the first reverse lookup of ``127.0.0.1`` in a process takes 35 s
(later ones are cached), so every process that starts a stdlib server paid it: the
demo target, the test fixtures and the benchmark servers.

``python -m testence.loopback PORT [--directory DIR]`` replaces
``python -m http.server PORT --bind 127.0.0.1`` for serving static files.
"""

from __future__ import annotations

import argparse
import functools
import socketserver
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class LoopbackHTTPServer(ThreadingHTTPServer):
    """A ``ThreadingHTTPServer`` whose bind records the address without resolving it."""

    def server_bind(self) -> None:
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = str(host)
        self.server_port = int(port)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="serve a directory on 127.0.0.1")
    parser.add_argument("port", type=int)
    parser.add_argument("--directory", default=".")
    args = parser.parse_args(argv)
    handler = functools.partial(SimpleHTTPRequestHandler, directory=args.directory)
    with LoopbackHTTPServer(("127.0.0.1", args.port), handler) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()


__all__ = ["LoopbackHTTPServer", "main"]
