"""Engine facade. Import the protocol and the factory from here — never a
concrete implementation: that indirection is what keeps a future CDP-native
executor a swap rather than a rewrite (ADR-0001)."""

import os
import re
from typing import Any

from .capabilities import (
    CAPABILITY_SCHEMA,
    Capability,
    CapabilityProvider,
    EvidenceEngine,
    LifecycleEngine,
    UnsupportedCapability,
    capability_document,
    engine_capabilities,
    require_capabilities,
)
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

    capture = settings.extra.get("capture_policy", {})
    if not isinstance(capture, dict):
        raise ValueError("capture_policy must be an object")
    admitted = capture.get("body_content_types", ["application/json"])
    if not isinstance(admitted, list) or not all(isinstance(item, str) for item in admitted):
        raise ValueError("capture_policy.body_content_types must be a list of strings")
    debug_port = getattr(settings, "debug_port", None)
    if debug_port is None:
        debug_port = _DEFAULT_DEBUG_PORT
    return PlaywrightCdpEngine(
        base_url=settings.base_url,
        cdp_url=settings.cdp_url,
        browser_channel=settings.browser_channel,
        headed=settings.headed,
        api_prefix=settings.api_prefix,
        timeout_ms=settings.timeout_ms,
        ignore_https_errors=not settings.verify_tls,
        debug_port=0 if debug_port == 0 else debug_port + worker_port_offset(),
        # On by default at the framework level: CSS entry animations are pure wait
        # for a deterministic runner (150-300 ms per modal/panel open), and no case
        # should ever assert on an animation frame. Escape hatch for the one that
        # legitimately must: `"keep_animations": true` in the profile's extras.
        reduce_motion=not settings.extra.get("keep_animations", False),
        # Which DOM attribute Target("testid", ...) resolves against. Declared per
        # project in the settings file, because the stable attribute is a property
        # of the application, not of the framework.
        test_id_attribute=str(settings.extra.get("test_id_attribute", "")),
        user_data_dir=str(settings.extra.get("user_data_dir") or "") or None,
        capture_network_bodies=bool(capture.get("network_bodies", False)),
        capture_screenshots=bool(capture.get("screenshots", False)),
        admitted_body_content_types=tuple(admitted),
        body_cap_bytes=int(capture.get("body_cap_bytes", 64 * 1024)),
        viewport=settings.extra.get("viewport"),
        screenshot_masks=_screenshot_masks(settings),
    )


_MISSING_BROWSER = (
    "Executable doesn't exist",
    "Looks like Playwright was just installed",
    "is not found at",
)


def browser_launch_hint(channel: str, failure: str) -> str:
    """What to do when the browser for ``channel`` failed to launch with ``failure``.

    A missing executable is fixed by installing it. A browser that exists but does not
    start (a crash on spawn, an application-control or antivirus policy, a broken
    profile) is not: reinstalling the same executable changes nothing, while another
    channel usually runs at once.
    """
    if any(marker in failure for marker in _MISSING_BROWSER):
        if channel in {"chromium", "chromium-headless-shell"}:
            return f"python -m playwright install {channel}"
        return (
            f"install the {channel!r} browser, or point Testence at another one with "
            "TESTENCE_BROWSER_CHANNEL"
        )
    other = "msedge" if os.name == "nt" and channel != "msedge" else "chrome"
    if channel in {"chrome", "msedge"} and other == channel:
        other = "chromium"
    return (
        f"the {channel!r} browser is installed but did not start; try "
        f"TESTENCE_BROWSER_CHANNEL={other}, and check antivirus or application-control "
        "policies for the Playwright browser directory"
    )


def _screenshot_masks(settings: Any) -> tuple[Target, ...]:
    masks = getattr(settings, "screenshot_masks", None)
    return tuple(masks()) if callable(masks) else ()


__all__ = [
    "BACKENDS",
    "Capability",
    "CAPABILITY_SCHEMA",
    "CapabilityProvider",
    "Engine",
    "EvidenceEngine",
    "LifecycleEngine",
    "NetRecord",
    "Target",
    "UnsupportedCapability",
    "capability_document",
    "browser_launch_hint",
    "create_engine",
    "dump_net",
    "engine_capabilities",
    "require_capabilities",
    "worker_port_offset",
]
