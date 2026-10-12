"""Fresh-process collection guard for the exact debug scope."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest


class Selection:
    def __init__(self, path: Path, verify: bool) -> None:
        self.path, self.verify = path, verify

    @pytest.hookimpl(trylast=True)
    def pytest_collection_finish(self, session: pytest.Session) -> None:
        selection: dict[str, Any] = {
            "nodes": [
                {
                    "nodeid": item.nodeid,
                    "parallel_declared": item.get_closest_marker("testence_parallel") is not None,
                    "namespace_fixture": "testence_namespace" in getattr(item, "fixturenames", ()),
                }
                for item in session.items
            ],
            "files": {
                str(item.path): hashlib.sha256(item.path.read_bytes()).hexdigest()
                for item in session.items
            },
        }
        if self.verify:
            if json.loads(self.path.read_text(encoding="utf-8")) != selection:
                raise pytest.UsageError(
                    "debug collection changed since preflight; no test body executed"
                )
        else:
            self.path.write_text(json.dumps(selection), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--run-id", required=True)
    args, pytest_args = parser.parse_known_args()
    os.environ["TESTENCE_RUN_ID"] = args.run_id
    if pytest_args and pytest_args[0] == "--":
        pytest_args = pytest_args[1:]
    return int(pytest.main(pytest_args, plugins=[Selection(args.selection, args.verify)]))


if __name__ == "__main__":
    raise SystemExit(main())
