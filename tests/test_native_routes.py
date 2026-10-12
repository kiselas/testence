"""Bounded model exploration of route registration, cancellation and dispatch."""

import inspect
from itertools import product
from types import SimpleNamespace

from testence.engine.native_routes import NativeRoutes


class Owner:
    def __init__(self):
        self.handlers = []
        self.pages = []
        self.listeners = []

    def route(self, url, handler, *, times=None):
        self.handlers.append((url, handler))

    def unroute(self, url, handler=None):
        self.handlers = [
            entry
            for entry in self.handlers
            if entry[0] != url or (handler is not None and entry[1] is not handler)
        ]

    def on(self, name, callback):
        self.listeners.append(callback)

    def remove_listener(self, name, callback):
        self.listeners.remove(callback)

    def dispatch(self):
        route = Route()
        for _, handler in reversed(self.handlers):
            argc = len(inspect.signature(handler).parameters)
            handler(route, route.request) if argc == 2 else handler(route)
            if route.outcome != "fallback":
                break
        return route


class Route:
    def __init__(self):
        self.request = object()
        self.outcome = None

    def fulfill(self, *, status=None, response=None, **kwargs):
        self.outcome = "fulfill"

    def abort(self, error_code="failed"):
        self.outcome = "abort"

    def fallback(self):
        self.outcome = "fallback"

    def continue_(self):
        self.outcome = "continue"


def test_short_lifecycle_sequences_agree_with_an_independent_model():
    operations = ("register", "unroute", "request", "close")
    for length in range(1, 5):
        for sequence in product(operations, repeat=length):
            owner = Owner()
            events = []
            watcher = NativeRoutes(
                lambda request, outcome: events.append(outcome), lambda page: None
            )
            watcher.install(owner)
            active, closed, expected = False, False, 0

            def handler(route):
                route.fulfill(status=201)

            for operation in sequence:
                if operation == "register" and not closed:
                    owner.route("**/x", handler)
                    active = True
                elif operation == "unroute":
                    owner.unroute("**/x", handler)
                    active = False
                elif operation == "request":
                    owner.dispatch()
                    expected += int(active)
                elif operation == "close":
                    watcher.close()
                    active, closed = False, True
                assert events == ["201"] * expected, sequence
            watcher.close()
            assert not owner.handlers and not owner.listeners, sequence


def test_fallback_then_fulfill_is_recorded_once_and_abort_is_distinct():
    owner = Owner()
    events = []
    watcher = NativeRoutes(lambda request, outcome: events.append(outcome), lambda page: None)
    watcher.install(owner)
    owner.route("**/x", lambda route: route.fulfill(response=SimpleNamespace(status=202)))
    owner.route("**/x", lambda route, request: route.fallback())
    assert owner.dispatch().outcome == "fulfill"
    assert events == ["202"]
    owner.route("**/x", lambda route: route.abort())
    assert owner.dispatch().outcome == "abort"
    assert events == ["202", "abort"]
    watcher.close()


def test_close_preserves_preexisting_handlers_and_later_client_customization():
    owner = Owner()

    def original(route):
        route.continue_()

    owner.route("**/x", original)
    watcher = NativeRoutes(lambda request, outcome: None, lambda page: None)
    watcher.install(owner)
    owner.route("**/x", lambda route: route.abort())

    def customized(*args, **kwargs):
        return None

    owner.route = customized
    watcher.close()
    assert owner.handlers == [("**/x", original)]
    assert owner.route is customized
