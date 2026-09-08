import json

import pytest

from testence import SCHEMA_VERSION
from testence.evidence import REDACTED, EvidenceWriter, estimate_tokens
from testence.evidence.events import Event
from testence.evidence.sanitize import LEDGER_STRING_LIMIT


def test_writer_produces_valid_jsonl(tmp_path):
    with EvidenceWriter(tmp_path, worker="") as writer:
        writer.emit("run.start", fingerprint={"os": "test"})
        writer.emit("test.start", test="t1")
        writer.emit("step.end", test="t1", step="s1", status="ok", duration_ms=12.5)
        writer.emit("run.end", duration_ms=100.0, passed=1, failed=0)

    lines = (writer.run_dir / "run.jsonl").read_text(encoding="utf-8").splitlines()
    docs = [Event.parse(line) for line in lines]
    assert len(docs) == 4
    assert all(d["v"] == SCHEMA_VERSION for d in docs)
    assert [d["seq"] for d in docs] == [1, 2, 3, 4]
    assert docs[2]["test"] == "t1"
    assert docs[2]["duration_ms"] == 12.5


def test_unknown_kind_rejected():
    with pytest.raises(ValueError):
        Event(kind="bogus", run="r")


def test_parse_rejects_foreign_schema():
    with pytest.raises(ValueError):
        Event.parse(json.dumps({"v": "other/9", "kind": "note"}))


def test_assertion_event_requires_the_public_proof_fields():
    with pytest.raises(ValueError, match="invalid assertion event"):
        Event(kind="assertion", run="r-proof", payload={"outcome": "passed"})


def test_utf8_and_lf_line_endings(tmp_path):
    with EvidenceWriter(tmp_path, worker="") as writer:
        writer.emit("note", text="кириллица и → стрелки")
    raw = (writer.run_dir / "run.jsonl").read_bytes()
    assert b"\r\n" not in raw
    assert "кириллица".encode() in raw


def test_token_estimate_monotonic():
    assert estimate_tokens("word " * 100) > estimate_tokens("word")


def test_writer_propagates_plan_claims_and_remembers_failed_oracle(tmp_path):
    with EvidenceWriter(tmp_path, worker="") as writer:
        writer.bind_test(
            "test_create",
            plan={
                "schema": "testence/planspec/2",
                "project_id": "testence",
                "id": "feature.create",
                "path": "specs/create.md",
            },
            claims=["feature.create.persisted"],
        )
        writer.emit("test.start", test="test_create")
        writer.emit("step.start", test="test_create", step="s1", intent="create")
        writer.emit(
            "oracle",
            test="test_create",
            name="persistence",
            ok=False,
            diff=[{"field": "id", "ui": "42", "api": "<missing>"}],
        )

        assert writer.context_for("test_create")["claims"] == ["feature.create.persisted"]
        assert writer.last_oracle_diff("test_create") == [
            {"field": "id", "ui": "42", "api": "<missing>"}
        ]

    docs = [
        json.loads(line)
        for line in (writer.run_dir / "run.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert all(doc["plan"]["id"] == "feature.create" for doc in docs)
    assert all(doc["claims"] == ["feature.create.persisted"] for doc in docs)


def test_writer_redacts_known_and_structured_secrets_before_persisting(tmp_path):
    canary = "ledger-canary-secret"
    with EvidenceWriter(tmp_path, worker="", redact_values=[canary]) as writer:
        writer.emit(
            "note",
            test=f"case[{canary}]",
            text=f"request failed with Bearer {canary}",
            cookie_line="Cookie: session=not-registered",
            headers={"Authorization": canary, "X-Trace": "safe"},
            response={"access_token": canary, "nested": {"password": canary}},
            oversized="x" * (LEDGER_STRING_LIMIT + 100),
        )

    raw = (writer.run_dir / "run.jsonl").read_text(encoding="utf-8")
    document = json.loads(raw)
    assert canary not in raw
    assert REDACTED in raw
    assert document["headers"]["Authorization"] == REDACTED
    assert document["response"]["access_token"] == REDACTED
    assert document["cookie_line"] == f"Cookie: {REDACTED}"
    assert len(document["oversized"]) < LEDGER_STRING_LIMIT + 100
