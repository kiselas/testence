from __future__ import annotations

import json
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

import testence.oracle as oracle_module
from testence.api import ApiClient, Response
from testence.engine import NetRecord
from testence.oracle import (
    ExpectedState,
    OracleFailed,
    OracleInconclusive,
    RequestExpectation,
    observe_expected_state,
    save_and_verify_state,
    verify_expected_state,
)


def _response(body, status=200, content_type="application/json") -> Response:
    text = body if isinstance(body, str) else json.dumps(body)
    return Response(status, [("content-type", content_type)], text)


def _state(**overrides):
    document = {
        "id": "widget-42",
        "role": "editor",
        "correlation_id": "run-7",
        "revision": 2,
        "state": "saved",
    }
    document.update(overrides)
    return document


def _expected(*, stability_ms=0):
    return ExpectedState(
        "widget 42 is durably saved",
        lambda body: body["state"] == "saved",
        entity_id="widget-42",
        actor_role="editor",
        correlation_id="run-7",
        minimum_revision=2,
        stability_ms=stability_ms,
    )


def test_expected_state_polls_past_optimistic_stale_read():
    responses = iter([_response(_state(revision=1)), _response(_state())])

    observed = observe_expected_state(
        lambda: next(responses), _expected(), deadline_ms=50, poll_ms=1
    )

    assert observed.outcome == "passed"
    assert observed.attempts == 2


@pytest.mark.parametrize(
    "response,reason",
    [
        (_response(""), "empty or non-JSON"),
        (_response("<html>login</html>", content_type="text/html"), "HTML"),
        (_response({"detail": "unauthorized"}, status=401), "HTTP 401"),
        (_response({"detail": "forbidden"}, status=403), "HTTP 403"),
        (_response({"detail": "missing"}, status=404), "HTTP 404"),
        (_response({"detail": "error"}, status=500), "HTTP 500"),
    ],
)
def test_unusable_authoritative_read_is_inconclusive(response, reason):
    observed = observe_expected_state(lambda: response, _expected(), deadline_ms=0)

    assert observed.outcome == "inconclusive"
    assert reason in observed.reason


@pytest.mark.parametrize(
    "actual,reason",
    [
        (_state(id="widget-other"), "wrong entity"),
        (_state(role="viewer"), "wrong role"),
        (_state(correlation_id="old-run"), "wrong correlation"),
        (_state(revision=1), "stale revision"),
    ],
)
def test_wrong_binding_is_a_decisive_failed_oracle(actual, reason):
    observed = observe_expected_state(lambda: _response(actual), _expected(), deadline_ms=0)

    assert observed.outcome == "failed"
    assert reason in observed.reason


class _Clock:
    """Virtual monotonic time for the oracle; a sleep may overshoot like a busy host.

    Stability windows are milliseconds long, and real sleeps overshoot them on hosted
    runners (5 ms took over 20 ms on macOS, 1 ms takes ~15 ms on Windows Python 3.10).
    Virtual time makes each scheduling case explicit instead of host-dependent.
    """

    def __init__(self, overshoot_ms: float = 0) -> None:
        self.now = 0.0
        self.overshoot = overshoot_ms / 1_000

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds + self.overshoot


@pytest.fixture
def clock(monkeypatch):
    def install(overshoot_ms: float = 0) -> _Clock:
        virtual = _Clock(overshoot_ms)
        monkeypatch.setattr(oracle_module, "time", virtual)
        return virtual

    return install


@pytest.mark.parametrize(("overshoot_ms", "attempts"), [(0, 5), (20, 2)])
def test_state_must_remain_true_through_the_observation_window(clock, overshoot_ms, attempts):
    clock(overshoot_ms)
    responses = iter([_response(_state()), _response(_state(state="rolled-back"))])

    observed = observe_expected_state(
        lambda: next(responses, _response(_state(state="rolled-back"))),
        _expected(stability_ms=15),
        deadline_ms=20,
        poll_ms=5,
    )

    assert observed.outcome == "failed"
    assert observed.attempts == attempts
    assert "predicate" in observed.reason


def test_negative_predicate_is_observed_for_the_whole_window(clock):
    clock()
    expected = ExpectedState(
        "deleted widget stays absent",
        lambda body: all(item["id"] != "widget-42" for item in body),
        stability_ms=10,
    )

    observed = observe_expected_state(
        lambda: _response([{"id": "widget-other"}]),
        expected,
        deadline_ms=20,
        poll_ms=5,
    )

    assert observed.outcome == "passed"
    assert observed.attempts == 3


@pytest.mark.parametrize("overshoot_ms", [0, 40])
def test_deadline_shorter_than_stability_window_is_inconclusive(clock, overshoot_ms):
    # With a 40 ms overshoot the second read lands 41 ms after the first, past the
    # 5 ms deadline. It must not complete the 30 ms window the deadline cannot hold.
    clock(overshoot_ms)
    observed = observe_expected_state(
        lambda: _response(_state()),
        _expected(stability_ms=30),
        deadline_ms=5,
        poll_ms=1,
    )

    assert observed.outcome == "inconclusive"
    assert "remain stable" in observed.reason


def test_point_in_time_state_read_after_the_deadline_still_passes(clock):
    clock(40)
    responses = iter([_response(_state(revision=1)), _response(_state())])

    observed = observe_expected_state(
        lambda: next(responses), _expected(), deadline_ms=5, poll_ms=1
    )

    assert observed.outcome == "passed"
    assert observed.attempts == 2


def test_oracle_loss_during_stability_window_is_inconclusive(clock):
    clock()
    responses = iter(
        [_response(_state()), _response("<html>lost</html>", content_type="text/html")]
    )

    observed = observe_expected_state(
        lambda: next(responses, _response("<html>lost</html>", content_type="text/html")),
        _expected(stability_ms=20),
        deadline_ms=5,
        poll_ms=1,
    )

    assert observed.outcome == "inconclusive"
    assert "HTML" in observed.reason


def test_request_expectation_binds_origin_path_method_correlation_and_graphql_operation():
    expectation = RequestExpectation(
        "/graphql",
        "POST",
        origin="https://app.example",
        correlation_id="run-7",
        graphql_operation="SaveWidget",
    )
    matching = NetRecord(
        "POST",
        "https://app.example/graphql",
        200,
        0.0,
        1.0,
        request_body=json.dumps(
            {
                "operationName": "SaveWidget",
                "variables": {"correlation_id": "run-7"},
            }
        ),
        response_body='{"data":{"saveWidget":{"id":"widget-42"}}}',
    )

    assert expectation.matches(matching)
    assert not expectation.matches(
        NetRecord(
            "POST",
            "https://other.example/graphql",
            200,
            0.0,
            1.0,
            request_body=matching.request_body,
        )
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"path": "api/widgets", "method": "POST"},
        {"path": "/api/widgets?all=1", "method": "POST"},
        {"path": "/api/widgets", "method": "GET"},
        {"path": "/api/widgets", "method": "POST", "origin": "app.example"},
        {"path": "/api/widgets", "method": "POST", "correlation_id": ""},
    ],
)
def test_request_expectation_rejects_ambiguous_identity(kwargs):
    with pytest.raises(ValueError):
        RequestExpectation(**kwargs)


class WriterProbe:
    def __init__(self):
        self.events = []

    def emit(self, kind, **document):
        self.events.append((kind, document))


def test_verify_expected_state_emits_typed_inconclusive_assertion():
    writer = WriterProbe()

    with pytest.raises(OracleInconclusive, match="inconclusive"):
        verify_expected_state(
            writer,
            "case",
            "persisted widget",
            lambda: _response("<html>login</html>", content_type="text/html"),
            _expected(),
            deadline_ms=0,
            assertion_id="assert.widget.persisted",
            claim_id="widget.persisted",
        )

    assertion = next(document for kind, document in writer.events if kind == "assertion")
    assert assertion["outcome"] == "inconclusive"
    assert assertion["assertion_id"] == "assert.widget.persisted"


def test_broken_expected_predicate_is_inconclusive_not_a_product_violation():
    expected = ExpectedState("broken predicate", lambda _body: 1 / 0)

    observed = observe_expected_state(
        lambda: _response({"state": "saved"}), expected, deadline_ms=0
    )

    assert observed.outcome == "inconclusive"
    assert "ZeroDivisionError" in observed.reason


@dataclass
class EngineProbe:
    records: list[NetRecord]

    def net_mark(self):
        return 0

    def wait_for_response(self, _path, *, method, since, timeout_ms, predicate):
        return next(
            (record for record in self.records[since:] if record.status and predicate(record)),
            None,
        )

    def network_log(self):
        return self.records


class ActionsProbe:
    def __init__(self, records):
        self.engine = EngineProbe(records)
        self.writer = WriterProbe()
        self.test_id = "case"
        self.clicks = 0

    def click(self, _target, *, intent):
        assert intent == "save widget"
        self.clicks += 1


def _mutation(correlation="run-7"):
    return NetRecord(
        "POST",
        "https://app.example/api/widgets",
        201,
        0.0,
        1.0,
        request_body=json.dumps({"correlation_id": correlation}),
        response_body='{"id":"widget-42"}',
    )


def test_save_and_verify_state_executes_mutation_once_then_polls_read():
    actions = ActionsProbe([_mutation()])

    observed = save_and_verify_state(
        actions,
        SimpleNamespace(),
        name="widget",
        request=RequestExpectation(
            "/api/widgets", "POST", origin="https://app.example", correlation_id="run-7"
        ),
        read=lambda: _response(_state()),
        expected=_expected(),
        deadline_ms=0,
    )

    assert actions.clicks == 1
    assert observed.outcome == "passed"


def test_duplicate_mutation_is_a_failed_oracle_and_is_not_retried():
    actions = ActionsProbe([_mutation(), _mutation()])
    reads = 0

    def read():
        nonlocal reads
        reads += 1
        return _response(_state())

    with pytest.raises(OracleFailed, match="expected_state"):
        save_and_verify_state(
            actions,
            SimpleNamespace(),
            name="widget",
            request=RequestExpectation("/api/widgets", "POST", correlation_id="run-7"),
            read=read,
            expected=_expected(),
            deadline_ms=0,
        )

    assert actions.clicks == 1
    assert reads == 0


def test_aborted_mutation_is_inconclusive_and_does_not_poll_state():
    mutation = _mutation()
    mutation.status = None
    mutation.response_body = None
    mutation.failure = "net::ERR_ABORTED"
    actions = ActionsProbe([mutation])
    reads = 0

    def read():
        nonlocal reads
        reads += 1
        return _response(_state())

    with pytest.raises(OracleInconclusive, match="no completed response"):
        save_and_verify_state(
            actions,
            SimpleNamespace(),
            name="widget",
            request=RequestExpectation("/api/widgets", "POST", correlation_id="run-7"),
            read=read,
            expected=_expected(),
            deadline_ms=0,
        )

    assert actions.clicks == 1
    assert reads == 0


def test_missing_mutation_is_a_failed_oracle_and_does_not_poll_state():
    actions = ActionsProbe([])
    reads = 0

    def read():
        nonlocal reads
        reads += 1
        return _response(_state())

    with pytest.raises(OracleFailed, match="expected_state"):
        save_and_verify_state(
            actions,
            SimpleNamespace(),
            name="widget",
            request=RequestExpectation("/api/widgets", "POST", correlation_id="run-7"),
            read=read,
            expected=_expected(),
            deadline_ms=0,
        )

    assert actions.clicks == 1
    assert reads == 0


def test_api_fresh_read_sets_cache_bypass_headers(monkeypatch):
    captured = {}

    def fake_http(method, url, **kwargs):
        captured.update(method=method, url=url, **kwargs)
        return _response({"id": "widget-42"})

    monkeypatch.setattr("testence.api.http_json", fake_http)

    ApiClient("https://app.example").get_fresh(
        "/api/widgets/widget-42", headers={"Cache-Control": "max-age=3600"}
    )

    assert captured["headers"]["Cache-Control"] == "no-cache"
    assert captured["headers"]["Pragma"] == "no-cache"
