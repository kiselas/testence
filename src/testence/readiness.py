"""Fail-fast authoring readiness for PlanSpec scenarios.

The browser is deliberately absent from this module.  Readiness answers the cheaper
question first: does this target have the routes, fixtures, credentials, capabilities,
and oracle adapters needed to author the requested scenarios honestly?
"""

from __future__ import annotations

import json
import os
import ssl
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urlsplit, urlunsplit

from .config import Settings
from .contracts import READINESS_REPORT_SCHEMA, PlanSpec, load_plan
from .engine import create_engine, engine_capabilities

_BUILTIN_ORACLES = {
    "ui": "browser.dom",
    "network": "browser.network",
}
_CHECK_TYPES = frozenset({"env", "file", "http"})


class ReadinessError(ValueError):
    """The readiness configuration is invalid and no result can be trusted."""


@dataclass(frozen=True)
class ReadinessConfig:
    checks: tuple[dict[str, Any], ...]
    scenarios: dict[str, tuple[str, ...]]
    oracle_adapters: frozenset[str]
    require_scenario_checks: bool


def _strings(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ReadinessError(f"{label} must be an array of non-empty strings")
    if len(set(value)) != len(value):
        raise ReadinessError(f"{label} must not contain duplicates")
    return tuple(value)


def _load_config(settings: Settings, plan: PlanSpec) -> ReadinessConfig:
    raw = settings.extra.get("readiness")
    if raw is None:
        raw = {
            "schema": "testence/readiness/1",
            "checks": [],
            "scenarios": {},
            "oracle_adapters": [],
        }
    if not isinstance(raw, dict):
        raise ReadinessError("testence settings must define a readiness object")
    unknown = sorted(
        set(raw) - {"schema", "checks", "scenarios", "oracle_adapters", "require_scenario_checks"}
    )
    if unknown:
        raise ReadinessError("readiness has unknown field(s): " + ", ".join(unknown))
    if raw.get("schema") != "testence/readiness/1":
        raise ReadinessError("readiness.schema must be 'testence/readiness/1'")

    raw_checks = raw.get("checks", [])
    if not isinstance(raw_checks, list):
        raise ReadinessError("readiness.checks must be an array")
    checks: list[dict[str, Any]] = []
    ids: set[str] = set()
    for index, item in enumerate(raw_checks):
        label = f"readiness.checks[{index}]"
        if not isinstance(item, dict):
            raise ReadinessError(f"{label} must be an object")
        check_id = item.get("id")
        kind = item.get("type")
        if not isinstance(check_id, str) or not check_id:
            raise ReadinessError(f"{label}.id must be a non-empty string")
        if check_id in ids:
            raise ReadinessError(f"readiness check ID {check_id!r} is duplicated")
        if kind not in _CHECK_TYPES:
            raise ReadinessError(f"{label}.type must be one of: {', '.join(sorted(_CHECK_TYPES))}")
        allowed = {
            "env": {"id", "type", "variables", "fix"},
            "file": {"id", "type", "path", "fix"},
            "http": {
                "id",
                "type",
                "url",
                "path",
                "status",
                "timeout_ms",
                "json_pointer",
                "equals",
                "fix",
            },
        }[kind]
        extra = sorted(set(item) - allowed)
        if extra:
            raise ReadinessError(f"{label} has unknown field(s): {', '.join(extra)}")
        if "fix" in item:
            _validate_fix(item["fix"], f"{label}.fix")
        ids.add(check_id)
        checks.append(dict(item))

    raw_scenarios = raw.get("scenarios", {})
    if not isinstance(raw_scenarios, dict):
        raise ReadinessError("readiness.scenarios must be an object")
    scenarios: dict[str, tuple[str, ...]] = {}
    for scenario_id, references in raw_scenarios.items():
        parsed = _strings(references, f"readiness.scenarios.{scenario_id}")
        unknown_checks = sorted(set(parsed) - ids)
        if unknown_checks:
            raise ReadinessError(
                f"readiness.scenarios.{scenario_id} references unknown check(s): "
                + ", ".join(unknown_checks)
            )
        scenarios[scenario_id] = parsed

    adapters = frozenset(_strings(raw.get("oracle_adapters", []), "readiness.oracle_adapters"))
    unknown_oracles = sorted(adapters - {"api", "a11y", "custom", "visual"})
    if unknown_oracles:
        raise ReadinessError("unknown oracle adapter(s): " + ", ".join(unknown_oracles))
    strict = raw.get("require_scenario_checks", True)
    if not isinstance(strict, bool):
        raise ReadinessError("readiness.require_scenario_checks must be a boolean")
    return ReadinessConfig(tuple(checks), scenarios, adapters, strict)


def _validate_fix(value: Any, label: str) -> None:
    if not isinstance(value, dict):
        raise ReadinessError(f"{label} must be an object")
    unknown = sorted(set(value) - {"argv", "cwd", "timeout_ms"})
    if unknown:
        raise ReadinessError(f"{label} has unknown field(s): {', '.join(unknown)}")
    argv = _strings(value.get("argv"), f"{label}.argv")
    if not argv or len(argv) > 64 or any(len(part) > 2_000 for part in argv):
        raise ReadinessError(f"{label}.argv must contain 1..64 bounded arguments")
    cwd = value.get("cwd", ".")
    if not isinstance(cwd, str) or not cwd:
        raise ReadinessError(f"{label}.cwd must be a non-empty string")
    timeout_ms = value.get("timeout_ms", 120_000)
    if not isinstance(timeout_ms, int) or not 100 <= timeout_ms <= 900_000:
        raise ReadinessError(f"{label}.timeout_ms must be 100..900000")


def _json_pointer(document: Any, pointer: str) -> tuple[bool, Any]:
    if pointer == "":
        return True, document
    if not pointer.startswith("/"):
        raise ReadinessError("http check json_pointer must be empty or start with '/'")
    current = document
    for raw_part in pointer[1:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        try:
            current = current[int(part)] if isinstance(current, list) else current[part]
        except (IndexError, KeyError, TypeError, ValueError):
            return False, None
    return True, current


def _safe_url(url: str) -> str:
    """Remove query material and user info before a target URL enters a report."""

    parsed = urlsplit(url)
    host = parsed.hostname or ""
    if parsed.port is not None:
        host += f":{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))


def _run_check(check: dict[str, Any], *, project: Path, settings: Settings) -> tuple[bool, str]:
    kind = check["type"]
    if kind == "env":
        variables = _strings(check.get("variables"), f"readiness check {check['id']}.variables")
        missing = [
            name
            for name in variables
            if not (os.environ.get(name) or settings.env_values.get(name))
        ]
        return (
            (False, "missing environment variable(s): " + ", ".join(missing))
            if missing
            else (True, f"{len(variables)} required environment variable(s) are set")
        )

    if kind == "file":
        raw_path = check.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            raise ReadinessError(f"readiness check {check['id']}.path must be a non-empty string")
        path = (project / raw_path).resolve()
        if path != project and project not in path.parents:
            raise ReadinessError(f"readiness check {check['id']}.path leaves the project root")
        return path.is_file(), f"file {'exists' if path.is_file() else 'is missing'}: {raw_path}"

    path_or_url = check.get("url", check.get("path"))
    if not isinstance(path_or_url, str) or not path_or_url:
        raise ReadinessError(f"readiness check {check['id']} needs url or path")
    if not urlparse(path_or_url).scheme and not settings.base_url:
        raise ReadinessError(
            f"readiness check {check['id']} uses a relative path but profile base_url is empty"
        )
    url = urljoin(settings.base_url.rstrip("/") + "/", path_or_url.lstrip("/"))
    if urlparse(url).scheme not in {"http", "https"}:
        raise ReadinessError(f"readiness check {check['id']} URL must use http or https")
    report_url = _safe_url(url)
    statuses_raw = check.get("status", 200)
    statuses = {statuses_raw} if isinstance(statuses_raw, int) else set(statuses_raw or [])
    if not statuses or not all(isinstance(item, int) and 100 <= item <= 599 for item in statuses):
        raise ReadinessError(
            f"readiness check {check['id']}.status must be an HTTP status or array"
        )
    timeout_ms = check.get("timeout_ms", min(settings.timeout_ms, 5_000))
    if not isinstance(timeout_ms, int) or not 100 <= timeout_ms <= 30_000:
        raise ReadinessError(f"readiness check {check['id']}.timeout_ms must be 100..30000")
    context = None
    if not settings.verify_tls:
        context = ssl._create_unverified_context()  # noqa: SLF001 - mirrors browser setting
    elif settings.ca_bundle:
        context = ssl.create_default_context(cafile=settings.ca_bundle)
    request = urllib.request.Request(url, method="GET")
    try:
        response = urllib.request.urlopen(request, timeout=timeout_ms / 1000, context=context)
    except urllib.error.HTTPError as exc:
        response = exc
    except (OSError, TimeoutError) as exc:
        return False, f"GET {report_url} failed: {type(exc).__name__}"
    with response:
        status = int(response.status)
        body = response.read(1_048_577)
    if status not in statuses:
        return False, f"GET {report_url} returned {status}; expected {sorted(statuses)}"
    pointer = check.get("json_pointer")
    if pointer is not None:
        if not isinstance(pointer, str):
            raise ReadinessError(f"readiness check {check['id']}.json_pointer must be a string")
        if len(body) > 1_048_576:
            return False, f"GET {report_url} response exceeds 1 MiB"
        try:
            document = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False, f"GET {report_url} did not return JSON"
        found, value = _json_pointer(document, pointer)
        if not found:
            return False, f"GET {report_url} has no JSON pointer {pointer}"
        if "equals" in check and value != check["equals"]:
            return False, f"GET {report_url} JSON pointer {pointer} has an unexpected value"
    return True, f"GET {report_url} returned {status}"


def _apply_fix(check: dict[str, Any], *, project: Path) -> dict[str, Any]:
    fix = check["fix"]
    cwd = (project / fix.get("cwd", ".")).resolve()
    if cwd != project and project not in cwd.parents:
        raise ReadinessError(f"readiness check {check['id']}.fix.cwd leaves the project root")
    if not cwd.is_dir():
        raise ReadinessError(f"readiness check {check['id']}.fix.cwd is not a directory")
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            list(fix["argv"]),
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=fix.get("timeout_ms", 120_000) / 1000,
        )
        status = "applied" if completed.returncode == 0 else "failed"
        exit_code: int | None = int(completed.returncode)
    except (OSError, subprocess.TimeoutExpired):
        status = "failed"
        exit_code = None
    return {
        "check_id": check["id"],
        "status": status,
        "exit_code": exit_code,
        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
    }


def prepare_plan(
    plan_path: Path | str,
    project: Path | str = ".",
    *,
    profile: str | None = None,
    backend: str = "playwright-cdp",
    apply_fixes: bool = False,
) -> dict[str, Any]:
    """Return a bounded, secret-safe readiness report without starting a browser."""

    started = time.perf_counter()
    phase_started = started
    plan = load_plan(plan_path)
    timings = {"plan_ms": round((time.perf_counter() - phase_started) * 1000, 1)}

    root = Path(project).resolve()
    phase_started = time.perf_counter()
    settings = Settings.load(root, profile=profile)
    config = _load_config(settings, plan)
    timings["configuration_ms"] = round((time.perf_counter() - phase_started) * 1000, 1)
    if settings.project_id != plan.project_id:
        raise ReadinessError(
            f"profile project_id {settings.project_id!r} does not match plan {plan.project_id!r}"
        )

    phase_started = time.perf_counter()
    engine = create_engine(settings, backend=backend)
    capabilities = engine_capabilities(engine)
    timings["capabilities_ms"] = round((time.perf_counter() - phase_started) * 1000, 1)
    available_oracles = set(config.oracle_adapters)
    available_oracles.update(
        oracle for oracle, capability in _BUILTIN_ORACLES.items() if capability in capabilities
    )

    phase_started = time.perf_counter()
    results: dict[str, dict[str, Any]] = {}
    for check in config.checks:
        check_started = time.perf_counter()
        try:
            ok, detail = _run_check(check, project=root, settings=settings)
        except ReadinessError:
            raise
        except Exception as exc:
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        results[check["id"]] = {
            "id": check["id"],
            "type": check["type"],
            "ok": ok,
            "detail": detail,
            "duration_ms": round((time.perf_counter() - check_started) * 1000, 1),
        }
    timings["checks_ms"] = round((time.perf_counter() - phase_started) * 1000, 1)

    phase_started = time.perf_counter()
    fixes: list[dict[str, Any]] = []
    if apply_fixes:
        for check in config.checks:
            if results[check["id"]]["ok"] or "fix" not in check:
                continue
            fixes.append(_apply_fix(check, project=root))
            check_started = time.perf_counter()
            ok, detail = _run_check(check, project=root, settings=settings)
            fixes[-1]["check_ok_after"] = ok
            results[check["id"]] = {
                "id": check["id"],
                "type": check["type"],
                "ok": ok,
                "detail": detail,
                "duration_ms": round((time.perf_counter() - check_started) * 1000, 1),
            }
    timings["fixes_ms"] = round((time.perf_counter() - phase_started) * 1000, 1)

    required_oracles: dict[str, set[str]] = {}
    for assertion in plan.assertions:
        if assertion.required:
            required_oracles.setdefault(assertion.claim_id, set()).add(assertion.oracle)
    scenarios = []
    for scenario in plan.scenarios:
        blockers: list[dict[str, str]] = []
        missing_capabilities = sorted(set(scenario.capabilities) - capabilities)
        if missing_capabilities:
            blockers.append(
                {
                    "kind": "capability",
                    "detail": "missing engine capability: " + ", ".join(missing_capabilities),
                }
            )
        needed_oracles = set().union(
            *(required_oracles.get(claim, set()) for claim in scenario.claims)
        )
        missing_oracles = sorted(needed_oracles - available_oracles)
        if missing_oracles:
            blockers.append(
                {
                    "kind": "oracle",
                    "detail": "missing oracle adapter: " + ", ".join(missing_oracles),
                }
            )
        references = config.scenarios.get(scenario.id)
        if references is None and config.require_scenario_checks:
            blockers.append(
                {"kind": "configuration", "detail": "scenario has no readiness check mapping"}
            )
        for check_id in references or ():
            if not results[check_id]["ok"]:
                blockers.append(
                    {"kind": "check", "check_id": check_id, "detail": results[check_id]["detail"]}
                )
        scenarios.append(
            {
                "id": scenario.id,
                "status": "ready" if not blockers else "blocked",
                "checks": list(references or ()),
                "blockers": blockers,
            }
        )

    ready = sum(item["status"] == "ready" for item in scenarios)
    timings["total_ms"] = round((time.perf_counter() - started) * 1000, 1)
    return {
        "schema": READINESS_REPORT_SCHEMA,
        "status": "ready" if ready == len(scenarios) else "blocked",
        "plan": {"id": plan.id, "digest": plan.digest},
        "profile": settings.profile or "(default)",
        "backend": backend,
        "capabilities": sorted(capabilities),
        "oracle_adapters": sorted(available_oracles),
        "checks": list(results.values()),
        "fixes": fixes,
        "scenarios": scenarios,
        "summary": {"ready": ready, "blocked": len(scenarios) - ready, "total": len(scenarios)},
        "timings": timings,
    }
