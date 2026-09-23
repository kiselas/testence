"""Long-lived logged-in Chrome for the interactive development loop.

Iterating on a suite pays browser launch + login on every pytest run; this
launcher pays both once. Start it, leave it running, and point runs at it:

    python -m testence.dev_browser --profile staging

    # every subsequent run attaches in ~0 s instead of launching + logging in:
    python -m pytest tests_e2e --testence-profile staging-attached

The window is headed on purpose: the same browser is the triage substrate — when
a case fails, the page is sitting there at the failure state, already yours.
Ctrl+C closes it.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from testence.auth import from_settings
from testence.config import Settings
from testence.engine.playwright_cdp import PlaywrightCdpEngine


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="launch a logged-in Chrome with a CDP port and keep it alive"
    )
    parser.add_argument("--profile", default=None, help="settings profile (e.g. staging)")
    parser.add_argument("--port", type=int, default=9222, help="CDP debug port")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args(argv)

    settings = Settings.load(Path.cwd(), profile=args.profile)
    if not settings.base_url:
        raise SystemExit("no base_url — pass --profile or set TESTENCE_BASE_URL")

    profile_dir = Path(settings.runs_root) / f".chrome-profile-{args.profile or 'default'}"
    engine = PlaywrightCdpEngine(
        base_url=settings.base_url,
        headed=not args.headless,
        debug_port=args.port,
        api_prefix=settings.api_prefix,
        timeout_ms=settings.timeout_ms,
        ignore_https_errors=not settings.verify_tls,
        # A profile on disk, not new_context(): only the *default* context is
        # visible to a later connect_over_cdp, so a session established in an
        # anonymous context would be unreachable by the runs meant to reuse it.
        user_data_dir=str(profile_dir),
    )
    engine.start()
    context = from_settings(settings).authenticate(engine)
    print(f"logged in to {settings.base_url} ({context.describe()['scheme']})")
    print(f"CDP endpoint: http://127.0.0.1:{args.port}")
    print(
        "attach runs with an *-attached profile or "
        f"--testence-cdp http://127.0.0.1:{args.port} --testence-auth attached"
    )
    print("Ctrl+C to close.")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        engine.stop()


if __name__ == "__main__":
    main()
