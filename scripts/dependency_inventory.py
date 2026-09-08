"""Write the installed runtime dependency and license inventory as JSON."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
from collections import deque
from pathlib import Path
from typing import Any

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def _file_ref(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {"path": path.name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def runtime_inventory(
    root_package: str = "testence",
    *,
    distribution_path: Path | None = None,
    smoke_receipt_path: Path | None = None,
) -> dict[str, Any]:
    pending = deque([canonicalize_name(root_package)])
    seen: set[str] = set()
    packages: list[dict[str, Any]] = []
    while pending:
        requested = pending.popleft()
        if requested in seen:
            continue
        distribution = importlib.metadata.distribution(requested)
        name = distribution.metadata.get("Name", requested)
        normalized = canonicalize_name(name)
        seen.add(normalized)
        requirements = []
        for raw in distribution.requires or []:
            requirement = Requirement(raw)
            if requirement.marker and not requirement.marker.evaluate():
                continue
            dependency = canonicalize_name(requirement.name)
            requirements.append(str(requirement))
            if dependency not in seen:
                pending.append(dependency)
        classifiers = distribution.metadata.get_all("Classifier") or []
        licenses = [
            value.removeprefix("License :: ")
            for value in classifiers
            if value.startswith("License :: ")
        ]
        declared = distribution.metadata.get("License-Expression") or distribution.metadata.get(
            "License"
        )
        observed_license = declared or (", ".join(licenses) if licenses else "NOASSERTION")
        if "::" in observed_license:
            observed_license = "NOASSERTION"
        packages.append(
            {
                "name": name,
                "version": distribution.version,
                "license": observed_license,
                "requires": sorted(requirements),
            }
        )
    result: dict[str, Any] = {
        "schema": "testence/dependency-inventory/1",
        "root": canonicalize_name(root_package),
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "packages": sorted(packages, key=lambda item: canonicalize_name(item["name"])),
    }
    if distribution_path is not None:
        distribution_ref = _file_ref(distribution_path.resolve())
        result["distribution"] = distribution_ref
    if smoke_receipt_path is not None:
        smoke_path = smoke_receipt_path.resolve()
        smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
        if smoke.get("status") != "passed":
            raise ValueError("dependency inventory requires a passed installed-wheel smoke receipt")
        if distribution_path is None:
            raise ValueError("--smoke-receipt requires --distribution")
        smoke_distribution = smoke.get("distribution", {})
        if smoke_distribution.get("sha256") != result["distribution"]["sha256"]:
            raise ValueError("smoke receipt distribution differs from the inventory distribution")
        result["smoke_receipt"] = _file_ref(smoke_path)
        result["components"] = {
            "chromium": {
                "role": "browser runtime installed by Playwright",
                "version": smoke.get("browser", {}).get("version"),
            },
            "playwright_driver": {
                "role": "browser protocol client and bundled driver",
                "version": next(
                    (
                        item["version"]
                        for item in result["packages"]
                        if canonicalize_name(item["name"]) == "playwright"
                    ),
                    None,
                ),
            },
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", default="testence")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--distribution", type=Path)
    parser.add_argument("--smoke-receipt", type=Path)
    args = parser.parse_args()
    try:
        result = runtime_inventory(
            args.package,
            distribution_path=args.distribution,
            smoke_receipt_path=args.smoke_receipt,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
