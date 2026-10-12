"""One selected case, explicit parallel opt-in, bounded failure details."""

from __future__ import annotations

import json
import sys
import tempfile
import time
from importlib.metadata import version
from pathlib import Path
from typing import Any

from testence._process import run_owned
from testence.config import Settings
from testence.evidence import new_run_id
from testence.evidence.reader import read_run_ledgers
from testence.evidence.sanitize import sanitize
from testence.managed_paths import checked_member


def _settings(project: Path, profile: str) -> Settings:
    try:
        settings = Settings.load(project, profile=profile) if profile else Settings.load(project)
        settings.redaction_policy()
        settings.redaction_values()
        return settings
    except ValueError as exc:
        raise ValueError(
            "cannot read project status/debug: fix settings and redaction configuration"
        ) from exc


def project_status(project: Path, profile: str = "") -> dict[str, Any]:
    import testence

    settings = _settings(project, profile)
    files = [name for name in ("testence.json", "testence.toml") if (project / name).is_file()]
    return sanitize(
        {
            "version": testence.__version__,
            "package_path": str(Path(testence.__file__).parent),
            "python": sys.executable,
            "project": str(project.resolve()),
            "settings_files": files,
            "settings": settings.describe(),
            "runs_root": str((project / settings.runs_root).resolve()),
            "previous_name": "Exhibit",
            "legacy_package": "stf_autotests",
            "parallel": settings.extra.get("parallel", {}),
            "scope": "not collected; debug preflight reports exact selected nodes",
        },
        secrets=settings.redaction_values(),
        policy=settings.redaction_policy(),
    )


def debug(
    project: Path,
    node: str,
    *,
    profile: str = "",
    workers: int = 1,
    allow_multiple: bool = False,
    timeout_s: int = 300,
    browser_reuse: bool = False,
) -> dict[str, Any]:
    from testence.application import inspect_run

    if not node or node.startswith("-"):
        raise ValueError("debug requires a pytest node or file")
    if type(workers) is not int or not 1 <= workers <= 16:
        raise ValueError("workers must be an integer from 1 to 16")
    if type(timeout_s) is not int or not 1 <= timeout_s <= 900:
        raise ValueError("timeout must be an integer from 1 to 900 seconds")
    if type(browser_reuse) is not bool:
        raise ValueError("browser_reuse must be a boolean")
    project = project.resolve()
    settings = _settings(project, profile)
    started = time.monotonic()
    run_id = new_run_id()
    root = (project / settings.runs_root).resolve()
    run_dir = root / run_id
    common = [
        "--rootdir",
        str(project),
        "--testence-headless",
        "--testence-runs-root",
        str(root),
        "-q",
    ]
    if browser_reuse:
        common.append("--testence-browser-reuse")
    if profile:
        common.extend(["--testence-profile", profile])
    result: dict[str, Any] = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "executed": False,
        "workers": workers,
        "selected": [],
        "exit_code": 2,
    }
    with tempfile.TemporaryDirectory(prefix="testence-debug-") as temporary:
        selection = Path(temporary) / "selection.json"
        command = [sys.executable, "-m", "testence.debug_worker", "--selection", str(selection)]
        collected = run_owned(
            [*command, "--run-id", run_id + "-collection", "--", node, *common, "--collect-only"],
            cwd=project,
            timeout=timeout_s,
        )
        result["collection_ms"] = round((time.monotonic() - started) * 1000, 1)
        result["output_tail"] = collected.stdout + collected.stderr
        if collected.returncode != 0 or not selection.is_file():
            result.update(error="collection did not complete", timed_out=collected.timed_out)
        else:
            nodes = json.loads(selection.read_text(encoding="utf-8"))["nodes"]
            result["selected"] = [item["nodeid"] for item in nodes]
            problem = ""
            if not nodes:
                problem = "no tests selected"
            elif len(nodes) != 1 and not allow_multiple:
                problem = (
                    f"selected {len(nodes)} cases; choose one exact node or use --allow-multiple"
                )
            elif workers > 1:
                policy = settings.extra.get("parallel", {})
                if (
                    not isinstance(policy, dict)
                    or policy.get("enabled") is not True
                    or policy.get("accounts") not in ("isolated", "non-revoking")
                    or policy.get("cleanup") != "asserted-absence"
                ):
                    problem = "parallel requires extra.parallel enabled, isolated/non-revoking accounts and asserted-absence cleanup"
                elif not all(
                    item["parallel_declared"] and item["namespace_fixture"] for item in nodes
                ):
                    problem = "parallel requires @pytest.mark.testence_parallel and testence_namespace for every selected case"
                else:
                    try:
                        version("pytest-xdist")
                    except Exception:
                        problem = "parallel requires pytest-xdist"
            if problem:
                result["error"] = problem
            else:
                run_args = [*common, "--durations=10"]
                if workers > 1:
                    run_args.extend(["-n", str(workers)])
                executed = run_owned(
                    [*command, "--verify", "--run-id", run_id, "--", node, *run_args],
                    cwd=project,
                    timeout=timeout_s,
                )
                result.update(
                    executed=True,
                    exit_code=executed.returncode,
                    timed_out=executed.timed_out,
                    output_tail=executed.stdout + executed.stderr,
                )
                if run_dir.is_dir():
                    try:
                        result["summary"] = inspect_run(run_dir)
                        result["phases"] = phase_timings(read_run_ledgers(run_dir))
                    except Exception as exc:
                        result["summary"] = {"error": f"{type(exc).__name__}: {exc}"}
                    packs = []
                    for relative in result["summary"].get("packs", [])[:10]:
                        if not relative:
                            continue
                        portable = Path(relative).as_posix()
                        aria = checked_member(run_dir, portable + "/aria.txt")
                        triage = checked_member(run_dir, portable + "/TRIAGE.md")
                        packs.append(
                            {
                                "path": relative,
                                "aria": aria.read_text(encoding="utf-8")[:20000]
                                if aria.is_file()
                                else "",
                                "triage": triage.read_text(encoding="utf-8")[:10000]
                                if triage.is_file()
                                else "",
                            }
                        )
                    result["failure_packs"] = packs
                if executed.timed_out:
                    result["error"] = "deadline expired; execution incomplete"
                    result["exit_code"] = 124
    result["elapsed_ms"] = round((time.monotonic() - started) * 1000, 1)
    return sanitize(
        result, secrets=settings.redaction_values(), policy=settings.redaction_policy(), limit=20000
    )


def phase_timings(events: list[dict[str, Any]]) -> dict[str, Any]:
    phases: dict[str, float] = {}
    steps: dict[str, float] = {}
    waits: dict[str, float] = {}
    workers: set[str] = set()
    wall_ms = 0.0
    for event in events:
        if event.get("kind") == "test.waits":
            for name, data in event.get("by_op", {}).items():
                waits[name] = waits.get(name, 0) + float(data.get("ms", 0))
        if event.get("kind") == "run.end":
            worker = event.get("worker") or "controller"
            if worker == "controller":
                wall_ms = float(event.get("duration_ms", 0))
            else:
                workers.add(str(worker))
        if event.get("kind") == "test.phase":
            name = str(event.get("phase"))
            phases[name] = phases.get(name, 0) + float(event.get("duration_ms", 0))
        if event.get("kind") == "note" and event.get("lifecycle_phase"):
            name = str(event["lifecycle_phase"])
            steps[name] = steps.get(name, 0) + float(event.get("duration_ms", 0))
    goto_ms = waits.get("goto", 0)
    total_wait_ms = sum(waits.values())
    return {
        "test_phase_ms": phases,
        "lifecycle_ms": steps,
        "wait_ops_ms": waits,
        "navigation": {
            "goto_ms": goto_ms,
            "percent_of_recorded_waits": round(100 * goto_ms / total_wait_ms, 1)
            if total_wait_ms
            else None,
            "percent_of_serial_run_wall": round(100 * goto_ms / wall_ms, 1)
            if wall_ms and len(workers) <= 1
            else None,
        },
        "note": "lifecycle phases are nested within test phases; never add the two totals",
    }
