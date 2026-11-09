"""Fresh-process collection for ``testence cases``: test ids and their case ids."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest


class _Cases:
    def __init__(self, path: Path) -> None:
        self.path = path

    @pytest.hookimpl(trylast=True)
    def pytest_collection_finish(self, session: pytest.Session) -> None:
        from testence.cases import SYSTEM

        tests: list[dict[str, Any]] = []
        for item in session.items:
            marker = item.get_closest_marker("testence")
            tms = (marker.kwargs.get("tms") if marker is not None else None) or {}
            raw = tms.get(SYSTEM, ()) if isinstance(tms, dict) else ()
            ids = [raw] if isinstance(raw, (str, int)) else list(raw)
            tests.append({"nodeid": item.nodeid, "cases": [str(case).strip() for case in ids]})
        self.path.write_text(json.dumps({"tests": tests}), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args, pytest_args = parser.parse_known_args()
    if pytest_args and pytest_args[0] == "--":
        pytest_args = pytest_args[1:]
    code = pytest.main([*pytest_args, "--collect-only", "-q"], plugins=[_Cases(args.out)])
    return 0 if args.out.is_file() else int(code)


if __name__ == "__main__":
    raise SystemExit(main())
