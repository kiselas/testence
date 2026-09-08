"""Pytest integration: lifecycle ledger, per-test evidence, failure packs.

The pytest hooks own result recording so a test exists even when it never requests
``ex`` or fails before that fixture can be created. ``ex`` remains the author-facing
Actions fixture and contributes browser evidence when it is present.
"""

from __future__ import annotations

import hashlib
import os
import platform
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from testence import __version__, kernels
from testence.api import ApiClient
from testence.assurance import POLICY_DIGEST
from testence.auth import AuthContext, from_settings
from testence.config import Settings
from testence.contracts import PlanSpec, load_plan
from testence.contracts._validation import ContractError
from testence.dsl import Actions
from testence.engine import Engine, create_engine, engine_capabilities
from testence.evidence import RUN_ID_ENV, EvidenceWriter, new_run_id
from testence.fingerprints import DEFAULT_STORE, FingerprintStore
from testence.identity import TestIdentity, proof_id, source_case_id, variant_id
from testence.isolation import TestNamespace
from testence.testplan import (
    ALLURE_TESTPLAN_ENV,
    SelectionCandidate,
    TestPlanError,
    load_testplan,
    select_candidates,
)
from testence.triage import assemble_pack
from testence.triage.heal import propose

_WARM_ENGINE: Engine | None = None
_WARM_ENGINE_KEY: tuple[Any, ...] | None = None
_WARM_ENGINE_ANY_FAILED = False


def _engine_key(settings: Settings) -> tuple[Any, ...]:
    """Fields that change the browser connection or context contract."""
    return (
        settings.base_url,
        settings.api_prefix,
        settings.cdp_url,
        getattr(settings, "execution_mode", "isolated"),
        settings.browser_channel,
        getattr(settings, "debug_port", 9222),
        settings.headed,
        settings.timeout_ms,
        settings.verify_tls,
        settings.ca_bundle,
        tuple(sorted((str(key), repr(value)) for key, value in settings.extra.items())),
    )


def _acquire_warm_engine(settings: Settings) -> Engine:
    global _WARM_ENGINE, _WARM_ENGINE_KEY, _WARM_ENGINE_ANY_FAILED
    key = _engine_key(settings)
    if _WARM_ENGINE is not None and _WARM_ENGINE_KEY != key:
        close_warm_engine()
    if _WARM_ENGINE is None:
        _WARM_ENGINE = create_engine(settings)
        _WARM_ENGINE.start()
        _WARM_ENGINE_KEY = key
        _WARM_ENGINE_ANY_FAILED = False
    return _WARM_ENGINE


def close_warm_engine() -> None:
    """Close the engine retained by an opt-in warm CLI process, if any."""
    global _WARM_ENGINE, _WARM_ENGINE_KEY, _WARM_ENGINE_ANY_FAILED
    if _WARM_ENGINE is not None:
        _WARM_ENGINE.stop(keep_browser=_WARM_ENGINE_ANY_FAILED)
    _WARM_ENGINE = None
    _WARM_ENGINE_KEY = None
    _WARM_ENGINE_ANY_FAILED = False


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("testence")
    group.addoption(
        "--testence-base-url", default=None, help="target server; overrides settings/env"
    )
    group.addoption(
        "--testence-profile", default=None, help="settings profile to use (e.g. staging, local)"
    )
    group.addoption(
        "--testence-auth",
        default=None,
        help="auth scheme: none|form|api-session|bearer|basic|attached",
    )
    group.addoption(
        "--testence-cdp",
        default=None,
        help="attach to a running Chrome (e.g. http://127.0.0.1:9222) instead of launching",
    )
    group.addoption(
        "--testence-browser-channel",
        default=None,
        help="browser channel to launch (default: Playwright-bundled chromium)",
    )
    group.addoption("--testence-headless", action="store_true", default=False)
    group.addoption("--testence-runs-root", default=None)
    group.addoption("--testence-api-prefix", default=None)
    group.addoption(
        "--testence-empty-testplan",
        choices=("fail", "noop"),
        default=os.environ.get("TESTENCE_EMPTY_TESTPLAN", "fail"),
        help="policy for an explicitly empty Allure test plan (default: fail)",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Name the run before xdist spawns anyone.

    Workers are subprocesses of this process, so an environment variable set here
    reaches all of them — which is how every worker writes its ledger into one run
    directory instead of inventing a directory each. ``setdefault``: a worker runs
    this hook too and must keep the inherited value.
    """
    config.addinivalue_line(
        "markers",
        "testence(plan, case_id, claims, allure_id): bind a test to a PlanSpec case",
    )
    os.environ.setdefault(RUN_ID_ENV, new_run_id())


@dataclass(frozen=True)
class _TestContract:
    plan: PlanSpec
    path: str
    claims: tuple[str, ...]
    case_id: str
    allure_id: str | None = None

    def ledger_context(self) -> dict[str, Any]:
        assertions = [
            {
                "id": assertion.id,
                "claim_id": assertion.claim_id,
                "oracle": assertion.oracle,
                "required": assertion.required,
                **({"expected": assertion.expected} if assertion.expected else {}),
            }
            for assertion in self.plan.assertions
            if assertion.claim_id in self.claims
        ]
        scenario = next(item for item in self.plan.scenarios if item.id == self.case_id)
        return {
            "plan": {
                "schema": self.plan.schema,
                "project_id": self.plan.project_id,
                "id": self.plan.id,
                "path": self.path,
                "digest": self.plan.digest,
            },
            "claims": list(self.claims),
            "assertions": assertions,
            "plan_digest": self.plan.digest,
            "policy_digest": POLICY_DIGEST,
            **({"owner": self.plan.owner} if self.plan.owner else {}),
            **({"risk": scenario.risk} if scenario.risk else {}),
            "capabilities": list(scenario.capabilities),
            "requirements": [
                {"id": item.id, **({"url": item.url} if item.url else {})}
                for item in self.plan.requirements
            ],
            "issues": [
                {"id": item.id, **({"url": item.url} if item.url else {})}
                for item in self.plan.issues
            ],
            **({"allure_id": self.allure_id} if self.allure_id else {}),
        }


_CONTRACT_KEY = pytest.StashKey[_TestContract | None]()
_IDENTITY_KEY = pytest.StashKey[dict[str, Any]]()
_TESTPLAN_NOOP_KEY = pytest.StashKey[bool]()


def _resolve_contract(
    item: pytest.Item,
    rootpath: Path,
    available_capabilities: frozenset[str] | None = None,
) -> _TestContract | None:
    marker = item.get_closest_marker("testence")
    if marker is None:
        return None
    if marker.args:
        raise ContractError("@pytest.mark.testence accepts keyword arguments only")
    unknown = sorted(set(marker.kwargs) - {"plan", "claims", "case_id", "allure_id"})
    if unknown:
        raise ContractError("unknown testence marker field(s): " + ", ".join(unknown))
    plan_value = marker.kwargs.get("plan")
    if not isinstance(plan_value, str) or not plan_value.strip():
        raise ContractError("@pytest.mark.testence requires plan='specs/<feature>.md'")
    raw_claims = marker.kwargs.get("claims")
    if isinstance(raw_claims, str):
        claims = (raw_claims,)
    elif isinstance(raw_claims, (list, tuple)) and all(
        isinstance(claim, str) for claim in raw_claims
    ):
        claims = tuple(raw_claims)
    else:
        raise ContractError("@pytest.mark.testence requires claims=['claim.id', ...]")

    root = rootpath.resolve()
    candidate = (root / plan_value).resolve()
    if candidate != root and root not in candidate.parents:
        raise ContractError("testence plan path must stay inside the repository")
    plan = load_plan(candidate)
    plan.require_claims(claims)
    case_value = marker.kwargs.get("case_id")
    if case_value is not None and not isinstance(case_value, str):
        raise ContractError("@pytest.mark.testence case_id must be a string")
    case_id = plan.resolve_case(case_value, claims)
    scenario = next(candidate for candidate in plan.scenarios if candidate.id == case_id)
    if available_capabilities is not None:
        missing = sorted(set(scenario.capabilities) - available_capabilities)
        if missing:
            raise ContractError(
                f"case {case_id!r} requires unsupported engine capability: {', '.join(missing)}"
            )
    raw_allure_id = marker.kwargs.get("allure_id")
    if raw_allure_id is not None and (
        isinstance(raw_allure_id, bool) or not isinstance(raw_allure_id, (str, int))
    ):
        raise ContractError("@pytest.mark.testence allure_id must be a string or integer")
    allure_id = str(raw_allure_id).strip() if raw_allure_id is not None else None
    if raw_allure_id is not None and not allure_id:
        raise ContractError("@pytest.mark.testence allure_id must not be empty")
    return _TestContract(
        plan,
        candidate.relative_to(root).as_posix(),
        claims,
        case_id,
        allure_id,
    )


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    state = config.stash.get(_LIFECYCLE_KEY, None)
    available_capabilities = (
        engine_capabilities(create_engine(state.settings)) if state is not None else None
    )
    for item in items:
        try:
            contract = _resolve_contract(
                item, Path(config.rootpath), available_capabilities=available_capabilities
            )
            item.stash[_CONTRACT_KEY] = contract
            project_id = (
                contract.plan.project_id
                if contract is not None and contract.plan.project_id != "legacy"
                else (state.settings.project_id if state is not None else "unconfigured")
            )
            raw_parameters = dict(getattr(getattr(item, "callspec", None), "params", {}) or {})
            item_variant_id, parameters = variant_id(raw_parameters, nodeid=item.nodeid)
            item.stash[_IDENTITY_KEY] = {
                "project_id": project_id,
                "case_id": contract.case_id
                if contract is not None
                else source_case_id(item.nodeid),
                "variant_id": item_variant_id,
                "parameters": parameters,
            }
        except ContractError as exc:
            raise pytest.UsageError(f"{item.nodeid}: invalid Testence contract: {exc}") from exc
    _apply_testplan(config, items)


def _apply_testplan(config: pytest.Config, items: list[pytest.Item]) -> None:
    raw_path = os.environ.get(ALLURE_TESTPLAN_ENV)
    if raw_path is None:
        return
    if not raw_path.strip():
        raise pytest.UsageError(f"{ALLURE_TESTPLAN_ENV} must not be empty")
    try:
        plan = load_testplan(raw_path)
        if not plan.tests:
            if config.getoption("--testence-empty-testplan") != "noop":
                raise TestPlanError(
                    "Allure test plan selected zero tests; pass "
                    "--testence-empty-testplan=noop for an intentional no-op"
                )
            deselected = list(items)
            items[:] = []
            config.stash[_TESTPLAN_NOOP_KEY] = True
            if deselected:
                config.hook.pytest_deselected(items=deselected)
            return
        candidates: list[SelectionCandidate] = []
        for item in items:
            identity = item.stash[_IDENTITY_KEY]
            contract = item.stash.get(_CONTRACT_KEY, None)
            candidates.append(
                SelectionCandidate(
                    nodeid=item.nodeid,
                    project_id=str(identity["project_id"]),
                    case_id=str(identity["case_id"]),
                    variant_id=str(identity["variant_id"]),
                    allure_id=contract.allure_id if contract is not None else None,
                )
            )
        selected_indices = select_candidates(plan, candidates)
    except TestPlanError as exc:
        raise pytest.UsageError(str(exc)) from exc
    selected = [item for index, item in enumerate(items) if index in selected_indices]
    deselected = [item for index, item in enumerate(items) if index not in selected_indices]
    items[:] = selected
    if deselected:
        config.hook.pytest_deselected(items=deselected)


def _code_digest(path: Any) -> str:
    try:
        return hashlib.sha256(Path(str(path)).read_bytes()).hexdigest()
    except OSError:
        return ""


def _code_hash(path: Any) -> str:
    """Short digest of the file a test is defined in.

    Scopes flakiness to one version of the test: a case that goes fail -> pass while
    being authored has changed code, and calling that a flake made the suite's own
    metric read 44.4 % where nothing had ever flapped.
    """
    return _code_digest(path)[:12]


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]):
    outcome = yield
    report = outcome.get_result()
    item.stash.setdefault(_REPORTS_KEY, {})[report.when] = report  # type: ignore[misc]
    state = item.config.stash.get(_LIFECYCLE_KEY, None)
    if state is None or state.closed:
        return
    payload: dict[str, Any] = {
        "nodeid": item.nodeid,
        "display_name": item.name,
        "phase": report.when,
        "status": report.outcome,
        "duration_ms": round(float(report.duration) * 1000, 1),
    }
    wasxfail = getattr(report, "wasxfail", None)
    if wasxfail:
        payload["xfail_reason"] = str(wasxfail)
        payload["xfail"] = bool(report.skipped)
        payload["xpass"] = bool(report.passed or report.failed)
    if report.failed or report.skipped:
        payload["error"] = _report_error(report)
    state.writer.emit("test.phase", test=_test_id(item), **payload)
    if report.failed:
        engine = item.stash.get(_ENGINE_KEY, None)
        if engine is not None:
            # The report exists before fixture teardown. Mark it here so a session
            # engine knows to preserve the browser even when this is the last test.
            engine._testence_state["any_failed"] = True  # type: ignore[attr-defined]
        if report.when != "teardown" and not item.stash.get(_PACK_ATTEMPTED_KEY, False):
            item.stash[_PACK_ATTEMPTED_KEY] = True
            pack = _failure_pack(item, state, _test_id(item), _report_error(report))
            if pack:
                item.stash[_PACK_KEY] = pack


_REPORTS_KEY = pytest.StashKey[dict]()


@dataclass
class _LifecycleState:
    settings: Settings
    writer: EvidenceWriter
    started_at: float
    started: dict[str, float]
    items: dict[str, pytest.Item]
    finished: set[str]
    counts: dict[str, int]
    attempts: dict[tuple[str, str, str], int]
    deselected: int = 0
    collection_errors: int = 0
    closed: bool = False


_LIFECYCLE_KEY = pytest.StashKey[_LifecycleState]()
_ACTIONS_KEY = pytest.StashKey[Actions]()
_ENGINE_KEY = pytest.StashKey[Engine]()
_FINGERPRINTS_KEY = pytest.StashKey[FingerprintStore]()
_PACK_KEY = pytest.StashKey[str]()
_PACK_ATTEMPTED_KEY = pytest.StashKey[bool]()
_ACTIVE_STATE: _LifecycleState | None = None

#: Per-test wait budgets for the end-of-run summary (reset per pytest process).
_RUN_WAITS: list[dict[str, Any]] = []


def _settings_from_config(config: pytest.Config) -> Settings:
    return Settings.load(
        config.rootpath,
        profile=config.getoption("--testence-profile"),
        base_url=config.getoption("--testence-base-url"),
        auth=config.getoption("--testence-auth"),
        cdp_url=config.getoption("--testence-cdp"),
        browser_channel=config.getoption("--testence-browser-channel"),
        api_prefix=config.getoption("--testence-api-prefix"),
        runs_root=config.getoption("--testence-runs-root"),
        headed=False if config.getoption("--testence-headless") else None,
    )


def _new_lifecycle(config: pytest.Config) -> _LifecycleState:
    settings = _settings_from_config(config)
    redact_values = tuple(
        value
        for variable in (settings.user_var, settings.password_var)
        if (value := os.environ.get(variable) or settings.env_values.get(variable))
    )
    writer = EvidenceWriter(
        settings.runs_root,
        project_id=settings.project_id,
        redact_values=redact_values,
    )
    writer.emit(
        "run.start",
        testence=__version__,
        fingerprint={
            "os": f"{platform.system()} {platform.release()}",
            "python": platform.python_version(),
            "kernels": kernels.active_backend(),
            "worker": writer.worker or "(single)",
            **settings.describe(),
        },
    )
    writer.emit("collection.start")
    return _LifecycleState(
        settings=settings,
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


def pytest_sessionstart(session: pytest.Session | None) -> None:
    """Start evidence before collection; warm pytest sessions remain isolated."""
    global _ACTIVE_STATE
    _RUN_WAITS.clear()
    # Kept as a harmless seam for embedders that only reset the warm-run summary.
    if session is None:
        return
    state = _new_lifecycle(session.config)
    session.config.stash[_LIFECYCLE_KEY] = state
    _ACTIVE_STATE = state


def pytest_collectreport(report: pytest.CollectReport) -> None:
    state = _ACTIVE_STATE
    if state is None or state.closed:
        return
    if report.failed:
        state.collection_errors += 1
        state.writer.emit(
            "collection.error",
            nodeid=report.nodeid,
            error=_report_error(report),
        )
    elif report.skipped:
        state.writer.emit(
            "collection.skip",
            nodeid=report.nodeid,
            reason=_report_error(report),
        )


def pytest_deselected(items: list[pytest.Item]) -> None:
    state = _ACTIVE_STATE
    if state is None or state.closed or not items:
        return
    state.deselected += len(items)
    state.writer.emit(
        "collection.deselected",
        count=len(items),
        nodeids=[item.nodeid for item in items],
    )


def pytest_collection_finish(session: pytest.Session) -> None:
    state = session.config.stash.get(_LIFECYCLE_KEY, None)
    if state is None or state.closed:
        return
    cases: list[dict[str, Any]] = []
    for item in session.items:
        identity = dict(
            item.stash.get(
                _IDENTITY_KEY,
                {
                    "project_id": state.settings.project_id,
                    "case_id": source_case_id(item.nodeid),
                    "variant_id": variant_id({}, nodeid=item.nodeid)[0],
                    "parameters": {},
                },
            )
        )
        identity.update(nodeid=item.nodeid, display_name=item.name)
        contract = item.stash.get(_CONTRACT_KEY, None)
        if contract is not None:
            identity.update(contract.ledger_context())
        cases.append(identity)
    state.writer.emit(
        "collection.end",
        selected=len(session.items),
        deselected=state.deselected,
        errors=state.collection_errors,
        nodeids=[item.nodeid for item in session.items],
        cases=cases,
    )


def _test_id(item: pytest.Item) -> str:
    # Full nodeid is the collision-free source identity until schema /2 introduces
    # an explicit logical case_id.  Display names stay separate for reports.
    return item.nodeid


def _report_error(report: pytest.TestReport | pytest.CollectReport) -> str:
    crash = getattr(getattr(report, "longrepr", None), "reprcrash", None)
    message = getattr(crash, "message", None)
    if message:
        return str(message)
    longreprtext = getattr(report, "longreprtext", None)
    if longreprtext:
        return str(longreprtext)[-4000:]
    return str(getattr(report, "longrepr", ""))[-4000:]


def _start_test(item: pytest.Item, state: _LifecycleState) -> None:
    if item.nodeid in state.started and item.nodeid not in state.finished:
        return
    state.finished.discard(item.nodeid)
    item.stash[_REPORTS_KEY] = {}
    item.stash[_PACK_ATTEMPTED_KEY] = False
    item.stash[_PACK_KEY] = ""
    test_id = _test_id(item)
    contract = item.stash.get(_CONTRACT_KEY, None)
    static_identity = item.stash.get(
        _IDENTITY_KEY,
        {
            "project_id": state.settings.project_id,
            "case_id": source_case_id(item.nodeid),
            "variant_id": variant_id({}, nodeid=item.nodeid)[0],
            "parameters": {},
        },
    )
    attempt_key = (
        str(static_identity["project_id"]),
        str(static_identity["case_id"]),
        str(static_identity["variant_id"]),
    )
    attempt_number = state.attempts.get(attempt_key, 0) + 1
    state.attempts[attempt_key] = attempt_number
    attempt_id = f"attempt-{state.writer.worker or 'controller'}-{attempt_number}"
    raw_parameters = static_identity.get("parameters")
    parameters = (
        {str(key): str(value) for key, value in raw_parameters.items()}
        if isinstance(raw_parameters, dict)
        else {}
    )
    identity = TestIdentity(
        project_id=attempt_key[0],
        case_id=attempt_key[1],
        variant_id=attempt_key[2],
        attempt_id=attempt_id,
        run_id=state.writer.run_id,
        proof_id=proof_id(state.writer.run_id, attempt_key[1], attempt_key[2], attempt_id),
        parameters=parameters,
    )
    context = contract.ledger_context() if contract is not None else {}
    node_path = getattr(item, "path", "")
    test_digest_value = _code_digest(node_path)
    test_digest = f"sha256:{test_digest_value}" if test_digest_value else "unknown"
    bound_identity = identity.as_dict()
    for field in ("owner", "risk", "requirements", "issues", "allure_id"):
        if field in context:
            bound_identity[field] = context[field]
    state.writer.bind_test(
        test_id,
        identity=bound_identity,
        plan=context.get("plan"),
        claims=context.get("claims", ()),
        assertions=context.get("assertions", ()),
        plan_digest=context.get("plan_digest", "unknown"),
        test_digest=test_digest,
        policy_digest=context.get("policy_digest", POLICY_DIGEST),
    )
    state.started[item.nodeid] = time.perf_counter()
    state.items[item.nodeid] = item
    state.writer.emit(
        "test.start",
        test=test_id,
        display_name=item.name,
        file=str(node_path),
        code=test_digest_value[:12],
        nodeid=item.nodeid,
        markers=sorted({mark.name for mark in item.iter_markers()}),
    )


def _execution_outcome(reports: dict[str, pytest.TestReport]) -> tuple[str, str]:
    for phase in ("setup", "teardown"):
        report = reports.get(phase)
        if report is not None and report.failed:
            return "broken", phase

    call = reports.get("call")
    if call is not None and call.failed:
        return "failed", "call"

    for phase in ("setup", "call", "teardown"):
        report = reports.get(phase)
        if report is not None and report.skipped:
            return "skipped", phase

    if call is not None and call.passed and "teardown" in reports:
        return "passed", "call"
    return "aborted", next(
        (phase for phase in ("setup", "call", "teardown") if phase not in reports),
        "unknown",
    )


def _failure_pack(
    item: pytest.Item,
    state: _LifecycleState,
    test_id: str,
    error: str,
) -> str | None:
    engine = item.stash.get(_ENGINE_KEY, None)
    actions = item.stash.get(_ACTIONS_KEY, None)
    fingerprints = item.stash.get(_FINGERPRINTS_KEY, None)
    if engine is None or actions is None or fingerprints is None:
        return None
    engine._testence_state["any_failed"] = True  # type: ignore[attr-defined]
    try:
        heal = None
        failure = actions.last_failure
        if failure is not None and failure.target is not None:
            known = fingerprints.get(test_id, failure.intent)
            heal = propose(engine, failure.intent, failure.target, known)
        pack_dir = assemble_pack(
            engine,
            state.writer,
            test_id,
            error=error,
            oracle_diff=state.writer.last_oracle_diff(test_id),
            heal=heal,
        )
        return str(pack_dir.relative_to(state.writer.run_dir))
    except Exception as exc:  # Evidence collection must never replace the pytest result.
        state.writer.emit(
            "note",
            test=test_id,
            text="failure pack capture failed",
            error=f"{type(exc).__name__}: {exc}",
        )
        return None


def _finalize_test(item: pytest.Item, state: _LifecycleState) -> None:
    if item.nodeid in state.finished or item.nodeid not in state.started:
        return
    test_id = _test_id(item)
    reports = item.stash.get(_REPORTS_KEY, {})
    status, phase = _execution_outcome(reports)
    errors = [_report_error(report) for report in reports.values() if report.failed]
    error = errors[0] if errors else ""
    pack = item.stash.get(_PACK_KEY, None)
    if status in ("failed", "broken") and not item.stash.get(_PACK_ATTEMPTED_KEY, False):
        item.stash[_PACK_ATTEMPTED_KEY] = True
        pack = _failure_pack(item, state, test_id, error)
    duration_ms = round((time.perf_counter() - state.started[item.nodeid]) * 1000, 1)
    xfail_reason = next(
        (str(report.wasxfail) for report in reports.values() if getattr(report, "wasxfail", None)),
        None,
    )
    xfail_marker = item.get_closest_marker("xfail")
    strict_xpass = bool(
        xfail_marker is not None
        and reports.get("call") is not None
        and reports["call"].failed
        and "XPASS(strict)" in _report_error(reports["call"])
    )
    if xfail_reason is None and xfail_marker is not None:
        marker_reason = xfail_marker.kwargs.get("reason")
        xfail_reason = str(marker_reason) if marker_reason else "xfail"
    payload: dict[str, Any] = {
        "nodeid": item.nodeid,
        "display_name": item.name,
        "status": status,
        "phase": phase,
        "duration_ms": duration_ms,
    }
    if error:
        payload["error"] = error
    if pack:
        payload["pack"] = pack
    if xfail_reason:
        payload["xfail_reason"] = xfail_reason
        payload["xfail"] = any(
            report.skipped and getattr(report, "wasxfail", None) for report in reports.values()
        )
        payload["xpass"] = strict_xpass or any(
            (report.passed or report.failed) and getattr(report, "wasxfail", None)
            for report in reports.values()
        )
    state.writer.emit("test.end", test=test_id, **payload)
    state.counts[status] += 1
    state.finished.add(item.nodeid)
    state.writer.unbind_test(test_id)


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_protocol(item: pytest.Item, nextitem: pytest.Item | None):
    state = item.config.stash.get(_LIFECYCLE_KEY, None)
    if state is None or state.closed:
        yield
        return
    _start_test(item, state)
    try:
        yield
    finally:
        _finalize_test(item, state)


@pytest.hookimpl(optionalhook=True)
def pytest_testnodedown(node: Any, error: object | None) -> None:
    state = _ACTIVE_STATE
    if state is None or state.closed or error is None:
        return
    state.writer.emit(
        "worker.crash",
        crashed_worker=getattr(getattr(node, "gateway", None), "id", "unknown"),
        error=str(error),
    )


def _run_status(exitstatus: int | pytest.ExitCode) -> str:
    value = int(exitstatus)
    return {
        int(pytest.ExitCode.OK): "passed",
        int(pytest.ExitCode.TESTS_FAILED): "failed",
        int(pytest.ExitCode.INTERRUPTED): "interrupted",
        int(pytest.ExitCode.INTERNAL_ERROR): "internal_error",
        int(pytest.ExitCode.USAGE_ERROR): "usage_error",
        int(pytest.ExitCode.NO_TESTS_COLLECTED): "no_tests",
    }.get(value, "unknown")


def _close_lifecycle(state: _LifecycleState, exitstatus: int | pytest.ExitCode) -> None:
    if state.closed:
        return
    for item in state.items.values():
        _finalize_test(item, state)
    state.writer.emit(
        "run.end",
        duration_ms=round((time.perf_counter() - state.started_at) * 1000, 1),
        exit_code=int(exitstatus),
        run_status=_run_status(exitstatus),
        collection_errors=state.collection_errors,
        deselected=state.deselected,
        passed=state.counts["passed"],
        failed=state.counts["failed"],
        broken=state.counts["broken"],
        skipped=state.counts["skipped"],
        aborted=state.counts["aborted"],
        not_run=state.counts["not_run"],
    )
    state.closed = True
    state.writer.close()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int | pytest.ExitCode) -> None:
    global _ACTIVE_STATE
    if session.config.stash.get(_TESTPLAN_NOOP_KEY, False) and int(exitstatus) == int(
        pytest.ExitCode.NO_TESTS_COLLECTED
    ):
        exitstatus = pytest.ExitCode.OK
        session.exitstatus = pytest.ExitCode.OK
    state = session.config.stash.get(_LIFECYCLE_KEY, None)
    if state is not None:
        _close_lifecycle(state, exitstatus)
    if _ACTIVE_STATE is state:
        _ACTIVE_STATE = None


def pytest_terminal_summary(terminalreporter: Any) -> None:
    """One table answering "where did the time go" — the wait ledger, aggregated."""
    if not _RUN_WAITS:
        return
    write = terminalreporter.write_line
    total_wall = sum(row["wall_ms"] for row in _RUN_WAITS)
    total_wait = sum(row["waited_ms"] for row in _RUN_WAITS)
    write("")
    write(
        f"testence wait budget: {total_wait / 1000:.1f}s waited of "
        f"{total_wall / 1000:.1f}s test wall-clock"
    )

    # By operation first: this is the line that names the thing to fix. Per-test
    # rows say which case is slow; this says why, across the whole suite.
    rollup: dict[str, dict[str, float]] = {}
    for row in _RUN_WAITS:
        for op, stats in (row.get("by_op") or {}).items():
            acc = rollup.setdefault(op, {"ms": 0.0, "n": 0})
            acc["ms"] += stats["ms"]
            acc["n"] += stats["n"]
    for op, stats in sorted(rollup.items(), key=lambda kv: -kv[1]["ms"])[:8]:
        share = (stats["ms"] / total_wait * 100) if total_wait else 0
        write(
            f"  {op:22s} {stats['ms'] / 1000:6.1f}s  x{int(stats['n']):<4d} "
            f"{share:4.0f}%  avg {stats['ms'] / max(stats['n'], 1):5.0f}ms"
        )

    for row in sorted(_RUN_WAITS, key=lambda r: -r["waited_ms"])[:10]:
        worst: dict[str, Any] = row["top"][0] if row["top"] else {"op": "-", "detail": "", "ms": 0}
        write(
            f"  {row['test']}: waited {row['waited_ms'] / 1000:.1f}s "
            f"of {row['wall_ms'] / 1000:.1f}s "
            f"(worst: {worst['op']} {worst['detail'][:60]} {worst['ms']:.0f}ms)"
        )


@pytest.fixture(scope="session")
def testence_settings(request: pytest.FixtureRequest) -> Settings:
    """Resolved configuration: settings file → .env → env → CLI flags."""
    state = request.config.stash.get(_LIFECYCLE_KEY, None)
    return state.settings if state is not None else _settings_from_config(request.config)


@pytest.fixture(scope="session")
def testence_writer(request: pytest.FixtureRequest) -> EvidenceWriter:
    state = request.config.stash.get(_LIFECYCLE_KEY, None)
    if state is None:
        raise RuntimeError("Testence lifecycle writer was not initialized")
    return state.writer


@pytest.fixture
def testence_engine(testence_settings: Settings) -> Iterator[Engine]:
    global _WARM_ENGINE_ANY_FAILED
    mode = (
        "warm"
        if os.environ.get("TESTENCE_WARM_ENGINE") == "1"
        else ("attached" if testence_settings.cdp_url else testence_settings.execution_mode)
    )
    warm = mode == "warm"
    engine = _acquire_warm_engine(testence_settings) if warm else create_engine(testence_settings)
    if warm:
        if hasattr(engine, "reset_session"):
            engine.reset_session()
        else:  # compatibility path for pre-R1 custom engines
            engine.reset_taps()
    else:
        engine.start()
    state: dict[str, Any] = {"any_failed": False, "mode": mode}
    engine._testence_state = state  # type: ignore[attr-defined]
    try:
        yield engine
    finally:
        if warm:
            _WARM_ENGINE_ANY_FAILED = _WARM_ENGINE_ANY_FAILED or state["any_failed"]
        else:
            # CI/default isolation owns and closes its browser even after failure.
            # Attached mode only detaches; the launcher's browser is never ours.
            engine.stop(keep_browser=mode == "attached" and state["any_failed"])


@pytest.fixture
def testence_auth(
    testence_settings: Settings,
    testence_engine: Engine,
    testence_writer: EvidenceWriter,
) -> AuthContext:
    """Authenticated session for one isolated test, using the configured scheme.

    Logged as an evidence event (scheme and names only) so a failed run always
    shows whether it was authenticated — a surprisingly common root cause.
    """
    adapter = from_settings(testence_settings)
    started = time.perf_counter()
    context = adapter.authenticate(testence_engine)
    testence_writer.emit(
        "note",
        text="authenticated",
        auth=context.describe(),
        duration_ms=round((time.perf_counter() - started) * 1000, 1),
    )
    return context


@pytest.fixture
def testence_api(testence_settings: Settings, testence_auth: AuthContext) -> ApiClient:
    """API client sharing the browser's session — for oracles and seeding."""
    return ApiClient.from_settings(testence_settings, testence_auth)


@pytest.fixture
def testence_namespace(
    request: pytest.FixtureRequest,
    testence_settings: Settings,
    testence_writer: EvidenceWriter,
) -> TestNamespace:
    """Stable per-attempt marker for project-owned seed and cleanup adapters."""
    role = str(testence_settings.extra.get("session_expected_role") or "anonymous")
    worker = os.environ.get("PYTEST_XDIST_WORKER", "controller")
    return TestNamespace(
        project_id=testence_settings.project_id,
        run_id=testence_writer.run_id,
        worker_id=worker,
        case_id=source_case_id(request.node.nodeid),
        role=role,
    )


@pytest.fixture
def testence_seed_marker(testence_namespace: TestNamespace) -> str:
    return testence_namespace.marker


@pytest.fixture(scope="session")
def testence_fingerprints(
    request: pytest.FixtureRequest, testence_writer: EvidenceWriter
) -> Iterator[FingerprintStore]:
    """Memory of the last green run, for heal proposals. Lives in the project repo
    so a proposed edit can be read against what the element used to be."""
    store = FingerprintStore(
        Path(request.config.rootpath) / DEFAULT_STORE,
        redact_values=testence_writer.redact_values,
    )
    yield store
    store.flush()


@pytest.fixture
def ex(
    request: pytest.FixtureRequest,
    testence_engine: Engine,
    testence_writer: EvidenceWriter,
    testence_fingerprints: FingerprintStore,
):
    test_id = _test_id(request.node)
    request.node.stash[_ACTIONS_KEY] = actions = Actions(
        testence_engine,
        testence_writer,
        test_id,
        store=testence_fingerprints,
    )
    request.node.stash[_ENGINE_KEY] = testence_engine
    request.node.stash[_FINGERPRINTS_KEY] = testence_fingerprints
    testence_engine.reset_taps()
    started = time.perf_counter()
    try:
        yield actions
    finally:
        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        # Wait budget remains evidence supplied by the browser fixture; the terminal
        # execution outcome is owned by pytest_runtest_protocol.
        ledger = testence_engine.wait_ledger() if hasattr(testence_engine, "wait_ledger") else []
        if ledger:
            waited_ms = round(sum(entry["ms"] for entry in ledger), 1)
            top = sorted(ledger, key=lambda entry: -entry["ms"])[:5]
            by_op: dict[str, dict[str, float]] = {}
            for entry in ledger:
                row = by_op.setdefault(entry["op"], {"ms": 0.0, "n": 0})
                row["ms"] = round(row["ms"] + entry["ms"], 1)
                row["n"] += 1
            testence_writer.emit(
                "test.waits",
                test=test_id,
                waited_ms=waited_ms,
                ops=len(ledger),
                by_op=by_op,
                top=top,
            )
            _RUN_WAITS.append(
                {
                    "test": test_id,
                    "wall_ms": duration_ms,
                    "waited_ms": waited_ms,
                    "top": top,
                    "by_op": by_op,
                }
            )
