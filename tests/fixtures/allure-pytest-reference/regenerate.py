"""Rebuild ``expected.json`` from a real allure-pytest run of ``project/``.

    cd tests/fixtures/allure-pytest-reference/project
    <venv with allure-pytest>/python -m pytest -p no:cacheprovider \\
        --alluredir <out> --clean-alluredir
    cd ..
    python regenerate.py <out> <allure-pytest version>

Only fields that identify a result or carry declared metadata are kept. ``host``,
``thread``, ``language`` and ``framework`` describe the machine or the tool, not the
test, and differ between the two producers by design.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ENVIRONMENT_LABELS = {"host", "thread", "language", "framework"}


def main(results: Path, version: str) -> None:
    cases = []
    for path in sorted(results.glob("*-result.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        cases.append(
            {
                "fullName": document["fullName"],
                "testCaseId": document["testCaseId"],
                "historyId": document["historyId"],
                "name": document["name"],
                "description": document.get("description"),
                "titlePath": document.get("titlePath", []),
                "parameters": sorted(
                    (
                        {"name": item["name"], "value": item["value"]}
                        for item in document.get("parameters", [])
                    ),
                    key=lambda item: item["name"],
                ),
                "labels": sorted(
                    (
                        {"name": item["name"], "value": item["value"]}
                        for item in document.get("labels", [])
                        if item["name"] not in ENVIRONMENT_LABELS
                    ),
                    key=lambda item: (item["name"], item["value"]),
                ),
                "links": sorted(
                    (
                        {"name": item.get("name"), "url": item["url"], "type": item.get("type")}
                        for item in document.get("links", [])
                    ),
                    key=lambda item: item["url"],
                ),
            }
        )
    cases.sort(key=lambda case: (case["fullName"], case["historyId"]))
    target = Path(__file__).with_name("expected.json")
    target.write_text(
        json.dumps(
            {"producer": f"allure-pytest {version}", "cases": cases}, indent=1, ensure_ascii=False
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2])
