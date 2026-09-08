from __future__ import annotations

import json

import pytest

from testence import SCHEMA_VERSION
from testence.evidence import Event, EvidenceWriter
from testence.export._model import LoadedRun
from testence.identity import adapt_event, parameter_fingerprints, variant_id


def test_v2_writer_stamps_run_project_worker_and_unique_event_ids(tmp_path):
    writer = EvidenceWriter(tmp_path, run_id="r-identity", worker="gw2", project_id="shop")
    writer.emit("run.start")
    writer.emit("note", text="ready")
    writer.close()

    documents = [json.loads(line) for line in writer.path.read_text(encoding="utf-8").splitlines()]
    assert [document["event_id"] for document in documents] == ["gw2:1", "gw2:2"]
    assert all(document["v"] == SCHEMA_VERSION for document in documents)
    assert all(document["run_id"] == document["run"] == "r-identity" for document in documents)
    assert all(document["project_id"] == "shop" for document in documents)


def test_event_payload_cannot_override_identity_envelope():
    event = Event(
        "note",
        "r-real",
        project_id="shop",
        worker="gw0",
        payload={"run_id": "r-spoof", "project_id": "spoof", "worker": "spoof", "event_id": "x"},
    )
    event.stamp(7)

    document = json.loads(event.to_json())
    assert document["run_id"] == "r-real"
    assert document["project_id"] == "shop"
    assert document["worker"] == "gw0"
    assert document["event_id"] == "gw0:7"


def test_legacy_event_adapter_is_lossless_and_never_invents_proof():
    event = adapt_event(
        {
            "v": "testence/1",
            "run": "r-old",
            "seq": 3,
            "kind": "note",
            "future_field": {"kept": True},
        }
    )
    assert event["v"] == "testence/2"
    assert event["source_schema"] == "testence/1"
    assert event["assurance"] == "unverified"
    assert event["future_field"] == {"kept": True}


def test_unsupported_evidence_major_is_rejected():
    with pytest.raises(ValueError, match="unsupported schema version"):
        Event.parse('{"v":"testence/99"}')


def test_variant_identity_is_canonical_and_does_not_retain_raw_values():
    left, left_parameters = variant_id({"role": "admin", "browser": "chromium"})
    right, right_parameters = variant_id({"browser": "chromium", "role": "admin"})

    assert left == right
    assert left_parameters == right_parameters
    serialized = json.dumps(left_parameters)
    assert "admin" not in serialized and "chromium" not in serialized
    assert parameter_fingerprints({"token": "short-secret"})["token"] != "short-secret"


def test_two_hundred_unicode_variants_with_long_prefixes_do_not_collide():
    prefix = "роль-администратора-" * 20
    variants = {
        variant_id({"role": f"{prefix}{index}", "browser": "chromium"})[0] for index in range(200)
    }
    assert len(variants) == 200


def test_loaded_run_keeps_attempts_of_one_case_separate():
    base = {
        "v": "testence/2",
        "project_id": "shop",
        "run": "r-retry",
        "run_id": "r-retry",
        "case_id": "checkout",
        "variant_id": "default",
        "proof_id": "proof-one",
        "parameters": {},
        "test": "tests/test_shop.py::test_checkout",
        "nodeid": "tests/test_shop.py::test_checkout",
    }
    events = [
        {
            **base,
            "event_id": "gw0:1",
            "seq": 1,
            "kind": "test.start",
            "attempt_id": "attempt-gw0-1",
        },
        {
            **base,
            "event_id": "gw0:2",
            "seq": 2,
            "kind": "test.end",
            "attempt_id": "attempt-gw0-1",
            "status": "failed",
        },
        {
            **base,
            "event_id": "gw0:3",
            "seq": 3,
            "kind": "test.start",
            "attempt_id": "attempt-gw0-2",
        },
        {
            **base,
            "event_id": "gw0:4",
            "seq": 4,
            "kind": "test.end",
            "attempt_id": "attempt-gw0-2",
            "status": "passed",
        },
    ]

    tests = LoadedRun.from_events(events).tests
    assert [(test.attempt_id, test.status) for test in tests] == [
        ("attempt-gw0-1", "failed"),
        ("attempt-gw0-2", "passed"),
    ]


def test_pytest_lifecycle_allocates_a_new_identity_for_a_repeated_protocol(tmp_path):
    import time

    from testence.config import Settings
    from testence.pytest_plugin import (
        _CONTRACT_KEY,
        _IDENTITY_KEY,
        _LifecycleState,
        _start_test,
    )

    class Item:
        nodeid = "tests/test_retry.py::test_retry"
        name = "test_retry"
        path = tmp_path / "test_retry.py"
        stash = pytest.Stash()

        @staticmethod
        def iter_markers():
            return ()

    Item.path.write_text("def test_retry(): pass\n", encoding="utf-8")
    item = Item()
    item.stash[_CONTRACT_KEY] = None
    item.stash[_IDENTITY_KEY] = {
        "project_id": "project",
        "case_id": "retry-case",
        "variant_id": "default",
        "parameters": {},
    }
    writer = EvidenceWriter(tmp_path, run_id="r-retry", worker="gw0", project_id="project")
    state = _LifecycleState(
        settings=Settings(project_id="project"),
        writer=writer,
        started_at=time.perf_counter(),
        started={},
        items={},
        finished=set(),
        counts={
            status: 0 for status in ("passed", "failed", "broken", "skipped", "aborted", "not_run")
        },
        attempts={},
    )

    _start_test(item, state)  # type: ignore[arg-type]
    state.finished.add(item.nodeid)
    writer.unbind_test(item.nodeid)
    _start_test(item, state)  # type: ignore[arg-type]
    writer.close()

    starts = []
    for line in writer.path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event["kind"] == "test.start":
            starts.append(event)
    assert [event["attempt_id"] for event in starts] == ["attempt-gw0-1", "attempt-gw0-2"]
    assert len({event["proof_id"] for event in starts}) == 2
