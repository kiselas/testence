from __future__ import annotations

from pathlib import Path
from typing import Any

from testence.engine import NetRecord
from testence.evidence import REDACTED, EvidenceWriter
from testence.export import export_run
from testence.fingerprints import FingerprintStore
from testence.report import render_report
from testence.triage import assemble_pack


class _CanaryEngine:
    def __init__(self, canary: str) -> None:
        self.canary = canary

    def settle(self, timeout_ms: int = 1_500) -> bool:
        return True

    def aria_snapshot(self) -> str:
        return f'- textbox "Password" value="{self.canary}"'

    def network_log(self) -> list[NetRecord]:
        return [
            NetRecord(
                "POST",
                f"https://app.example.test/api/save?token={self.canary}",
                500,
                0.0,
                5.0,
                request_body=f'{{"password":"{self.canary}"}}',
                response_body=f'{{"access_token":"{self.canary}"}}',
            )
        ]

    def console_log(self) -> list[dict[str, Any]]:
        return [{"level": "error", "text": f"Bearer {self.canary}"}]

    def screenshot(self, path: str) -> None:
        Path(path).write_bytes(b"")

    def browser_manifest(self) -> dict[str, Any]:
        return {
            "cdp_endpoint": "http://127.0.0.1:9222",
            "page_url": f"https://app.example.test/failure?api_key={self.canary}",
        }


def test_canary_is_absent_from_ledger_pack_report_and_exports(tmp_path):
    canary = "synthetic-canary-9f31"
    writer = EvidenceWriter(tmp_path, run_id="r-canary", worker="", redact_values=[canary])
    writer.emit("run.start", fingerprint={"authorization": f"Bearer {canary}"})
    writer.emit("test.start", test=f"test_secret[{canary}]", file="tests/test_secret.py")
    pack = assemble_pack(
        _CanaryEngine(canary),
        writer,
        f"test_secret[{canary}]",
        error=f"password={canary}",
        oracle_diff=[{"field": "token", "ui": canary, "api": canary}],
    )
    writer.emit(
        "test.end",
        test=f"test_secret[{canary}]",
        status="failed",
        error=f"Authorization: Bearer {canary}",
        pack=str(pack.relative_to(writer.run_dir)),
    )
    writer.emit("run.end", duration_ms=1.0, passed=0, failed=1)
    writer.close()

    render_report(writer.run_dir, tmp_path / "report.html")
    export_run(writer.run_dir, "allure", tmp_path / "allure")
    export_run(writer.run_dir, "ctrf", tmp_path / "ctrf")
    fingerprints = FingerprintStore(tmp_path / "fingerprints.json", redact_values=[canary])
    fingerprints.record(
        f"test_secret[{canary}]",
        f"enter {canary}",
        f"label={canary}",
        {"name": canary, "selector": f"[data-token='{canary}']"},
    )
    fingerprints.flush()

    text_suffixes = {".json", ".jsonl", ".txt", ".md", ".html", ".properties"}
    persisted = [path for path in tmp_path.rglob("*") if path.suffix in text_suffixes]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in persisted)
    assert canary not in combined
    assert REDACTED in combined


class _MultiRequestEngine:
    """A capture with more than one request: the ordinary shape of a real failure."""

    def __init__(self, unknown_secret: str) -> None:
        self.unknown_secret = unknown_secret

    def settle(self, timeout_ms: int = 1_500) -> bool:
        return True

    def aria_snapshot(self) -> str:
        return '- button "Save"'

    def network_log(self) -> list[NetRecord]:
        return [
            NetRecord(
                "POST",
                "https://app.example.test/api/login",
                200,
                0.0,
                5.0,
                request_body=f'{{"user":"alice","password":"{self.unknown_secret}"}}',
                response_body=f'{{"access_token":"{self.unknown_secret}"}}',
            ),
            NetRecord("GET", "https://app.example.test/api/me", 200, 0.0, 3.0),
        ]

    def console_log(self) -> list[dict[str, Any]]:
        return []

    def screenshot(self, path: str) -> None:
        Path(path).write_bytes(b"")

    def browser_manifest(self) -> dict[str, Any]:
        return {"cdp_endpoint": "http://127.0.0.1:9222", "page_url": "https://app.example.test"}


def test_credential_fields_are_redacted_in_a_multi_request_capture(tmp_path):
    """A second request must not disable key-based redaction for the whole capture.

    The pack writes network evidence as JSON Lines. Sanitizing the joined blob as one
    JSON document only succeeded for a single record; every larger capture fell back to
    text rules that cannot see an already escaped ``password`` field.
    """

    secret = "never-configured-2f7c"
    writer = EvidenceWriter(tmp_path, run_id="r-multi", worker="", redact_values=[])
    pack = assemble_pack(
        _MultiRequestEngine(secret),
        writer,
        "test_multi_request",
        error="save failed",
    )
    writer.close()

    network = (pack / "network.jsonl").read_text(encoding="utf-8")
    assert secret not in network
    assert network.count("\n") == 1, "every captured record stays its own line"
    assert REDACTED in network
    persisted = [path for path in tmp_path.rglob("*") if path.suffix in {".json", ".jsonl"}]
    assert secret not in "\n".join(path.read_text(encoding="utf-8") for path in persisted)
