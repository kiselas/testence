"""Capability negotiation for engine adapters without implementation types."""

from __future__ import annotations

from enum import Enum
from typing import Any, Protocol, runtime_checkable


class Capability(str, Enum):
    LIFECYCLE = "lifecycle"
    SESSION = "session"
    NAVIGATION = "browser.navigation"
    DOM = "browser.dom"
    NETWORK = "browser.network"
    WEBSOCKET = "browser.websocket"
    VISUAL = "visual.screenshot"
    ACCESSIBILITY = "browser.accessibility"
    JAVASCRIPT = "browser.javascript"
    KEYBOARD = "browser.keyboard"
    FRAMES = "browser.frames"
    POPUPS = "browser.popups"
    FILES = "browser.files"
    DIALOGS = "browser.dialogs"
    #: Fake timers: install, fast-forward, pause and resume page time.
    CLOCK = "browser.clock"
    #: The engine's own page object for what the DSL does not express (ADR-0027).
    NATIVE = "browser.native"
    EVIDENCE = "evidence"


CAPABILITY_SCHEMA = "testence/engine-capabilities/1"
WEB_CAPABILITIES = frozenset(cap.value for cap in Capability)
PLATFORM_CAPABILITIES = frozenset({Capability.LIFECYCLE.value, Capability.EVIDENCE.value})


class UnsupportedCapability(RuntimeError):
    """Raised before an operation when its engine capability is unavailable."""

    def __init__(self, operation: str, required: set[str], available: set[str]) -> None:
        self.operation = operation
        self.required = frozenset(required)
        self.available = frozenset(available)
        missing = ", ".join(sorted(required - available))
        super().__init__(f"{operation} requires unsupported engine capability: {missing}")


@runtime_checkable
class CapabilityProvider(Protocol):
    def capabilities(self) -> frozenset[str]: ...


@runtime_checkable
class LifecycleEngine(Protocol):
    def start(self) -> None: ...
    def stop(self, *, keep_browser: bool = False) -> None: ...
    def reset_session(self) -> None: ...


@runtime_checkable
class EvidenceEngine(Protocol):
    def network_log(self) -> list[Any]: ...
    def console_log(self) -> list[dict[str, Any]]: ...
    def wait_ledger(self) -> list[dict[str, Any]]: ...
    def reset_taps(self) -> None: ...
    def browser_manifest(self) -> dict[str, Any]: ...


def engine_capabilities(engine: object) -> frozenset[str]:
    provider = getattr(engine, "capabilities", None)
    if callable(provider):
        return frozenset(
            str(value.value if isinstance(value, Capability) else value) for value in provider()
        )
    # Compatibility for adapters written before capability negotiation. Their old
    # composite Engine surface remains usable, but they should declare capabilities
    # before claiming conformance or platform-neutral operation.
    return WEB_CAPABILITIES


def require_capabilities(engine: object, operation: str, *required: Capability | str) -> None:
    expected = {value.value if isinstance(value, Capability) else str(value) for value in required}
    available = set(engine_capabilities(engine))
    if not expected <= available:
        raise UnsupportedCapability(operation, expected, available)


def capability_document(engine: object, *, backend: str) -> dict[str, Any]:
    return {
        "schema": CAPABILITY_SCHEMA,
        "backend": backend,
        "capabilities": sorted(engine_capabilities(engine)),
    }
