"""Evidence-pack assembly — the failure path, which was previously verified only
by hand and by the corpus. A framework whose whole value is what it produces on
failure cannot leave that path untested.

Uses a fake engine: pack assembly must work even when the page is unreachable,
which is exactly the situation a real failure often creates.
"""

from __future__ import annotations

import json
from typing import Any

from testence.engine import NetRecord
from testence.evidence import EvidenceWriter
from testence.triage import assemble_pack
from testence.triage.heal import HealProposal


class FakeEngine:
    def __init__(self, *, aria: str = "- button \"Save\"", broken: bool = False) -> None:
        self._aria = aria
        self._broken = broken

    def settle(self, timeout_ms: int = 1_500) -> bool:
        return True

    def aria_snapshot(self) -> str:
        if self._broken:
            raise RuntimeError("target page closed")
        return self._aria

    def network_log(self) -> list[NetRecord]:
        return [
            NetRecord("GET", "/api/v1/things", 200, 0.0, 12.0),
            NetRecord("POST", "/api/v1/things", 500, 0.0, 40.0,
                      request_body='{"name":"x"}', response_body='{"detail":"boom"}'),
        ]

    def console_log(self) -> list[dict[str, Any]]:
        return [{"level": "error", "text": "TypeError: x is not a function"}]

    def screenshot(self, path: str) -> None:
        if self._broken:
            raise RuntimeError("no page to capture")
        open(path, "wb").close()

    def browser_manifest(self) -> dict[str, Any]:
        return {"cdp_endpoint": "http://127.0.0.1:9222", "page_url": "http://app/x"}


def test_pack_contains_every_section_an_agent_needs(tmp_path):
    writer = EvidenceWriter(tmp_path, worker="")
    pack = assemble_pack(FakeEngine(), writer, "test_thing", error="AssertionError: nope")

    for name in ("pack.json", "TRIAGE.md", "aria.txt", "network.jsonl",
                 "console.txt", "browser.json"):
        assert (pack / name).exists(), f"missing {name}"

    index = json.loads((pack / "pack.json").read_text(encoding="utf-8"))
    assert index["error"].startswith("AssertionError")
    assert index["page_settled"] is True
    assert set(index["verdicts"]) == {"real_bug", "behaviour_change", "ui_change",
                                      "flaky_timing", "environment"}
    assert index["sections_est_tokens"]["aria"] > 0

    # The network ledger must carry the failing response body — that is usually the
    # single most decisive piece of evidence.
    network = (pack / "network.jsonl").read_text(encoding="utf-8")
    assert '"status": 500' in network and "boom" in network
    assert "cdp_endpoint" in (pack / "browser.json").read_text(encoding="utf-8")


def test_pack_survives_a_dead_page(tmp_path):
    """When the page is gone, that fact is itself evidence — assembly must not
    raise, or a crash inside triage would erase the whole failure."""
    writer = EvidenceWriter(tmp_path, worker="")
    pack = assemble_pack(FakeEngine(broken=True), writer, "test_dead", error="browser died")

    assert "unavailable" in (pack / "aria.txt").read_text(encoding="utf-8")
    assert (pack / "network.jsonl").exists()


def test_oracle_diff_is_written_when_present(tmp_path):
    writer = EvidenceWriter(tmp_path, worker="")
    pack = assemble_pack(FakeEngine(), writer, "test_oracle", error="oracle failed",
                         oracle_diff=[{"field": "cidr", "ui": "10.0.0.0/24",
                                       "api": "10.0.1.0/24"}])
    document = json.loads((pack / "oracle.json").read_text(encoding="utf-8"))
    assert document[0]["field"] == "cidr"


def test_heal_proposal_is_surfaced_in_the_index(tmp_path):
    """A triage agent must see the moved-vs-gone reading before opening sections."""
    writer = EvidenceWriter(tmp_path, worker="")
    proposal = HealProposal(intent="save the form", old_target="role='button'",
                            verdict_hint="ui_change", score=0.91,
                            new_target={"kind": "role", "value": "button", "name": "Store"},
                            suggested_edit="- old\n+ new")
    pack = assemble_pack(FakeEngine(), writer, "test_heal", error="not found", heal=proposal)

    index = json.loads((pack / "pack.json").read_text(encoding="utf-8"))
    assert index["heal_hint"] == {"verdict_hint": "ui_change", "score": 0.91}
    heal = json.loads((pack / "heal.json").read_text(encoding="utf-8"))
    assert heal["new_target"]["name"] == "Store"


def test_oversized_section_is_truncated_with_a_pointer(tmp_path):
    """Budgets must clip loudly: an agent has to be able to tell "small" from
    "clipped", or it will reason about a page it only partly saw."""
    writer = EvidenceWriter(tmp_path, worker="")
    huge = "- button \"x\"\n" * 20_000
    pack = assemble_pack(FakeEngine(aria=huge), writer, "test_big", error="boom")

    aria = (pack / "aria.txt").read_text(encoding="utf-8")
    assert "<truncated:" in aria
    assert (pack / "full-aria.txt").exists()
    assert len(aria) < len(huge)


def test_pack_event_lands_in_the_ledger(tmp_path):
    writer = EvidenceWriter(tmp_path, worker="")
    assemble_pack(FakeEngine(), writer, "test_ledger", error="boom")
    events = [json.loads(line) for line in
              (writer.run_dir / "run.jsonl").read_text(encoding="utf-8").splitlines()]
    pack_events = [e for e in events if e["kind"] == "pack"]
    assert len(pack_events) == 1
    assert pack_events[0]["test"] == "test_ledger"
    assert "aria" in pack_events[0]["sections_est_tokens"]
