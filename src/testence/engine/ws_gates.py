"""WebSocket gates: hold back server frames from the page, keep the socket open (ADR-0035).

A gate routes matching sockets through the driver with ``route_web_socket``. Client
frames pass untouched. Server frames pass while the gate is online; while it is
offline its drop rule decides. Only frames actually sent to the page are recorded,
so a dropped frame never reaches ``wait_for_ws``.
"""

from __future__ import annotations

import re
from typing import Any, Callable

PROTOCOLS = ("socket.io", "raw")

#: A drop rule sees one server frame (text or bytes) and says whether to hold it back.
DropRule = Callable[[Any], bool]


def glob_matcher(pattern: str | re.Pattern[str]) -> Callable[[str], bool]:
    """A URL matcher: a compiled regex searches, a glob matches the whole URL.

    In a glob ``**`` matches any characters and ``*`` any characters but ``/``;
    everything else is literal, including ``?``.
    """
    if isinstance(pattern, re.Pattern):
        return lambda url: pattern.search(url) is not None
    if not isinstance(pattern, str) or not pattern:
        raise ValueError("a WebSocket gate needs a URL glob or a compiled regex")
    parts = re.split(r"(\*\*|\*)", pattern)
    body = "".join(
        ".*" if part == "**" else "[^/]*" if part == "*" else re.escape(part) for part in parts
    )
    compiled = re.compile(body)
    return lambda url: compiled.fullmatch(url) is not None


def pattern_label(pattern: str | re.Pattern[str]) -> str:
    return pattern.pattern if isinstance(pattern, re.Pattern) else pattern


def socket_io_packet(payload: Any) -> tuple[str, int]:
    """Classify an engine.io/socket.io WebSocket frame.

    Returns ``(kind, attachments)``: ``event`` for ``42…``, ``binary_event`` for
    ``45…`` with the number of binary frames that follow it, ``binary_ack`` for
    ``46…`` likewise, ``binary`` for a binary frame, ``other`` for the rest (open,
    close, ping, pong, noop, connect, disconnect, acknowledgement, error).
    """
    if not isinstance(payload, str):
        return "binary", 0
    if payload.startswith("42"):
        return "event", 0
    if payload[:2] in ("45", "46"):
        head = re.match(r"(\d+)-", payload[2:])
        count = int(head.group(1)) if head else 0
        return ("binary_event" if payload[1] == "5" else "binary_ack"), count
    return "other", 0


class WsGate:
    """One gate. The engine owns it; the DSL wraps it in a recorded handle."""

    def __init__(
        self,
        pattern: str | re.Pattern[str],
        *,
        protocol: str,
        drop: DropRule | None,
        offline: bool,
        record_frame: Callable[[str, Any], None],
        claim_url: Callable[[str], None],
        settle: Callable[[int], None],
    ) -> None:
        if protocol not in PROTOCOLS:
            raise ValueError(
                f"WebSocket gate protocol must be one of {PROTOCOLS}, not {protocol!r}"
            )
        if drop is not None and not callable(drop):
            raise ValueError("drop must be a callable taking one server frame")
        self.pattern = pattern
        self.label = pattern_label(pattern)
        self.matches = glob_matcher(pattern)
        self.protocol = protocol
        self.drop = drop
        self.offline = offline
        self.active = True
        self.dropped = 0
        self.delivered = 0
        self.sockets = 0
        self._window = 0
        self._record_frame = record_frame
        self._claim_url = claim_url
        self._settle = settle

    def matches_url(self, url: str) -> bool:
        return self.active and self.matches(url)

    def handle(self, route: Any) -> None:
        """The ``route_web_socket`` handler: connect, forward, filter server frames."""
        if not self.active:
            # Playwright cannot unroute a WebSocket; a removed gate is a passthrough.
            route.connect_to_server()
            return
        url = str(route.url)
        self.sockets += 1
        self._claim_url(url)
        server = route.connect_to_server()
        held_attachments = [0]

        def from_server(message: Any) -> None:
            if self.active and self._holds(message, held_attachments):
                self.dropped += 1
                self._window += 1
                return
            route.send(message)
            if self.active:
                self.delivered += 1
                self._record_frame(url, message)

        server.on_message(from_server)

    def _holds(self, message: Any, held_attachments: list[int]) -> bool:
        kind, attachments = (
            socket_io_packet(message) if self.protocol == "socket.io" else ("frame", 0)
        )
        if kind == "binary" and held_attachments[0]:
            # Attachments follow the event they belong to, whatever the state now.
            held_attachments[0] -= 1
            return True
        if not self.offline:
            return False
        if self.drop is not None:
            return bool(self.drop(message))
        if self.protocol == "raw":
            return True
        if kind == "binary_event":
            held_attachments[0] = attachments
        return kind in ("event", "binary_event")

    def set_offline(self, offline: bool, drain_ms: int = 0) -> int:
        """Switch state after deciding queued frames under the current one.

        Returns how many frames were held back since the gate last went offline
        (0 when going offline).
        """
        if not self.active:
            raise RuntimeError(
                f"the WebSocket gate on {self.label} was removed with its browser context"
            )
        if type(drain_ms) is not int or drain_ms < 0:
            raise ValueError("drain_ms must be a non-negative integer")
        self._settle(drain_ms)
        held = self._window if self.offline and not offline else 0
        if offline and not self.offline:
            self._window = 0
        self.offline = offline
        return held

    def summary(self) -> dict[str, Any]:
        return {
            "pattern": self.label,
            "protocol": self.protocol,
            "custom_drop": self.drop is not None,
            "offline": self.offline,
            "sockets": self.sockets,
            "dropped": self.dropped,
            "delivered": self.delivered,
        }

    def deactivate(self) -> None:
        self.active = False
