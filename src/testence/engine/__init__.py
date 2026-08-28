"""Engine facade. Import the protocol and the factory from here — never a
concrete implementation: that indirection is what keeps a future CDP-native
executor a swap rather than a rewrite (ADR-0001)."""

import os
import re
from typing import Any

from .protocol import Engine, NetRecord, Target, dump_net

#: Registered implementations. A new backend registers a name here and becomes
#: selectable by configuration, with no change above this layer.
BACKENDS = ("playwright-cdp",)

_DEFAULT_DEBUG_PORT = 9222


def worker_port_offset() -> int:
    """Debug-port offset for this process, from the xdist worker id.

    Every browser is launched with ``--remote-debugging-port`` so a triage client
    can attach later. That port is a machine-wide resource: four workers all
    asking for 9222 means one binds it and the rest fail. ``gw3`` therefore gets
    9225.
    """
    match = re.search(r"\d+", os.environ.get("PYTEST_XDIST_WORKER", ""))
    return int(match.group()) if match else 0


def create_engine(settings: Any, backend: str = "playwright-cdp") -> Engine:
    """Build the engine named by ``backend`` from resolved settings."""
    if backend not in BACKENDS:
        raise ValueError(f"unknown engine backend {backend!r}; known: {', '.join(BACKENDS)}")
    from .playwright_cdp import PlaywrightCdpEngine

    return PlaywrightCdpEngine(
        base_url=settings.base_url,
        cdp_url=settings.cdp_url,
        browser_channel=settings.browser_channel,
        headed=settings.headed,
        api_prefix=settings.api_prefix,
        timeout_ms=settings.timeout_ms,
        ignore_https_errors=not settings.verify_tls,
        debug_port=(getattr(settings, "debug_port", None) or _DEFAULT_DEBUG_PORT)
        + worker_port_offset(),
        # On by default at the framework level: CSS entry animations are pure wait
        # for a deterministic runner (150-300 ms per modal/panel open), and no case
        # should ever assert on an animation frame. Escape hatch for the one that
        # legitimately must: `"keep_animations": true` in the profile's extras.
        reduce_motion=not settings.extra.get("keep_animations", False),
        # Which DOM attribute Target("testid", ...) resolves against. Declared per
        # project in the settings file, because the stable attribute is a property
        # of the application, not of the framework.
        test_id_attribute=str(settings.extra.get("test_id_attribute", "")),
    )


__all__ = ["BACKENDS", "Engine", "NetRecord", "Target", "create_engine", "dump_net",
           "worker_port_offset"]
