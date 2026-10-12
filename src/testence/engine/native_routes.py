"""Observe public native route outcomes without replacing Page or Route objects.

Interposition is per owned client object, never a global Playwright patch. Handler
signatures and unroute identities are preserved; passthrough is left untouched.
"""

from __future__ import annotations

from contextlib import suppress
from functools import wraps
from typing import Any, Callable
from weakref import WeakSet


class NativeRoutes:
    def __init__(self, record: Callable[[Any, str], None], tap: Callable[[Any], None]) -> None:
        self.record = record
        self.tap = tap
        self._owners: list[tuple[Any, Any, Any, Any, Any]] = []
        self._handlers: list[tuple[Any, Any]] = []
        self._registrations: list[tuple[Any, Any, Any]] = []
        self._routes: WeakSet[Any] = WeakSet()
        self._context: Any = None

    def install(self, context: Any) -> None:
        self._context = context
        self._watch_owner(context)
        for page in context.pages:
            self._watch_page(page)
        context.on("page", self._watch_page)

    def _watch_page(self, page: Any) -> None:
        self._watch_owner(page)
        self.tap(page)

    def _watch_owner(self, owner: Any) -> None:
        if any(entry[0] is owner for entry in self._owners):
            return
        original_route, original_unroute = owner.route, owner.unroute

        @wraps(original_route)
        def route(url: Any, handler: Any, **kwargs: Any) -> Any:
            if getattr(handler, "_testence_builtin_mock", False):
                return original_route(url, handler, **kwargs)
            bridge = self._handler(handler)
            result = original_route(url, bridge, **kwargs)
            self._registrations.append((original_unroute, url, bridge))
            return result

        @wraps(original_unroute)
        def unroute(url: Any, handler: Any = None) -> Any:
            wrapped = next(
                (bridge for source, bridge in self._handlers if source is handler), handler
            )
            return original_unroute(url, wrapped)

        self._owners.append((owner, original_route, original_unroute, route, unroute))
        owner.route, owner.unroute = route, unroute

    def _handler(self, handler: Any) -> Any:
        for source, existing in self._handlers:
            if source is handler:
                return existing

        @wraps(handler)
        def bridge(*args: Any, **kwargs: Any) -> Any:
            self._observe_route(args[0] if args else kwargs["route"])
            return handler(*args, **kwargs)

        self._handlers.append((handler, bridge))
        return bridge

    def _observe_route(self, route: Any) -> None:
        if route in self._routes:
            return
        self._routes.add(route)
        original_fulfill, original_abort = route.fulfill, route.abort

        @wraps(original_fulfill)
        def fulfill(*args: Any, **kwargs: Any) -> Any:
            response = kwargs.get("response")
            status = kwargs.get("status")
            if status is None:
                status = response.status if response is not None else 200
            self.record(route.request, str(status))
            return original_fulfill(*args, **kwargs)

        @wraps(original_abort)
        def abort(*args: Any, **kwargs: Any) -> Any:
            self.record(route.request, "abort")
            return original_abort(*args, **kwargs)

        route.fulfill, route.abort = fulfill, abort

    def close(self) -> None:
        for unroute, url, bridge in self._registrations:
            # Remove only handlers this client registered, including on borrowed
            # contexts; do not leave callbacks bound to a closed test writer.
            with suppress(Exception):
                unroute(url, bridge)
        if self._context is not None:
            self._context.remove_listener("page", self._watch_page)
        for owner, original_route, original_unroute, route, unroute in self._owners:
            # Respect subsequent client customization of the same instance.
            if owner.route is route:
                owner.route = original_route
            if owner.unroute is unroute:
                owner.unroute = original_unroute
        self._owners.clear()
        self._handlers.clear()
        self._registrations.clear()
        self._context = None
