"""``testence inventory``: a per-screen reference from a synthetic ``run.jsonl``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from testence.cli import main
from testence.evidence import EvidenceWriter
from testence.inventory import UNKNOWN_PAGE, inventory, template_path

SAVE = "role='button' name='Save'"
NAME = "role='textbox' name='Name'"
TOAST = "role='status'"


class _Ledger:
    """Synthetic events through the real writer, so they carry a valid identity."""

    def __init__(self, root: Path, run_id: str) -> None:
        self.writer = EvidenceWriter(root / "runs", run_id=run_id, worker="")
        self.step = 0

    def emit(self, kind: str, test: str = "", attempt: str = "a1", **fields: Any) -> None:
        if test:
            fields["test"] = test
        self.writer.emit(kind, **fields)

    def step_pair(
        self,
        test: str,
        intent: str,
        target: str | None = None,
        *,
        status: str = "ok",
        text: str = "",
        operation: str | None = None,
        attempt: str = "a1",
        error: str | None = None,
    ) -> None:
        self.step += 1
        extra = {"operation": {"method": operation}} if operation else {}
        self.emit(
            "step.start",
            test,
            attempt,
            step=f"s{self.step}",
            intent=intent,
            target=target,
            depth=0,
            **extra,
        )
        end: dict[str, Any] = {"step": f"s{self.step}", "status": status, "depth": 0}
        if status == "ok" and target:
            end["fingerprint"] = {"tag": "div", "text": text}
        if error:
            end["error"] = error
        self.emit("step.end", test, attempt, **end, **extra)

    def write(self) -> Path:
        self.writer.close()
        return Path(self.writer.run_dir)


EDIT = "tests/test_projects.py::test_rename"
LIST = "tests/test_projects.py::test_list_shows_rows"


def _first_run(root: Path) -> Path:
    ledger = _Ledger(root, "r-1")
    ledger.emit("run.start")
    # Attempt 1: the toast check fails; the rerun goes green.
    for attempt, toast_ok in (("a1", False), ("a2", True)):
        ledger.emit("test.start", EDIT, attempt)
        ledger.step_pair(EDIT, "open https://app.example/projects/42/settings", attempt=attempt)
        ledger.step_pair(EDIT, "type the new name", NAME, operation="fill", attempt=attempt)
        ledger.step_pair(EDIT, "save", SAVE, operation="click", text="Save", attempt=attempt)
        ledger.step_pair(
            EDIT,
            "expect 'Project saved' at role='status'",
            TOAST,
            status="ok" if toast_ok else "fail",
            text="Project saved",
            attempt=attempt,
            error=None if toast_ok else "AssertionError: role='status' not visible in 5000 ms",
        )
        ledger.emit(
            "net",
            EDIT,
            attempt,
            reads=[{"method": "GET", "path": "/api/v1/projects/{id}", "n": 2, "status": 200}],
            mutations=[{"method": "PATCH", "origin": "https://app.example",
                        "path": "/api/v1/projects/{id}", "status": 409 if not toast_ok else 200}],
        )  # fmt: skip
        ledger.emit(
            "api.request",
            EDIT,
            attempt,
            method="GET",
            url="https://app.example/api/v1/projects/42",
            status=200,
        )
        ledger.emit(
            "test.end",
            EDIT,
            attempt,
            status="passed" if toast_ok else "failed",
            **({} if toast_ok else {"rerun": True}),
        )
    # A test whose only navigation is a custom intent without a URL.
    ledger.emit("test.start", LIST)
    ledger.step_pair(LIST, "open the project list")
    ledger.step_pair(LIST, "first row is the seeded project", "css='tr[data-key]'", text="P-1")
    ledger.emit("test.end", LIST, status="passed")
    ledger.emit("run.end", status="passed", run_status="passed")
    return ledger.write()


def test_template_path_drops_origin_query_and_identifiers() -> None:
    assert template_path("https://app.example/projects/42/settings?tab=1") == (
        "/projects/{id}/settings"
    )
    uuid = "0b7d2c1e-8f1a-4c2b-9d3e-1a2b3c4d5e6f"
    assert template_path(f"/api/v1/hosts/{uuid}/") == "/api/v1/hosts/{id}"
    assert template_path("https://app.example") == "/"


def test_inventory_lists_targets_api_texts_and_traps_per_page(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run = _first_run(tmp_path)
    out = tmp_path / "docs" / "inventory"

    assert main(["inventory", str(run), "--out", str(out), "--json"]) == 0
    result = json.loads(capsys.readouterr().out)

    pages = {page["page"]: page for page in result["pages"]}
    assert set(pages) == {"/projects/{id}/settings", UNKNOWN_PAGE}
    settings = (out / "projects-id-settings.md").read_text(encoding="utf-8")
    assert settings.startswith("# /projects/{id}/settings\n")
    assert "`https://app.example/projects/42/settings`" in settings
    assert "| `role='textbox' name='Name'` | textbox | Name | fill |" in settings
    assert "| `role='button' name='Save'` | button | Save | click | Save |" in settings
    assert "| page | PATCH | `/api/v1/projects/{id}` | 409, 200 |" in settings
    assert "| page | GET | `/api/v1/projects/{id}` | 200 |" in settings
    assert "| test | GET | `/api/v1/projects/{id}` | 200 |" in settings
    assert "- Project saved" in settings
    assert (
        "**expect 'Project saved' at role='status'** at `role='status'`: failed 1x, then green"
        in (settings)
    )
    assert "not visible in 5000 ms" in settings

    unknown = (out / f"{UNKNOWN_PAGE}.md").read_text(encoding="utf-8")
    assert "`css='tr[data-key]'`" in unknown
    assert "Put the URL in the `goto` intent" in unknown
    assert pages[UNKNOWN_PAGE]["targets"] == 1


def test_rerun_merges_with_the_file_and_keeps_manual_sections(tmp_path: Path) -> None:
    out = tmp_path / "inventory"
    inventory(_first_run(tmp_path), out)
    page = out / "projects-id-settings.md"
    manual = "## Notes <!-- manual -->\n\nThe Save button stays disabled until the name changes.\n"
    page.write_text(page.read_text(encoding="utf-8").replace("## Texts", manual + "\n## Texts"),
                    encoding="utf-8")  # fmt: skip

    ledger = _Ledger(tmp_path, "r-2")
    ledger.emit("test.start", EDIT)
    ledger.step_pair(EDIT, "open https://app.example/projects/7/settings")
    ledger.step_pair(EDIT, "delete the project", "role='button' name='Delete'", operation="click")
    ledger.step_pair(
        EDIT,
        "expect 'Project saved' at role='status'",
        TOAST,
        status="fail",
        error="AssertionError: toast text differs",
    )
    ledger.emit("test.end", EDIT, status="failed")
    second = inventory(ledger.write(), out)

    [entry] = [p for p in second["pages"] if p["page"] == "/projects/{id}/settings"]
    assert entry["status"] == "updated"
    assert entry["manual_sections"] == 1
    text = page.read_text(encoding="utf-8")
    assert "The Save button stays disabled until the name changes." in text
    assert text.count("## Notes <!-- manual -->") == 1
    assert "runs `r-1`, `r-2`" in text
    # Earlier facts survive, new ones join, and the trap accumulates.
    assert "`role='button' name='Save'`" in text
    assert "`role='button' name='Delete'`" in text
    assert "failed 2x, then green" in text
    assert "toast text differs" in text

    again = inventory(tmp_path / "runs" / "r-2", out)
    assert [p["status"] for p in again["pages"] if p["page"] != UNKNOWN_PAGE] == ["unchanged"]


def test_a_missing_run_directory_is_an_input_error(tmp_path: Path) -> None:
    assert main(["inventory", str(tmp_path / "runs" / "r-none")]) == 2
