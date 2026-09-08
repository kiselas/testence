"""API-oracle helpers: the FE/BE-divergence detector.

The single most valuable practice from manual agent-driven runs: after every UI save,
re-read the entity through the API and diff it against what the UI claims. It catches
both silent misclicks (panel closed without saving, looking like success) and the bug
class UI tests exist for — client logic diverging from server logic.
"""

from __future__ import annotations

import inspect
import json
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from testence.api import Response
from testence.engine import NetRecord
from testence.evidence import EvidenceWriter

_NEXT_UI_COMMIT = """() => new Promise(resolve => {
    requestAnimationFrame(() => requestAnimationFrame(() => resolve(true)));
})"""


def diff_views(ui_view: dict[str, Any], api_view: dict[str, Any]) -> list[dict[str, Any]]:
    """Compare only keys the UI claims to display; extra API fields are not drift."""
    diffs: list[dict[str, Any]] = []
    for key, ui_value in ui_view.items():
        api_value = api_view.get(key, "<missing>")
        if _norm(ui_value) != _norm(api_value):
            diffs.append({"field": key, "ui": ui_value, "api": api_value})
    return diffs


def _norm(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


class OracleFailed(AssertionError):
    def __init__(self, name: str, diffs: list[dict[str, Any]]) -> None:
        fields = ", ".join(d["field"] for d in diffs)
        super().__init__(f"oracle {name!r}: UI and API disagree on: {fields}")
        self.diffs = diffs


class OracleInconclusive(AssertionError):
    """The authoritative source could not produce usable evidence."""


def _origin(url: str) -> tuple[str, str, int | None]:
    parsed = urllib.parse.urlsplit(url)
    scheme = parsed.scheme.lower()
    port = parsed.port or (443 if scheme == "https" else 80 if scheme == "http" else None)
    return scheme, (parsed.hostname or "").lower(), port


def _contains_scalar(value: Any, wanted: str) -> bool:
    if isinstance(value, dict):
        return any(_contains_scalar(item, wanted) for item in value.values())
    if isinstance(value, list):
        return any(_contains_scalar(item, wanted) for item in value)
    return str(value) == wanted


@dataclass(frozen=True)
class RequestExpectation:
    """Identity of the one mutation response that belongs to an action."""

    path: str
    method: str
    origin: str | None = None
    correlation_id: str | None = None
    graphql_operation: str | None = None
    predicate: Callable[[NetRecord], bool] | None = None

    def __post_init__(self) -> None:
        if not self.path.startswith("/"):
            raise ValueError("request expectation path must start with '/'")
        if urllib.parse.urlsplit(self.path).query or urllib.parse.urlsplit(self.path).fragment:
            raise ValueError("request expectation path cannot contain query or fragment")
        if not self.method or self.method.upper() == "GET":
            raise ValueError("request expectation must name a mutation method")
        if self.origin is not None:
            scheme, host, _port = _origin(self.origin)
            if scheme not in {"http", "https"} or not host:
                raise ValueError("request expectation origin must be absolute HTTP(S)")
        if self.correlation_id == "" or self.graphql_operation == "":
            raise ValueError("request correlation and GraphQL operation cannot be empty")

    def matches(self, record: NetRecord) -> bool:
        parsed = urllib.parse.urlsplit(record.url)
        if parsed.path != self.path or record.method.upper() != self.method.upper():
            return False
        if self.origin is not None and _origin(record.url) != _origin(self.origin):
            return False
        body: Any = None
        if record.request_body:
            try:
                body = json.loads(record.request_body)
            except ValueError:
                body = record.request_body
        if self.graphql_operation is not None:
            if not isinstance(body, dict) or body.get("operationName") != self.graphql_operation:
                return False
        if self.correlation_id is not None:
            query = urllib.parse.parse_qs(parsed.query)
            response = record.json_body()
            if not any(
                _contains_scalar(candidate, self.correlation_id)
                for candidate in (query, body, response)
                if candidate is not None
            ):
                return False
        return self.predicate(record) if self.predicate is not None else True


_MISSING = object()


class _PredicateError(Exception):
    pass


def _at(document: Any, path: str) -> Any:
    if not path:
        return document
    if path.startswith("/"):
        parts = [part.replace("~1", "/").replace("~0", "~") for part in path[1:].split("/")]
    else:
        parts = path.split(".")
    current = document
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return _MISSING
    return current


@dataclass(frozen=True)
class ExpectedState:
    """Predicate and bindings for a fresh authoritative product-state read."""

    description: str
    predicate: Callable[[Any], bool]
    entity_id: Any = None
    entity_path: str = "id"
    actor_role: str | None = None
    role_path: str = "role"
    correlation_id: str | None = None
    correlation_path: str = "correlation_id"
    minimum_revision: int | float | str | None = None
    revision_path: str = "revision"
    stability_ms: int = 0
    accepted_statuses: tuple[int, ...] = (200,)

    def __post_init__(self) -> None:
        if not self.description.strip():
            raise ValueError("expected state needs a description")
        if not callable(self.predicate):
            raise TypeError("expected-state predicate must be callable")
        if self.stability_ms < 0:
            raise ValueError("stability_ms cannot be negative")
        if not self.accepted_statuses or any(
            not isinstance(status, int) or not 100 <= status <= 599
            for status in self.accepted_statuses
        ):
            raise ValueError("accepted_statuses must contain valid HTTP statuses")

    def evaluate(self, actual: Any) -> tuple[bool, str]:
        bindings = (
            (self.entity_id, self.entity_path, "entity"),
            (self.actor_role, self.role_path, "role"),
            (self.correlation_id, self.correlation_path, "correlation"),
        )
        for expected, path, label in bindings:
            if expected is None:
                continue
            observed = _at(actual, path)
            if observed is _MISSING or observed != expected:
                return False, f"wrong {label} binding at {path!r}"
        if self.minimum_revision is not None:
            observed = _at(actual, self.revision_path)
            if observed is _MISSING:
                return False, f"missing revision at {self.revision_path!r}"
            if isinstance(observed, (int, float)) and isinstance(
                self.minimum_revision, (int, float)
            ):
                fresh = observed >= self.minimum_revision
            else:
                fresh = observed == self.minimum_revision
            if not fresh:
                return False, f"stale revision at {self.revision_path!r}"
        try:
            matches = bool(self.predicate(actual))
        except Exception as exc:  # noqa: BLE001 - a broken predicate cannot prove state
            raise _PredicateError(
                f"expected-state predicate raised {exc.__class__.__name__}: {exc}"
            ) from exc
        return (True, "matched") if matches else (False, "expected predicate did not match")

    def public(self) -> dict[str, Any]:
        document: dict[str, Any] = {"description": self.description}
        for key in ("entity_id", "actor_role", "correlation_id", "minimum_revision"):
            value = getattr(self, key)
            if value is not None:
                document[key] = value
        if self.stability_ms:
            document["stability_ms"] = self.stability_ms
        return document


@dataclass(frozen=True)
class OracleObservation:
    outcome: str
    reason: str
    actual: Any
    attempts: int
    elapsed_ms: float


def _authoritative_value(response: Any, expected: ExpectedState) -> tuple[Any, str | None]:
    if not isinstance(response, Response):
        return None, "authoritative read must return testence.api.Response"
    if response.status not in expected.accepted_statuses:
        return None, f"authoritative read returned HTTP {response.status}"
    content_type = (response.header("content-type") or "").lower()
    if "text/html" in content_type or response.body.lstrip().lower().startswith("<!doctype html"):
        return None, "authoritative read returned HTML"
    value = response.json
    if value in (None, "", [], {}):
        return None, "authoritative read returned empty or non-JSON content"
    return value, None


def observe_expected_state(
    read: Callable[[], Response],
    expected: ExpectedState,
    *,
    deadline_ms: int = 3_000,
    poll_ms: int = 100,
) -> OracleObservation:
    """Repeat safe reads until state matches for the required observation window."""
    if deadline_ms < 0 or poll_ms <= 0:
        raise ValueError("deadline_ms must be non-negative and poll_ms must be positive")
    started = time.monotonic()
    deadline = started + deadline_ms / 1_000
    stable_since: float | None = None
    attempts = 0
    actual: Any = None
    last_reason = "deadline elapsed before a usable observation"
    saw_valid = False
    last_was_valid = False
    while True:
        attempts += 1
        try:
            response = read()
            actual, invalid = _authoritative_value(response, expected)
        except Exception as exc:  # noqa: BLE001 - unavailable oracle is inconclusive
            invalid = f"authoritative read raised {exc.__class__.__name__}: {exc}"
        now = time.monotonic()
        if invalid is not None:
            last_reason = invalid
            stable_since = None
            last_was_valid = False
        else:
            try:
                matches, last_reason = expected.evaluate(actual)
            except _PredicateError as exc:
                last_reason = str(exc)
                stable_since = None
                last_was_valid = False
            else:
                saw_valid = True
                last_was_valid = True
                if matches:
                    if stable_since is None:
                        stable_since = now
                    if (now - stable_since) * 1_000 >= expected.stability_ms:
                        return OracleObservation(
                            "passed",
                            "matched expected state",
                            actual,
                            attempts,
                            (now - started) * 1_000,
                        )
                else:
                    stable_since = None
        if now >= deadline:
            break
        time.sleep(min(poll_ms / 1_000, max(0.0, deadline - now)))
    if stable_since is not None:
        last_reason = f"state did not remain stable for {expected.stability_ms}ms"
        outcome = "inconclusive"
    else:
        outcome = "failed" if saw_valid and last_was_valid else "inconclusive"
    return OracleObservation(
        outcome, last_reason, actual, attempts, (time.monotonic() - started) * 1_000
    )


def _source_location(depth: int = 2) -> str:
    frame = inspect.currentframe()
    try:
        for _ in range(depth):
            frame = frame.f_back if frame is not None else None
        if frame is None:
            return "unknown"
        source = Path(frame.f_code.co_filename)
        try:
            source = source.resolve().relative_to(Path.cwd().resolve())
        except (OSError, ValueError):
            source = Path(source.name)
        return f"{source.as_posix()}:{frame.f_lineno}"
    finally:
        del frame


def _assertion_identity(assertion_id: str | None, claim_id: str | None) -> bool:
    if (assertion_id is None) != (claim_id is None):
        raise ValueError("assertion_id and claim_id must be supplied together")
    return assertion_id is not None


def _emit_assertion(
    writer: EvidenceWriter,
    test_id: str,
    *,
    assertion_id: str,
    claim_id: str,
    oracle_kind: str,
    expected: Any,
    actual: Any,
    diffs: list[dict[str, Any]],
    source: str,
    outcome: str | None = None,
) -> None:
    writer.emit(
        "assertion",
        test=test_id,
        assertion_id=assertion_id,
        claim_id=claim_id,
        oracle_kind=oracle_kind,
        outcome=outcome or ("failed" if diffs else "passed"),
        expected=expected,
        actual=actual,
        diff=diffs or None,
        source=source,
    )


def _emit_observation(
    writer: EvidenceWriter,
    test_id: str,
    name: str,
    expected: ExpectedState,
    observation: OracleObservation,
    *,
    assertion_id: str | None,
    claim_id: str | None,
    source: str,
    operation: dict[str, Any] | None = None,
) -> None:
    detail = {
        "outcome": observation.outcome,
        "reason": observation.reason,
        "attempts": observation.attempts,
        "elapsed_ms": round(observation.elapsed_ms, 1),
    }
    writer.emit(
        "oracle",
        test=test_id,
        name=name,
        ok=observation.outcome == "passed",
        expected=expected.public(),
        actual=observation.actual,
        observation=detail,
        operation=operation,
    )
    if _assertion_identity(assertion_id, claim_id):
        diffs = (
            []
            if observation.outcome == "passed"
            else [
                {
                    "field": "expected_state",
                    "expected": expected.description,
                    "actual": observation.reason,
                }
            ]
        )
        _emit_assertion(
            writer,
            test_id,
            assertion_id=str(assertion_id),
            claim_id=str(claim_id),
            oracle_kind="api",
            expected=expected.public(),
            actual=observation.actual,
            diffs=diffs,
            source=source,
            outcome=observation.outcome,
        )


def _raise_observation(name: str, observation: OracleObservation) -> None:
    if observation.outcome == "passed":
        return
    if observation.outcome == "inconclusive":
        raise OracleInconclusive(f"oracle {name!r} was inconclusive: {observation.reason}")
    raise OracleFailed(
        name,
        [{"field": "expected_state", "expected": "matched", "api": observation.reason}],
    )


def verify_expected_state(
    writer: EvidenceWriter,
    test_id: str,
    name: str,
    read: Callable[[], Response],
    expected: ExpectedState,
    *,
    deadline_ms: int = 3_000,
    poll_ms: int = 100,
    assertion_id: str | None = None,
    claim_id: str | None = None,
    source: str | None = None,
) -> OracleObservation:
    """Prove an expected predicate with fresh reads and optional stability window."""
    assertion_source = source or _source_location()
    observation = observe_expected_state(
        read,
        expected,
        deadline_ms=deadline_ms,
        poll_ms=poll_ms,
    )
    _emit_observation(
        writer,
        test_id,
        name,
        expected,
        observation,
        assertion_id=assertion_id,
        claim_id=claim_id,
        source=assertion_source,
    )
    _raise_observation(name, observation)
    return observation


def save_and_verify_state(
    actions: Any,
    save_target: Any,
    *,
    name: str,
    request: RequestExpectation,
    read: Callable[[], Response],
    expected: ExpectedState,
    request_timeout_ms: int = 3_000,
    deadline_ms: int = 3_000,
    poll_ms: int = 100,
    assertion_id: str | None = None,
    claim_id: str | None = None,
) -> OracleObservation:
    """Perform one mutation, bind its response, then prove stable persisted state."""
    assertion_source = _source_location()
    _assertion_identity(assertion_id, claim_id)
    mark = actions.engine.net_mark()
    actions.click(save_target, intent=f"save {name}")
    response = actions.engine.wait_for_response(
        request.path,
        method=request.method,
        since=mark,
        timeout_ms=request_timeout_ms,
        predicate=request.matches,
    )
    records = [record for record in actions.engine.network_log()[mark:] if request.matches(record)]
    operation = {
        "path": request.path,
        "method": request.method.upper(),
        "correlation_id": request.correlation_id,
        "graphql_operation": request.graphql_operation,
        "matching_requests": len(records),
        "status": response.status if response is not None else None,
    }
    if len(records) > 1:
        observation = OracleObservation(
            "failed", "mutation was sent more than once", operation, 0, 0.0
        )
    elif response is None:
        if records:
            observation = OracleObservation(
                "inconclusive",
                "matching mutation produced no completed response",
                operation,
                0,
                0.0,
            )
        else:
            observation = OracleObservation(
                "failed", "matching mutation was not sent", operation, 0, 0.0
            )
    elif response.status is None:
        observation = OracleObservation(
            "inconclusive", "matching mutation response was incomplete", operation, 0, 0.0
        )
    elif not 200 <= response.status < 300:
        observation = OracleObservation(
            "failed", f"matching mutation returned HTTP {response.status}", operation, 0, 0.0
        )
    elif response.json_body() in (None, "", [], {}):
        observation = OracleObservation(
            "inconclusive",
            "matching mutation returned empty or non-JSON content",
            operation,
            0,
            0.0,
        )
    else:
        observation = observe_expected_state(
            read,
            expected,
            deadline_ms=deadline_ms,
            poll_ms=poll_ms,
        )
    _emit_observation(
        actions.writer,
        actions.test_id,
        name,
        expected,
        observation,
        assertion_id=assertion_id,
        claim_id=claim_id,
        source=assertion_source,
        operation=operation,
    )
    _raise_observation(name, observation)
    return observation


def save_and_verify(
    actions: Any,
    save_target: Any,
    *,
    name: str,
    ui_view: Callable[[], dict[str, Any]],
    api_view: Callable[[], dict[str, Any]],
    expect_request: str | None = None,
    settle_ms: int = 3_000,
    assertion_id: str | None = None,
    claim_id: str | None = None,
    oracle_kind: str = "api",
) -> list[dict[str, Any]]:
    """Click save, then prove the save actually happened and agrees with the UI.

    This is the practice that produced every finding of the manual agent-driven
    runs, turned into one call. It guards two different failures at once:

    - **The click that did nothing.** A panel can close without saving and look
      exactly like success. Re-reading the entity through the API is the only way
      to tell those apart.
    - **Front end and back end disagreeing.** Client-side logic is a copy of
      server-side logic, and copies drift silently. Comparing the two views after
      each save is what makes a UI test worth more than an API test.

    ``expect_request`` additionally scopes a completed response to this click,
    which distinguishes "the server rejected it" from "the front end never
    asked" without waiting for global network quiet. ``settle_ms`` is the response
    budget in that path and the legacy network-idle budget only when no request
    signal is declared. Returns the diff (empty when consistent); raises
    :class:`OracleFailed` on divergence, so a test does not have to remember to
    assert.
    """
    bound_assertion = _assertion_identity(assertion_id, claim_id)
    assertion_source = _source_location()
    mark = actions.engine.net_mark() if expect_request else 0
    actions.click(save_target, intent=f"save {name}")
    if expect_request:
        # A completed mutation response is the outcome boundary. Waiting for
        # networkidle afterwards adds a mandatory 500 ms even on a quiet page and
        # burns the entire budget on polling/streaming SPAs. Scope the response to
        # this click so an earlier list/save request cannot satisfy it.
        response = actions.engine.wait_for_response(
            expect_request,
            since=mark,
            timeout_ms=settle_ms,
        )
        request_seen = response is not None or actions.engine.wait_for_request(
            expect_request, since=mark, timeout_ms=1
        )
        if not request_seen:
            raise AssertionError(
                f"saving {name} sent no request matching {expect_request!r} — "
                "the UI accepted the click but nothing reached the server"
            )
        # A response callback updates React state in a microtask; two animation
        # frames let that local commit render without waiting for unrelated global
        # traffic. Older/custom engines can omit this optional optimization.
        if hasattr(actions.engine, "wait_for_predicate_js"):
            actions.engine.wait_for_predicate_js(
                _NEXT_UI_COMMIT,
                timeout_ms=max(1, min(settle_ms, 250)),
            )
    else:
        # Compatibility path for applications with no declared mutation signal.
        # Prefer expect_request: networkidle is intentionally only a fallback.
        actions.settle(settle_ms)

    observed_ui = ui_view()
    observed_api = api_view()
    diffs = diff_views(observed_ui, observed_api)
    actions.writer.emit(
        "oracle",
        test=actions.test_id,
        name=name,
        ok=not diffs,
        diff=diffs or None,
        ui=observed_ui,
        api=observed_api,
    )
    if bound_assertion:
        _emit_assertion(
            actions.writer,
            actions.test_id,
            assertion_id=str(assertion_id),
            claim_id=str(claim_id),
            oracle_kind=oracle_kind,
            expected=observed_ui,
            actual=observed_api,
            diffs=diffs,
            source=assertion_source,
        )
    if diffs:
        raise OracleFailed(name, diffs)
    return diffs


def verify(
    writer: EvidenceWriter,
    test_id: str,
    name: str,
    ui_view: dict[str, Any],
    api_view: dict[str, Any],
    *,
    assertion_id: str | None = None,
    claim_id: str | None = None,
    oracle_kind: str = "api",
    source: str | None = None,
) -> None:
    """Emit an oracle event; raise OracleFailed on divergence."""
    bound_assertion = _assertion_identity(assertion_id, claim_id)
    diffs = diff_views(ui_view, api_view)
    writer.emit("oracle", test=test_id, name=name, ok=not diffs, diff=diffs or None)
    if bound_assertion:
        _emit_assertion(
            writer,
            test_id,
            assertion_id=str(assertion_id),
            claim_id=str(claim_id),
            oracle_kind=oracle_kind,
            expected=ui_view,
            actual=api_view,
            diffs=diffs,
            source=source or _source_location(),
        )
    if diffs:
        raise OracleFailed(name, diffs)
