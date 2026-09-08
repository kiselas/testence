"""Exercise an installed Testence wheel from a consumer directory.

Run this script with isolated mode (``python -I``). Its directory contains no
``testence`` package, so every import resolves from the installed distribution.
"""

from __future__ import annotations

import argparse
import json
import socket
import tempfile
from importlib.resources import files
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

from testence.agent import install_skills, verify_skills
from testence.application import run_demo
from testence.config import Settings
from testence.contracts import SCHEMA_INVENTORY
from testence.distribution import verify_installed_wheel
from testence.engine import Target, create_engine


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--distribution", type=Path, required=True)
    args = parser.parse_args()
    distribution = args.distribution.resolve()
    binding = verify_installed_wheel(distribution)

    schema_root = files("testence.contracts").joinpath("schemas")
    schema_files = sorted(
        item.name for item in schema_root.iterdir() if item.name.endswith(".json")
    )
    missing_schemas = []
    for name, schema in SCHEMA_INVENTORY.items():
        if not any(
            json.dumps(schema) in schema_root.joinpath(path).read_text(encoding="utf-8")
            for path in schema_files
        ):
            missing_schemas.append(name)

    with tempfile.TemporaryDirectory(prefix="testence-wheel-consumer-") as temporary:
        consumer = Path(temporary)
        installed = install_skills(consumer, ["codex", "claude"])
        verified = verify_skills(consumer, ["codex", "claude"])
        demo = run_demo(consumer / "demo", run_prefix="wheel-smoke")

        page = consumer / "browser-smoke.html"
        page.write_text("<!doctype html><h1>Installed wheel browser smoke</h1>", encoding="utf-8")
        engine = create_engine(
            Settings(base_url="", headed=False, timeout_ms=5_000, debug_port=_free_port())
        )
        browser_ok = False
        browser_version = None
        try:
            engine.start()
            engine.goto(page.as_uri())
            engine.expect_text(
                Target("role", "heading", name="Installed wheel browser smoke"),
                "Installed wheel browser smoke",
            )
            browser_ok = True
        finally:
            engine.stop()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                browser_version = browser.version
            finally:
                browser.close()

        result: dict[str, Any] = {
            "schema": "testence/installed-wheel-smoke/1",
            "distribution": binding,
            "schemas": {"count": len(schema_files), "missing": missing_schemas},
            "agents": {
                "installed": installed["status"],
                "verified": verified["status"],
                "clients": sorted(item["client"] for item in verified["clients"]),
            },
            "demo": {
                "status": demo["status"],
                "runs": [
                    {
                        "name": item["name"],
                        "test_exit": item["test_exit"],
                        "assurance": item["summary"]["assurance"],
                        "report_exists": Path(item["report"]).is_file(),
                        "pack_required": item["name"] == "intentional_failure",
                        "pack_exists": item["pack"] is not None and Path(item["pack"]).is_dir(),
                    }
                    for item in demo["runs"]
                ],
            },
            "browser": {"chromium": browser_ok, "version": browser_version},
        }

    passed = (
        not missing_schemas
        and result["distribution"]["verified_package_files"] > 0
        and result["agents"]["installed"] == "installed"
        and result["agents"]["verified"] == "valid"
        and result["demo"]["status"] == "passed"
        and all(item["report_exists"] for item in result["demo"]["runs"])
        and all(item["pack_exists"] == item["pack_required"] for item in result["demo"]["runs"])
        and result["browser"]["chromium"]
        and bool(result["browser"]["version"])
    )
    result["status"] = "passed" if passed else "failed"
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
