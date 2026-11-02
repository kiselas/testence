"""``ex.ws_gate``: a tab that misses server pushes on purpose, with provenance (ADR-0034)."""

from __future__ import annotations

import json
import re
import time
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from testence.dsl import Actions
from testence.dsl.steps import StepFailed
from testence.engine import UnsupportedCapability
from testence.engine.native_routes import NativeRoutes
from testence.engine.playwright_cdp import PlaywrightCdpEngine
from testence.engine.ws_gates import WsGate, glob_matcher, socket_io_packet
from testence.evidence import EvidenceWriter
from tests.ws_app import WsApp

OPEN = '0{"sid":"s1","pingInterval":25000,"pingTimeout":20000}'

# -- codec, matcher and gate logic without a browser ---------------------------------


@pytest.mark.parametrize(
    ("frame", "kind", "attachments"),
    [
        ('42["changed",{"id":1}]', "event", 0),
        ('42/admin,["changed"]', "event", 0),
        ('4217["changed"]', "event", 0),
        ('451-["file",{"_placeholder":true,"num":0}]', "binary_event", 1),
        ('452-/admin,["files"]', "binary_event", 2),
        ('461-12[{"_placeholder":true,"num":0}]', "binary_ack", 1),
        ('4312["ok"]', "other", 0),
        ("40", "other", 0),
        ('40{"sid":"x"}', "other", 0),
        ("41", "other", 0),
        ('44{"message":"denied"}', "other", 0),
        (OPEN, "other", 0),
        ("2", "other", 0),
        ("3", "other", 0),
        ("6", "other", 0),
        (b"\x01\x02", "binary", 0),
    ],
)
def test_socket_io_frames_are_classified(frame, kind, attachments):
    assert socket_io_packet(frame) == (kind, attachments)


@pytest.mark.parametrize(
    ("pattern", "url", "matches"),
    [
        ("**/socket.io/**", "ws://h:1/socket.io/?EIO=4&transport=websocket", True),
        ("**/socket.io/**", "ws://h:1/raw-ws", False),
        ("ws://h:1/*", "ws://h:1/raw-ws", True),
        ("ws://h:1/*", "ws://h:1/a/b", False),
        ("ws://h:1/raw?", "ws://h:1/raw-", False),
        (re.compile(r"/socket\.io/"), "wss://h/socket.io/?EIO=4", True),
        (re.compile(r"/socket\.io/"), "wss://h/live", False),
    ],
)
def test_globs_match_whole_urls_and_regexes_search(pattern, url, matches):
    assert glob_matcher(pattern)(url) is matches


def test_an_empty_or_unknown_pattern_is_refused():
    with pytest.raises(ValueError, match="URL glob"):
        glob_matcher("")
    with pytest.raises(ValueError, match="protocol"):
        _gate(protocol="stomp")


class _Server:
    def __init__(self) -> None:
        self.handler: Callable[[Any], None] | None = None

    def on_message(self, handler: Callable[[Any], None]) -> None:
        self.handler = handler


class _Route:
    def __init__(self, url: str = "ws://h/socket.io/?EIO=4") -> None:
        self.url = url
        self.server = _Server()
        self.to_page: list[Any] = []
        self.connected = 0

    def connect_to_server(self) -> _Server:
        self.connected += 1
        return self.server

    def send(self, message: Any) -> None:
        self.to_page.append(message)

    def push(self, *frames: Any) -> None:
        for frame in frames:
            assert self.server.handler is not None
            self.server.handler(frame)


def _gate(**options: Any) -> tuple[WsGate, list[tuple[str, Any]], list[int], set[str]]:
    recorded: list[tuple[str, Any]] = []
    settles: list[int] = []
    owned: set[str] = set()
    settings = {"protocol": "socket.io", "drop": None, "offline": False, **options}
    gate = WsGate(
        "**/socket.io/**",
        record_frame=lambda url, frame: recorded.append((url, frame)),
        claim_url=owned.add,
        settle=settles.append,
        **settings,
    )
    return gate, recorded, settles, owned


def test_offline_socket_io_holds_events_and_keeps_the_connection_alive():
    gate, recorded, settles, owned = _gate()
    route = _Route()
    gate.handle(route)
    assert owned == {route.url}
    route.push(OPEN, "40", '42["a"]')
    gate.set_offline(True)
    route.push('42["b"]', "2", "3", '4312["ack"]', '451-["f",{"_placeholder":true}]', b"\x00")
    route.push('42/ns,["c"]', "41")
    held = gate.set_offline(False)
    route.push('42["d"]')
    assert route.to_page == [OPEN, "40", '42["a"]', "2", "3", '4312["ack"]', "41", '42["d"]']
    assert [frame for _, frame in recorded] == route.to_page
    assert (held, gate.dropped, gate.delivered, gate.sockets) == (4, 4, 8, 1)
    assert settles == [0, 0]


def test_attachments_of_a_delivered_binary_event_are_delivered():
    gate, _, _, _ = _gate()
    route = _Route()
    gate.handle(route)
    route.push('451-["f",{"_placeholder":true}]')
    gate.set_offline(True)
    route.push(b"\x00", '42["x"]')
    assert route.to_page == ['451-["f",{"_placeholder":true}]', b"\x00"]


def test_raw_holds_every_server_frame_and_drop_replaces_the_rule():
    raw, _, _, _ = _gate(protocol="raw", offline=True)
    route = _Route("ws://h/raw-ws")
    raw.handle(route)
    route.push("hello", "2", b"\x01")
    assert route.to_page == [] and raw.dropped == 3

    custom, _, _, _ = _gate(drop=lambda frame: "secret" in frame, offline=True)
    route = _Route()
    custom.handle(route)
    route.push('42["secret"]', '42["public"]')
    assert route.to_page == ['42["public"]']


def test_the_window_count_restarts_at_each_offline_and_drain_is_checked():
    gate, _, settles, _ = _gate()
    route = _Route()
    gate.handle(route)
    gate.set_offline(True)
    route.push('42["a"]', '42["b"]')
    assert gate.set_offline(False) == 2
    gate.set_offline(True, drain_ms=150)
    route.push('42["c"]')
    assert gate.set_offline(False) == 1
    assert gate.dropped == 3 and settles == [0, 0, 150, 0]
    with pytest.raises(ValueError, match="drain_ms"):
        gate.set_offline(True, drain_ms=-1)


def test_a_removed_gate_is_a_plain_passthrough_and_refuses_switching():
    gate, recorded, _, owned = _gate(offline=True)
    gate.deactivate()
    route = _Route()
    gate.handle(route)
    assert route.connected == 1 and route.server.handler is None and not owned
    with pytest.raises(RuntimeError, match="removed with its browser context"):
        gate.set_offline(False)
    assert not recorded


class _WsOwner:
    def __init__(self) -> None:
        self.pages: list[Any] = []
        self.registered: list[tuple[Any, Any]] = []

    def route(self, url, handler, **kwargs):
        pass

    def unroute(self, url, handler=None):
        pass

    def route_web_socket(self, url, handler):
        self.registered.append((url, handler))

    def on(self, name, callback):
        pass

    def remove_listener(self, name, callback):
        pass


def test_native_websocket_routes_are_observed_until_close():
    owner = _WsOwner()
    original = owner.route_web_socket
    registered: list[Any] = []
    routed: list[Any] = []
    handled: list[Any] = []
    watcher = NativeRoutes(
        lambda request, outcome: None,
        lambda page: None,
        on_ws_register=registered.append,
        on_ws_route=routed.append,
    )
    watcher.install(owner)
    owner.route_web_socket("**/live", handled.append)
    builtin = SimpleNamespace(_testence_builtin_gate=True)
    owner.route_web_socket("**/gate", builtin)
    assert registered == ["**/live"]
    (url, bridge), (_, kept) = owner.registered
    assert kept is builtin
    bridge("socket-1")
    assert routed == ["socket-1"] and handled == ["socket-1"]
    watcher.close()
    assert owner.route_web_socket == original
    bridge("socket-2")
    assert routed == ["socket-1"] and handled == ["socket-1", "socket-2"]


def test_an_engine_without_the_capability_refuses_before_anything_runs():
    class Plain:
        def capabilities(self) -> frozenset[str]:
            return frozenset({"browser.navigation"})

    actions = Actions(Plain(), SimpleNamespace(emit=lambda *a, **k: None), "t")  # type: ignore[arg-type]
    with pytest.raises(UnsupportedCapability, match="browser.websocket_mock"):
        actions.ws_gate("**/socket.io/**")


# -- live: a real browser against a real WebSocket server ----------------------------


def _events(writer: EvidenceWriter, kind: str = "websocket.gated") -> list[dict[str, Any]]:
    lines = writer.path.read_text(encoding="utf-8").splitlines()
    return [event for event in map(json.loads, lines) if event["kind"] == kind]


def _until(page: Any, condition: Callable[[], bool], what: str, timeout_s: float = 10.0) -> None:
    """Wait inside browser calls, so route callbacks keep being dispatched."""
    deadline = time.monotonic() + timeout_s
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError(f"timed out waiting for {what}")
        page.wait_for_timeout(20)


def _received(page: Any) -> list[str]:
    return list(page.evaluate("window.received"))


def _payloads(engine: PlaywrightCdpEngine) -> list[str]:
    return [frame["payload"] for frame in engine.ws_log()]


@pytest.fixture
def app():
    with WsApp() as server:
        yield server


@pytest.fixture
def engine():
    eng = PlaywrightCdpEngine(headed=False, debug_port=0)
    eng.start()
    yield eng
    eng.stop()


def _open(engine: PlaywrightCdpEngine, app: WsApp, path: str = "/") -> Any:
    engine.goto(app.base_url + path)
    page = engine.native_page()
    _until(page, lambda: len(app.clients) >= 1, "the socket to connect")
    if path == "/":
        _until(page, lambda: OPEN in _received(page), "the engine.io open packet")
    return page


def test_an_offline_tab_misses_events_while_pings_and_its_own_frames_flow(engine, app, tmp_path):
    with EvidenceWriter(tmp_path, worker="") as writer:
        ex = Actions(engine, writer, "gate")
        gate = ex.ws_gate("**/socket.io/**")
        page = _open(engine, app)
        app.push('42["first"]')
        _until(page, lambda: '42["first"]' in _received(page), "an online event")

        gate.go_offline()
        mark = engine.ws_mark()
        app.push('42["missed"]')
        app.push("2")
        _until(page, lambda: "3" in app.received, "the pong of the page")
        page.evaluate("window.say('42[\"mine\"]')")
        _until(page, lambda: '42["mine"]' in app.received, "a frame of the page")
        assert '42["missed"]' not in _received(page)
        assert engine.wait_for_ws("missed", since=mark, timeout_ms=200) is None
        assert page.evaluate("window.socketState") == "open"

        assert gate.go_online() == 1
        app.push('42["after"]')
        _until(page, lambda: '42["after"]' in _received(page), "an event after going online")
        assert engine.wait_for_ws("after", since=mark, timeout_ms=1000) is not None
        assert _received(page) == [OPEN, '42["first"]', "2", '42["after"]']
        assert _payloads(engine) == _received(page)
        assert app.connections == 1
        ex._finish_ws_gates()
        events = _events(writer)

    assert [event["action"] for event in events] == ["installed", "offline", "online", "summary"]
    assert events[0]["pattern"] == "**/socket.io/**" and events[0]["protocol"] == "socket.io"
    assert events[2]["dropped"] == 1
    assert {k: events[3][k] for k in ("sockets", "dropped", "delivered", "offline")} == {
        "sockets": 1,
        "dropped": 1,
        "delivered": 4,
        "offline": False,
    }


def test_frames_queued_while_the_test_was_busy_are_decided_as_offline(engine, app, tmp_path):
    with EvidenceWriter(tmp_path, worker="") as writer:
        ex = Actions(engine, writer, "drain")
        gate = ex.ws_gate(re.compile(r"/socket\.io/"))
        page = _open(engine, app)
        gate.go_offline()
        # Another client changes data; the test is busy outside the browser meanwhile.
        app.push('42["changed-by-other"]')
        time.sleep(0.3)
        assert gate.go_online() == 1
        page.wait_for_timeout(100)
        assert '42["changed-by-other"]' not in _received(page)


def test_a_gate_over_an_open_socket_fails_loudly(engine, app, tmp_path):
    with EvidenceWriter(tmp_path, worker="") as writer:
        ex = Actions(engine, writer, "late")
        _open(engine, app)
        with pytest.raises(StepFailed) as failure:
            ex.ws_gate("**/socket.io/**")
        assert "already open" in str(failure.value.__cause__ or failure.value)
        assert not _events(writer)


def test_raw_sockets_and_new_pages_are_gated_too(engine, app, tmp_path):
    with EvidenceWriter(tmp_path, worker="") as writer:
        ex = Actions(engine, writer, "raw")
        gate = ex.ws_gate("**/raw-ws", protocol="raw", offline=True)
        page = _open(engine, app, "/raw")
        child = page.context.new_page()
        child.goto(app.base_url + "/raw")
        _until(page, lambda: len(app.clients) >= 2, "the second page to connect")
        app.push("tick")
        app.push("2")
        page.wait_for_timeout(200)
        assert _received(page) == [] and _received(child) == []
        assert gate.dropped == 4 and gate.engine_gate.sockets == 2
        gate.go_online()
        app.push("tock")
        _until(child, lambda: _received(child) == ["tock"], "the second page online")
        _until(page, lambda: _received(page) == ["tock"], "the first page online")


def test_a_context_reset_removes_the_gate(engine, app, tmp_path):
    with EvidenceWriter(tmp_path, worker="") as writer:
        ex = Actions(engine, writer, "reset")
        gate = ex.ws_gate("**/socket.io/**", offline=True)
        engine.reset_session()
        page = _open(engine, app)
        app.push('42["visible"]')
        _until(page, lambda: '42["visible"]' in _received(page), "an ungated event")
        assert '42["visible"]' in _payloads(engine)
        with pytest.raises(StepFailed, match="deliver server frames"):
            gate.go_online()


def test_a_hand_written_gate_inside_native_leaves_provenance(engine, app, tmp_path):
    with EvidenceWriter(tmp_path, worker="") as writer:
        ex = Actions(engine, writer, "native")
        offline = {"on": False}
        with ex.native("gate the live socket by hand") as page:

            def handler(ws):
                server = ws.connect_to_server()

                def from_server(message):
                    if offline["on"] and str(message).startswith("42"):
                        return
                    ws.send(message)

                server.on_message(from_server)

            page.route_web_socket(re.compile(r"/socket\.io/"), handler)
        page = _open(engine, app)
        offline["on"] = True
        app.push('42["hidden"]')
        app.push("2")
        _until(page, lambda: "3" in app.received, "the pong of the page")
        assert '42["hidden"]' not in _received(page)
        assert '42["hidden"]' not in _payloads(engine)
        assert _payloads(engine) == _received(page)
        events = _events(writer)

    assert [(e["action"], e["source"]) for e in events] == [
        ("installed", "native"),
        ("routed", "native"),
    ]
    assert events[0]["pattern"] == r"/socket\.io/"
    assert events[1]["url"].startswith("ws://127.0.0.1:")
