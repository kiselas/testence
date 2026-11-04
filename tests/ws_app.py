"""A loopback live-update application with a real WebSocket endpoint (stdlib only).

The page at ``/`` opens ``/socket.io/?EIO=4&transport=websocket`` and speaks the slice
of engine.io/socket.io a gate has to understand: the server opens with ``0{...}``,
pings with ``2`` and the page answers ``3``; events are ``42[...]`` (or ``42/ns,[...]``).
Every frame the page receives is appended to ``#log`` and to ``window.frames``, so a
test can read what reached the page. ``/raw`` opens a plain socket on ``/raw-ws``.

The server records what it receives from pages, so a test can prove that client frames
and pong answers still reach it while server events are held back.
"""

from __future__ import annotations

import base64
import hashlib
import socket
import struct
import threading
from http.server import BaseHTTPRequestHandler
from typing import Any

from testence.loopback import LoopbackHTTPServer

_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

PAGE = """<!doctype html><meta charset=utf-8><title>live</title>
<ul id=log></ul>
<script>
window.received = [];
const url = location.origin.replace('http', 'ws') + '%(path)s';
const ws = new WebSocket(url);
window.socketState = 'connecting';
ws.onopen = () => { window.socketState = 'open'; };
ws.onclose = () => { window.socketState = 'closed'; };
ws.onmessage = (event) => {
  window.received.push(event.data);
  if (event.data === '2') { ws.send('3'); }
  const item = document.createElement('li');
  item.textContent = event.data;
  document.getElementById('log').appendChild(item);
};
window.say = (text) => ws.send(text);
</script>
"""


class _Client:
    def __init__(self, sock: socket.socket, path: str) -> None:
        self.sock = sock
        self.path = path
        self.lock = threading.Lock()
        self.open = True

    def send(self, text: str) -> None:
        data = text.encode("utf-8")
        header = bytearray([0x81])
        if len(data) < 126:
            header.append(len(data))
        elif len(data) < 1 << 16:
            header.append(126)
            header += struct.pack("!H", len(data))
        else:
            header.append(127)
            header += struct.pack("!Q", len(data))
        with self.lock:
            if self.open:
                try:
                    self.sock.sendall(bytes(header) + data)
                except OSError:
                    self.open = False


def _read_exact(sock: socket.socket, size: int) -> bytes:
    chunks = b""
    while len(chunks) < size:
        chunk = sock.recv(size - len(chunks))
        if not chunk:
            raise ConnectionError("socket closed")
        chunks += chunk
    return chunks


def _read_frame(sock: socket.socket) -> tuple[int, bytes]:
    first, second = _read_exact(sock, 2)
    opcode = first & 0x0F
    length = second & 0x7F
    if length == 126:
        length = struct.unpack("!H", _read_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", _read_exact(sock, 8))[0]
    mask = _read_exact(sock, 4) if second & 0x80 else b"\0\0\0\0"
    payload = bytes(b ^ mask[i % 4] for i, b in enumerate(_read_exact(sock, length)))
    return opcode, payload


class WsApp:
    """``with WsApp() as app: app.base_url``; ``app.push(text)`` to every open socket."""

    def __init__(self) -> None:
        self.clients: list[_Client] = []
        self.received: list[str] = []
        self.connections = 0
        self._changed = threading.Condition()
        app = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args: Any) -> None:
                pass

            def do_GET(self) -> None:  # noqa: N802
                if self.headers.get("Upgrade", "").lower() == "websocket":
                    app._serve_socket(self)
                    return
                path = {"/": "/socket.io/?EIO=4&transport=websocket", "/raw": "/raw-ws"}.get(
                    self.path.split("?")[0]
                )
                if path is None:
                    self.send_error(404)
                    return
                body = (PAGE % {"path": path}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self._server = LoopbackHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def __enter__(self) -> WsApp:
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        for client in list(self.clients):
            client.open = False
            try:
                client.sock.close()
            except OSError:
                pass
        self._server.shutdown()
        self._server.server_close()

    def _serve_socket(self, handler: BaseHTTPRequestHandler) -> None:
        key = handler.headers["Sec-WebSocket-Key"]
        accept = base64.b64encode(hashlib.sha1((key + _GUID).encode()).digest()).decode()
        handler.send_response(101)
        handler.send_header("Upgrade", "websocket")
        handler.send_header("Connection", "Upgrade")
        handler.send_header("Sec-WebSocket-Accept", accept)
        handler.end_headers()
        handler.wfile.flush()
        client = _Client(handler.connection, handler.path)
        with self._changed:
            self.clients.append(client)
            self.connections += 1
            self._changed.notify_all()
        if handler.path.startswith("/socket.io/"):
            client.send('0{"sid":"s1","pingInterval":25000,"pingTimeout":20000}')
        try:
            while client.open:
                opcode, payload = _read_frame(handler.connection)
                if opcode == 0x8:
                    break
                if opcode == 0x9:
                    continue
                with self._changed:
                    self.received.append(payload.decode("utf-8", "replace"))
                    self._changed.notify_all()
        except (ConnectionError, OSError):
            pass
        finally:
            client.open = False
            with self._changed:
                if client in self.clients:
                    self.clients.remove(client)
                self._changed.notify_all()
        handler.close_connection = True

    def push(self, text: str) -> int:
        """Send ``text`` to every open socket; return how many got it."""
        with self._changed:
            clients = [client for client in self.clients if client.open]
        for client in clients:
            client.send(text)
        return len(clients)

    def wait_for_clients(self, count: int, timeout: float = 10.0) -> None:
        with self._changed:
            if not self._changed.wait_for(lambda: len(self.clients) >= count, timeout):
                raise TimeoutError(f"{len(self.clients)} sockets open, expected {count}")

    def wait_received(self, text: str, timeout: float = 10.0) -> None:
        with self._changed:
            if not self._changed.wait_for(lambda: text in self.received, timeout):
                raise TimeoutError(f"server never received {text!r}: {self.received}")
