"""Pytest integration: per-run ledger, per-test evidence, failure packs.

Wiring: ``testence_writer`` (session) opens run.jsonl and stamps the environment
fingerprint; ``ex`` (function) gives the test an :class:`~testence.dsl.Actions`
bound to the shared engine, resets capture buffers, and on failure assembles the
evidence pack. The browser is kept alive at session end if anything failed —
the failure state is evidence (ADR-0008).
"""

from __future__ import annotations

import hashlib
import os
import platform
import time
from pathlib import Path
from typing import Any

import pytest

from testence import __version__, kernels
from testence.api import ApiClient
from testence.auth import AuthContext, from_settings
from testence.config import Settings
from testence.dsl import Actions
from testence.engine import Engine, create_engine
from testence.evidence import RUN_ID_ENV, EvidenceWriter, new_run_id
from testence.fingerprints import DEFAULT_STORE, FingerprintStore
from testence.triage import assemble_pack
from testence.triage.heal import propose


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("testence")
    group.addoption("--testence-base-url", default=None,
                    help="target server; overrides settings/env")
    group.addoption("--testence-profile", default=None,
                    help="settings profile to use (e.g. staging, local)")
    group.addoption("--testence-auth", default=None,
                    help="auth scheme: none|form|api-session|bearer|basic|attached")
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


def pytest_configure(config: pytest.Config) -> None:
    """Name the run before xdist spawns anyone.

    Workers are subprocesses of this process, so an environment variable set here
    reaches all of them — which is how every worker writes its ledger into one run
    directory instead of inventing a directory each. ``setdefault``: a worker runs
    this hook too and must keep the inherited value.
    """
    os.environ.setdefault(RUN_ID_ENV, new_run_id())


def _code_hash(path: Any) -> str:
    """Short digest of the file a test is defined in.

    Scopes flakiness to one version of the test: a case that goes fail -> pass while
    being authored has changed code, and calling that a flake made the suite's own
    metric read 44.4 % where nothing had ever flapped.
    """
    try:
        return hashlib.sha256(Path(str(path)).read_bytes()).hexdigest()[:12]
    except OSError:
        return ""


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]):
    outcome = yield
    report = outcome.get_result()
    item.stash.setdefault(_REPORTS_KEY, {})[report.when] = report  # type: ignore[misc]


_REPORTS_KEY = pytest.StashKey[dict]()

#: Per-test wait budgets for the end-of-run summary (reset per pytest process).
_RUN_WAITS: list[dict[str, Any]] = []


def pytest_terminal_summary(terminalreporter: Any) -> None:
    """One table answering "where did the time go" — the wait ledger, aggregated."""
    if not _RUN_WAITS:
        return
    write = terminalreporter.write_line
    total_wall = sum(row["wall_ms"] for row in _RUN_WAITS)
    total_wait = sum(row["waited_ms"] for row in _RUN_WAITS)
    write("")
    write(f"testence wait budget: {total_wait / 1000:.1f}s waited of "
          f"{total_wall / 1000:.1f}s test wall-clock")

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
        write(f"  {op:22s} {stats['ms'] / 1000:6.1f}s  x{int(stats['n']):<4d} "
              f"{share:4.0f}%  avg {stats['ms'] / max(stats['n'], 1):5.0f}ms")

    for row in sorted(_RUN_WAITS, key=lambda r: -r["waited_ms"])[:10]:
        worst = row["top"][0] if row["top"] else {"op": "-", "detail": "", "ms": 0}
        write(f"  {row['test']}: waited {row['waited_ms'] / 1000:.1f}s "
              f"of {row['wall_ms'] / 1000:.1f}s "
              f"(worst: {worst['op']} {worst['detail'][:60]} {worst['ms']:.0f}ms)")


@pytest.fixture(scope="session")
def testence_settings(request: pytest.FixtureRequest) -> Settings:
    """Resolved configuration: settings file → .env → env → CLI flags."""
    config = request.config
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


@pytest.fixture(scope="session")
def testence_writer(testence_settings: Settings):
    writer = EvidenceWriter(testence_settings.runs_root)
    writer.emit(
        "run.start",
        testence=__version__,
        fingerprint={
            "os": f"{platform.system()} {platform.release()}",
            "python": platform.python_version(),
            "kernels": kernels.active_backend(),
            # Which worker wrote this ledger, so a merged run stays attributable.
            "worker": writer.worker or "(single)",
            **testence_settings.describe(),
        },
    )
    started = time.perf_counter()
    counts = {"passed": 0, "failed": 0}
    writer.counts = counts  # type: ignore[attr-defined]
    yield writer
    writer.emit(
        "run.end",
        duration_ms=round((time.perf_counter() - started) * 1000, 1),
        **counts,
    )
    writer.close()


@pytest.fixture(scope="session")
def testence_engine(testence_settings: Settings):
    engine = create_engine(testence_settings)
    engine.start()
    state = {"any_failed": False}
    engine._testence_state = state  # type: ignore[attr-defined]
    yield engine
    engine.stop(keep_browser=state["any_failed"])


@pytest.fixture(scope="session")
def testence_auth(
    testence_settings: Settings,
    testence_engine: Engine,
    testence_writer: EvidenceWriter,
) -> AuthContext:
    """Authenticated session, once per run, per the configured scheme.

    Logged as an evidence event (scheme and names only) so a failed run always
    shows whether it was authenticated — a surprisingly common root cause.
    """
    adapter = from_settings(testence_settings)
    started = time.perf_counter()
    context = adapter.authenticate(testence_engine)
    testence_writer.emit(
        "note", text="authenticated", auth=context.describe(),
        duration_ms=round((time.perf_counter() - started) * 1000, 1),
    )
    return context


@pytest.fixture(scope="session")
def testence_api(testence_settings: Settings, testence_auth: AuthContext) -> ApiClient:
    """API client sharing the browser's session — for oracles and seeding."""
    return ApiClient.from_settings(testence_settings, testence_auth)


@pytest.fixture(scope="session")
def testence_fingerprints(request: pytest.FixtureRequest) -> FingerprintStore:
    """Memory of the last green run, for heal proposals. Lives in the project repo
    so a proposed edit can be read against what the element used to be."""
    store = FingerprintStore(Path(request.config.rootpath) / DEFAULT_STORE)
    yield store
    store.flush()


@pytest.fixture
def ex(
    request: pytest.FixtureRequest,
    testence_engine: Engine,
    testence_writer: EvidenceWriter,
    testence_fingerprints: FingerprintStore,
):
    test_id = request.node.name
    node_path = getattr(request.node, "path", "")
    testence_engine.reset_taps()
    # `nodeid` and `markers` exist for the exporters (ADR-0013): a reporting format
    # needs the test's full address and the suite's own marker taxonomy. This is how
    # an integration gets data — by appending fields to the ledger, never by asking
    # test authors to instrument their code.
    testence_writer.emit(
        "test.start",
        test=test_id,
        file=str(node_path),
        code=_code_hash(node_path),
        nodeid=request.node.nodeid,
        markers=sorted({mark.name for mark in request.node.iter_markers()}),
    )
    started = time.perf_counter()
    actions = Actions(testence_engine, testence_writer, test_id, store=testence_fingerprints)

    yield actions

    reports = request.node.stash.get(_REPORTS_KEY, {})
    call_report = reports.get("call")
    failed = bool(call_report and call_report.failed)
    duration_ms = round((time.perf_counter() - started) * 1000, 1)

    # Wait budget: what this test actually spent its wall-clock on. Emitted into
    # evidence AND accumulated for the terminal summary — a slow suite must show
    # its receipts without anyone re-running it under a profiler.
    ledger = testence_engine.wait_ledger() if hasattr(testence_engine, "wait_ledger") else []
    if ledger:
        waited_ms = round(sum(entry["ms"] for entry in ledger), 1)
        top = sorted(ledger, key=lambda entry: -entry["ms"])[:5]
        # Per-operation totals, not just the top five: a case with 59 waits showed
        # five of them and hid the rest, so "where did the time go" still needed a
        # re-run under a profiler. With this, the ledger answers it by itself.
        by_op: dict[str, dict[str, float]] = {}
        for entry in ledger:
            row = by_op.setdefault(entry["op"], {"ms": 0.0, "n": 0})
            row["ms"] = round(row["ms"] + entry["ms"], 1)
            row["n"] += 1
        testence_writer.emit("test.waits", test=test_id, waited_ms=waited_ms,
                            ops=len(ledger), by_op=by_op, top=top)
        _RUN_WAITS.append({"test": test_id, "wall_ms": duration_ms,
                           "waited_ms": waited_ms, "top": top, "by_op": by_op})
    if failed:
        testence_writer.counts["failed"] += 1  # type: ignore[attr-defined]
        testence_engine._testence_state["any_failed"] = True  # type: ignore[attr-defined]
        crash = getattr(getattr(call_report, "longrepr", None), "reprcrash", None)
        error = getattr(crash, "message", None) or (
            str(call_report.longrepr)[-2000:] if call_report else "unknown"
        )
        heal = None
        failure = actions.last_failure
        if failure is not None and failure.target is not None:
            known = testence_fingerprints.get(test_id, failure.intent)
            heal = propose(testence_engine, failure.intent, failure.target, known)
        pack_dir = assemble_pack(
            testence_engine, testence_writer, test_id, error=error, heal=heal
        )
        testence_writer.emit(
            "test.end", test=test_id, status="fail", duration_ms=duration_ms,
            pack=str(pack_dir.relative_to(testence_writer.run_dir)),
        )
    else:
        testence_writer.counts["passed"] += 1  # type: ignore[attr-defined]
        testence_writer.emit("test.end", test=test_id, status="pass", duration_ms=duration_ms)
