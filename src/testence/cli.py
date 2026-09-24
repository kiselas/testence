"""``testence`` CLI: metrics, reports, benchmarks and fast authoring loops.

Cross-platform by construction: pure Python entry points, no shell wrappers
(Windows, Linux and macOS are all first-class platforms, locally and in CI).
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType

from . import __version__
from .metrics import write_metrics
from .report.html import render_report

#: Watch-mode poll interval. A poll loop rather than a filesystem-notification
#: dependency: the whole point is to remove a wait, not to add a package.
_WATCH_POLL_S = 0.4


def _snapshot(roots: list[Path], patterns: list[str]) -> dict[Path, float]:
    seen: dict[Path, float] = {}
    for root in roots:
        for pattern in patterns:
            for path in root.rglob(pattern):
                if "__pycache__" in path.parts or ".venv" in path.parts:
                    continue
                try:
                    seen[path] = path.stat().st_mtime
                except OSError:
                    continue
    return seen


def _pytest_args(cmd: list[str]) -> list[str]:
    """Return pytest arguments for the command shapes warm mode can run safely."""
    if not cmd:
        raise ValueError("empty command")
    executable = Path(cmd[0]).stem.lower()
    if executable in {"pytest", "py.test"}:
        return cmd[1:]
    if len(cmd) >= 3 and executable.startswith("python") and cmd[1:3] == ["-m", "pytest"]:
        return cmd[3:]
    raise ValueError(
        "warm mode only supports `pytest ...` or `python -m pytest ...`; "
        "use regular mode for arbitrary commands"
    )


def _inside(path: Path, roots: list[Path]) -> bool:
    return any(path == root or root in path.parents for root in roots)


def _module_path(module: ModuleType) -> Path | None:
    value = getattr(module, "__file__", None)
    if not value:
        return None
    try:
        return Path(value).resolve()
    except OSError:
        return None


def _evict_project_modules(roots: list[Path]) -> list[str]:
    """Forget project modules so a warm rerun executes the code just saved.

    Testence itself is protected: unloading the CLI or its already-registered pytest
    plugin halfway through the process would combine old objects with new module
    globals. Framework development should use normal subprocess mode; product and test
    modules under the selected roots are safe to reload.
    """
    resolved = [root.resolve() for root in roots if root.exists()]
    protected = Path(__file__).resolve().parent
    evicted: list[str] = []
    for name, module in list(sys.modules.items()):
        if not isinstance(module, ModuleType) or name == "__main__":
            continue
        path = _module_path(module)
        if path is None or not _inside(path, resolved) or _inside(path, [protected]):
            continue
        sys.modules.pop(name, None)
        evicted.append(name)
    importlib.invalidate_caches()
    return sorted(evicted)


class _WarmPytestRunner:
    """Several isolated pytest sessions inside one Python interpreter."""

    def __init__(
        self,
        cmd: list[str],
        reload_roots: list[Path],
        *,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self.pytest_args = _pytest_args(cmd)
        self.reload_roots = reload_roots
        self.env = dict(env or {})
        self.runs = 0

    def run(
        self,
        *,
        run_id: str | None = None,
        extra_env: Mapping[str, str] | None = None,
    ) -> int:
        import pytest

        from testence.evidence import RUN_ID_ENV, new_run_id

        if self.runs:
            evicted = _evict_project_modules(self.reload_roots)
            print(f"[warm] reloaded {len(evicted)} project module(s)")
        self.runs += 1

        updates = {**self.env, **dict(extra_env or {})}
        updates["TESTENCE_WARM_ENGINE"] = "1"
        updates[RUN_ID_ENV] = run_id or new_run_id()
        previous = {key: os.environ.get(key) for key in updates}
        os.environ.update(updates)
        try:
            return int(pytest.main(self.pytest_args))
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def close(self) -> None:
        """Release process-scoped resources retained across warm sessions."""
        from testence.pytest_plugin import close_warm_engine

        close_warm_engine()


def _watch(
    watch_roots: list[Path],
    patterns: list[str],
    cmd: list[str],
    *,
    warm: bool = False,
) -> int:
    """Re-run ``cmd`` whenever a watched file changes, until interrupted.

    This exists because of where a suite's wall-clock actually goes: across a
    29-minute authoring session the runner accounted for 16 % of it, and the rest
    was the gap between saving a file and asking for a run. Pair it with an
    attached browser (``python -m testence.dev_browser`` plus a ``*-attached``
    profile) and the whole loop is the run itself. ``warm=True`` also keeps the
    Python interpreter and pytest imports alive; project modules are evicted before
    every rerun so saving code still changes what executes.
    """
    print(f"[watch] {' '.join(cmd)}")
    print(
        f"[watch] roots: {', '.join(str(r) for r in watch_roots)} "
        f"({', '.join(patterns)}) — Ctrl+C to stop"
    )
    state = _snapshot(watch_roots, patterns)
    warm_runner = _WarmPytestRunner(cmd, watch_roots) if warm else None
    runs = 0
    try:
        while True:
            runs += 1
            print(f"[watch] run {runs}")
            if warm_runner is not None:
                warm_runner.run()
            else:
                subprocess.run(cmd, check=False)
            print("[watch] waiting for a change...")
            while True:
                time.sleep(_WATCH_POLL_S)
                current = _snapshot(watch_roots, patterns)
                if current != state:
                    changed = [p for p, m in current.items() if state.get(p) != m]
                    state = current
                    for path in changed[:5]:
                        print(f"[watch] changed: {path}")
                    break
    except KeyboardInterrupt:
        print(f"\n[watch] stopped after {runs} run(s)")
    finally:
        if warm_runner is not None:
            warm_runner.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="testence",
        description="Agent-first browser testing with evidence-backed verdicts.",
        epilog=(
            "Start here: doctor, init, run, inspect, report.\n"
            "Authoring: plan, capabilities, watch, bench, demo, agent.\n"
            "Results: export, metrics, verdict, repair, quality, ci, delivery.\n"
            "Testence maintainers only: corpus, release.\n"
            "\n"
            "Exit codes: 0 success, 1 unexpected failure, 2 invalid input or "
            "configuration, 3 a valid answer that blocks the caller (blocked "
            "readiness, failed check, no-go decision)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # Alpha software: every bug report starts with "which version".
    parser.add_argument("--version", action="version", version=f"testence {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_metrics = sub.add_parser("metrics", help="aggregate metrics.json from run dirs")
    p_metrics.add_argument("run_dirs", nargs="+", type=Path)
    p_metrics.add_argument("-o", "--out", type=Path, default=Path("metrics.json"))

    p_report = sub.add_parser("report", help="render a self-contained HTML report")
    p_report.add_argument("run_dir", type=Path, help="run directory to render")
    p_report.add_argument("-o", "--out", type=Path, default=None)

    p_export = sub.add_parser("export", help="render an integration format from a run")
    p_export.add_argument("run_dir", nargs="?", type=Path)
    p_export.add_argument(
        "--to", default=None, metavar="EXPORTER", help="exporter name (see --list)"
    )
    p_export.add_argument("-o", "--out", type=Path, default=None)
    p_export.add_argument(
        "--attachments",
        choices=("full", "minimal", "none"),
        default="full",
        help="pack files to ship: full (redacted), minimal (no network/ARIA/screenshot), none",
    )
    p_export.add_argument(
        "--list", dest="list_", action="store_true", help="list registered exporters and exit"
    )

    p_bench = sub.add_parser("bench", help="run a command N times, then aggregate")
    p_bench.add_argument("-n", "--iterations", type=int, default=10)
    p_bench.add_argument("--runs-root", type=Path, default=Path("runs"))
    p_bench.add_argument(
        "--warm",
        action="store_true",
        help="reuse this Python process between pytest iterations",
    )
    p_bench.add_argument(
        "-w",
        "--reload-root",
        type=Path,
        action="append",
        default=None,
        help="project root whose imported modules warm mode reloads",
    )
    p_bench.add_argument("cmd", nargs=argparse.REMAINDER, help="command to repeat (prefix with --)")

    p_watch = sub.add_parser("watch", help="re-run a command whenever a file changes")
    p_watch.add_argument(
        "-w",
        "--watch",
        type=Path,
        action="append",
        default=None,
        help="directory to watch (repeatable; default: src, tests, examples)",
    )
    p_watch.add_argument(
        "-p",
        "--pattern",
        action="append",
        default=None,
        help="glob to watch (repeatable; default: *.py)",
    )
    p_watch.add_argument(
        "--warm",
        action="store_true",
        help="reuse this Python process; pytest commands only",
    )
    p_watch.add_argument("cmd", nargs=argparse.REMAINDER, help="command to re-run (prefix with --)")

    p_plan = sub.add_parser("plan", help="validate and inspect a PlanSpec")
    plan_sub = p_plan.add_subparsers(dest="plan_command", required=True)
    p_plan_validate = plan_sub.add_parser("validate", help="validate a PlanSpec")
    p_plan_validate.add_argument("path", type=Path, help="PlanSpec markdown or JSON file")
    p_plan_validate.add_argument("--json", dest="json_output", action="store_true")
    p_plan_prepare = plan_sub.add_parser(
        "prepare", help="check scenario readiness before browser authoring"
    )
    p_plan_prepare.add_argument("path", type=Path, help="PlanSpec markdown or JSON file")
    p_plan_prepare.add_argument("--project", type=Path, default=Path("."))
    p_plan_prepare.add_argument("--profile", default=None)
    p_plan_prepare.add_argument("--backend", default="playwright-cdp")
    p_plan_prepare.add_argument(
        "--apply-fixes",
        action="store_true",
        help="run explicitly configured argv fix recipes, then recheck",
    )
    p_plan_prepare.add_argument("--json", dest="json_output", action="store_true")

    p_verdict = sub.add_parser("verdict", help="validate an evidence-backed verdict")
    verdict_sub = p_verdict.add_subparsers(dest="verdict_command", required=True)
    p_verdict_validate = verdict_sub.add_parser("validate", help="validate verdict.json")
    p_verdict_validate.add_argument("path", type=Path)
    p_verdict_validate.add_argument(
        "--pack",
        type=Path,
        default=None,
        help="evidence-pack directory (default: verdict file directory)",
    )
    p_verdict_validate.add_argument("--plan", type=Path, default=None)
    p_verdict_validate.add_argument("--json", dest="json_output", action="store_true")
    p_verdict_submit = verdict_sub.add_parser("submit", help="validate and persist verdict.json")
    p_verdict_submit.add_argument("path", type=Path)
    p_verdict_submit.add_argument("--pack", type=Path, required=True)
    p_verdict_submit.add_argument("--plan", type=Path, required=True)
    p_verdict_submit.add_argument("--out", type=Path, default=None)
    p_verdict_submit.add_argument("--json", dest="json_output", action="store_true")

    p_repair = sub.add_parser("repair", help="validate a bound repair proposal")
    repair_sub = p_repair.add_subparsers(dest="repair_command", required=True)
    p_repair_validate = repair_sub.add_parser("validate", help="validate repair.json")
    p_repair_validate.add_argument("path", type=Path)
    p_repair_validate.add_argument("--verdict", type=Path, required=True)
    p_repair_validate.add_argument("--plan", type=Path, required=True)
    p_repair_validate.add_argument("--base", type=Path, required=True)
    p_repair_validate.add_argument("--pack", type=Path, default=None)
    p_repair_validate.add_argument("--evidence-root", type=Path, required=True)
    p_repair_validate.add_argument("--json", dest="json_output", action="store_true")

    p_ci = sub.add_parser("ci", help="produce a fail-closed CI outcome receipt")
    ci_sub = p_ci.add_subparsers(dest="ci_command", required=True)
    p_ci_evaluate = ci_sub.add_parser("evaluate", help="combine test, quality and delivery")
    p_ci_evaluate.add_argument("run_dir", type=Path)
    p_ci_evaluate.add_argument("--run-id", required=True)
    p_ci_evaluate.add_argument("--test-exit", type=int, required=True)
    p_ci_evaluate.add_argument(
        "--quality-mode", choices=("execution", "assurance"), default="assurance"
    )
    p_ci_evaluate.add_argument("--delivery-receipt", type=Path, default=None)
    p_ci_evaluate.add_argument("--ctrf", type=Path, default=None)
    p_ci_evaluate.add_argument("--junit", type=Path, default=None)
    p_ci_evaluate.add_argument("--allow-empty", action="store_true")
    p_ci_evaluate.add_argument(
        "--testplan-unresolved",
        choices=("warn", "fail"),
        default="warn",
        help="fail when Allure test plan entries matched no collected test (default: warn)",
    )
    p_ci_evaluate.add_argument("-o", "--out", type=Path, required=True)
    p_ci_evaluate.add_argument("--json", dest="json_output", action="store_true")

    p_delivery = sub.add_parser("delivery", help="run an idempotent result delivery")
    delivery_sub = p_delivery.add_subparsers(dest="delivery_command", required=True)
    p_delivery_run = delivery_sub.add_parser("run", help="deliver one explicit run")
    p_delivery_run.add_argument("run_dir", type=Path)
    p_delivery_run.add_argument("--run-id", required=True)
    p_delivery_run.add_argument("--project-id", required=True)
    p_delivery_run.add_argument("--launch-id", required=True)
    p_delivery_run.add_argument("--job-run-id", required=True)
    p_delivery_run.add_argument("--artifact-dir", type=Path, required=True)
    p_delivery_run.add_argument("--receipt", type=Path, required=True)
    p_delivery_run.add_argument("--retries", type=int, default=2)
    p_delivery_run.add_argument("--timeout", type=float, default=60.0)
    p_delivery_run.add_argument("cmd", nargs=argparse.REMAINDER)

    p_doctor = sub.add_parser("doctor", help="check the local Testence runtime")
    p_doctor.add_argument("--root", type=Path, default=Path("."), help="project directory to check")
    p_doctor.add_argument("--json", dest="json_output", action="store_true")

    p_init = sub.add_parser("init", help="create a conflict-safe onboarding scaffold")
    p_init.add_argument(
        "path", type=Path, nargs="?", default=Path("."), help="project directory to scaffold"
    )
    p_init.add_argument("--json", dest="json_output", action="store_true")

    p_run = sub.add_parser("run", help="run the explicit Testence scope")
    p_run.add_argument(
        "--project", type=Path, default=Path("."), help="project whose scaffold to run"
    )
    p_run.add_argument("--run-id", default=None, help="explicit run id; generated when omitted")
    p_run.add_argument("pytest_args", nargs=argparse.REMAINDER)

    p_inspect = sub.add_parser("inspect", help="inspect one explicit run directory")
    p_inspect.add_argument("run_dir", type=Path, help="run directory, for example runs/r-123")
    p_inspect.add_argument("--json", dest="json_output", action="store_true")

    p_demo = sub.add_parser("demo", help="run the deterministic green/failure proof demo")
    demo_sub = p_demo.add_subparsers(dest="demo_command", required=True)
    p_demo_run = demo_sub.add_parser("run", help="create, run and report the local demo")
    p_demo_run.add_argument("--project", type=Path, default=Path("testence-demo"))
    p_demo_run.add_argument("--run-prefix", default=None)
    p_demo_run.add_argument("--json", dest="json_output", action="store_true")

    p_capabilities = sub.add_parser("capabilities", help="inspect engine capabilities")
    p_capabilities.add_argument("--project", type=Path, default=Path("."))
    p_capabilities.add_argument("--backend", default="playwright-cdp")
    p_capabilities.add_argument("--json", dest="json_output", action="store_true")

    p_quality = sub.add_parser("quality", help="manage a versioned multi-project quality pack")
    quality_sub = p_quality.add_subparsers(dest="quality_command", required=True)
    p_quality_apply = quality_sub.add_parser("apply", help="apply a pinned quality pack")
    p_quality_apply.add_argument("pack", type=Path)
    p_quality_apply.add_argument("project", type=Path)
    p_quality_apply.add_argument("--dry-run", action="store_true")
    p_quality_apply.add_argument("--json", dest="json_output", action="store_true")
    p_quality_rollback = quality_sub.add_parser("rollback", help="restore a retained pack revision")
    p_quality_rollback.add_argument("project", type=Path)
    p_quality_rollback.add_argument("--digest", required=True)
    p_quality_rollback.add_argument("--json", dest="json_output", action="store_true")
    p_quality_summary = quality_sub.add_parser("summary", help="build an actionable QA summary")
    p_quality_summary.add_argument("run_dirs", nargs="+", type=Path)
    p_quality_summary.add_argument("--project", default=None)
    p_quality_summary.add_argument("--owner", default=None)
    p_quality_summary.add_argument("--risk", default=None)
    p_quality_summary.add_argument("--case", default=None)
    p_quality_summary.add_argument("-o", "--out", type=Path, default=None)
    p_quality_summary.add_argument("--json", dest="json_output", action="store_true")

    p_agent = sub.add_parser("agent", help="install and verify the bundled agent skill pack")
    agent_sub = p_agent.add_subparsers(dest="agent_command", required=True)
    p_agent_install = agent_sub.add_parser("install", help="install skills for agent clients")
    p_agent_install.add_argument("--project", type=Path, default=Path("."))
    p_agent_install.add_argument(
        "--client", action="append", choices=("codex", "claude"), required=True
    )
    p_agent_install.add_argument("--json", dest="json_output", action="store_true")
    p_agent_verify = agent_sub.add_parser("verify", help="verify installed agent skills")
    p_agent_verify.add_argument("--project", type=Path, default=Path("."))
    p_agent_verify.add_argument(
        "--client", action="append", choices=("codex", "claude"), default=[]
    )
    p_agent_verify.add_argument("--json", dest="json_output", action="store_true")

    p_corpus = sub.add_parser(
        "corpus", help="Testence maintainers: validate the frozen correctness corpus"
    )
    corpus_sub = p_corpus.add_subparsers(dest="corpus_command", required=True)
    p_corpus_validate = corpus_sub.add_parser("validate", help="validate corpus structure/freeze")
    p_corpus_validate.add_argument("path", type=Path)
    p_corpus_validate.add_argument("--root", type=Path, default=None)
    p_corpus_validate.add_argument("--structure-only", action="store_true")
    p_corpus_validate.add_argument("--json", dest="json_output", action="store_true")

    p_release = sub.add_parser(
        "release", help="Testence maintainers: validate a release decision manifest"
    )
    release_sub = p_release.add_subparsers(dest="release_command", required=True)
    p_release_validate = release_sub.add_parser("validate", help="validate manifest and evidence")
    p_release_validate.add_argument("path", type=Path)
    p_release_validate.add_argument("--root", type=Path, default=Path("."))
    p_release_validate.add_argument("--structure-only", action="store_true")
    p_release_validate.add_argument("--json", dest="json_output", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "metrics":
        doc = write_metrics(args.run_dirs, args.out)
        print(f"metrics -> {args.out}")
        print(doc)
        return 0

    if args.command == "report":
        out = args.out or (args.run_dir / "report.html")
        render_report(args.run_dir, out)
        print(f"report -> {out}")
        return 0

    if args.command == "doctor":
        from .application import doctor

        result = doctor(args.root)
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        else:
            for check in result["checks"]:
                print(f"{'ok' if check['ok'] else 'FAIL':4} {check['name']}: {check['detail']}")
        return 0 if result["ok"] else 2

    if args.command == "init":
        from .application import ApplicationError, init_project

        try:
            result = init_project(args.path)
        except (ApplicationError, OSError) as exc:
            print(f"init failed: {exc}", file=sys.stderr)
            return 2
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        else:
            print(f"initialized {result['project_id']}: {result['manifest']}")
        return 0

    if args.command == "run":
        from .evidence import RUN_ID_ENV, new_run_id

        project = args.project.resolve()
        run_id = args.run_id or new_run_id()
        pytest_args = [part for part in args.pytest_args if part != "--"]
        if not pytest_args:
            pytest_args = [".testence/examples/test_onboarding.py", "-q"]
        environment = dict(os.environ)
        environment[RUN_ID_ENV] = run_id
        print(f"testence run: {run_id}")
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "--rootdir", str(project), *pytest_args],
            cwd=project,
            env=environment,
            check=False,
        )
        return int(completed.returncode)

    if args.command == "inspect":
        from .application import ApplicationError, inspect_run

        try:
            result = inspect_run(args.run_dir)
        except ApplicationError as exc:
            print(f"inspect failed: {exc}", file=sys.stderr)
            return 2
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        else:
            print(
                f"{result['run_id']} {result['run_status']}: "
                f"{result['tests']} tests, {result['assurance']}"
            )
        return 0

    if args.command == "demo" and args.demo_command == "run":
        from .application import ApplicationError, run_demo

        try:
            result = run_demo(args.project, run_prefix=args.run_prefix)
        except (ApplicationError, OSError) as exc:
            print(f"demo failed: {exc}", file=sys.stderr)
            return 2
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        else:
            for item in result["runs"]:
                print(
                    f"{item['name']}: {item['summary']['run_status']} "
                    f"({item['summary']['assurance']}) -> {item['report']}"
                )
        return 0 if result["status"] == "passed" else 3

    if args.command == "capabilities":
        from .config import Settings
        from .engine import capability_document, create_engine

        try:
            engine = create_engine(Settings.load(args.project), backend=args.backend)
        except (OSError, ValueError) as exc:
            print(f"capability preflight failed: {exc}", file=sys.stderr)
            return 2
        result = capability_document(engine, backend=args.backend)
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        else:
            print(f"{result['backend']}: {', '.join(result['capabilities'])}")
        return 0

    if args.command == "quality":
        from .quality import (
            QualityPackError,
            apply_quality_pack,
            quality_summary,
            rollback_quality_pack,
        )

        try:
            if args.quality_command == "apply":
                result = apply_quality_pack(args.pack, args.project, dry_run=args.dry_run)
            elif args.quality_command == "rollback":
                result = rollback_quality_pack(args.project, args.digest)
            else:
                result = quality_summary(
                    args.run_dirs,
                    project=args.project,
                    owner=args.owner,
                    risk=args.risk,
                    case=args.case,
                )
                if args.out:
                    args.out.parent.mkdir(parents=True, exist_ok=True)
                    args.out.write_text(
                        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                        newline="\n",
                    )
        except (OSError, QualityPackError, ValueError) as exc:
            print(f"quality {args.quality_command} failed: {exc}", file=sys.stderr)
            return 2
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 3 if result.get("status") == "conflict" else 0

    if args.command == "agent":
        from .agent import AgentInstallError, install_skills, verify_skills

        try:
            if args.agent_command == "install":
                result = install_skills(args.project, args.client)
            else:
                result = verify_skills(args.project, args.client)
        except (AgentInstallError, OSError, ValueError) as exc:
            print(f"agent {args.agent_command} failed: {exc}", file=sys.stderr)
            return 2
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 3 if result["status"] in {"conflict", "drift"} else 0

    if args.command == "corpus":
        from .benchmark import CorpusProtocolError, validate_corpus_registry

        try:
            result = validate_corpus_registry(args.path, repository_root=args.root)
        except (CorpusProtocolError, OSError, ValueError) as exc:
            print(f"corpus validate failed: {exc}", file=sys.stderr)
            return 2
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if args.structure_only or result["acceptance_ready"] else 3

    if args.command == "release":
        from .release import ReleaseManifestError, validate_release_manifest

        try:
            result = validate_release_manifest(
                args.path,
                repository_root=args.root,
                verify_files=not args.structure_only,
            )
        except (ReleaseManifestError, OSError, ValueError) as exc:
            print(f"release validate failed: {exc}", file=sys.stderr)
            return 2
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "go" or result["ready_for_owner_decision"] else 3

    if args.command == "export":
        # Imported here, not at module scope: an exporter module is loaded only when
        # its format is asked for, so `testence report` and every test run pay nothing
        # for formats they do not use (ADR-0013).
        from .export import ExporterError, available, default_out_dir, export_run

        if args.list_:
            for exporter, source in sorted(available().items()):
                print(f"{exporter:12} {source}")
            return 0
        if args.run_dir is None or not args.to:
            p_export.error("needs a run directory and --to <exporter>, or --list")
        out = args.out or default_out_dir(args.run_dir, args.to)
        try:
            files = export_run(args.run_dir, args.to, out, attachments=args.attachments)
        except ExporterError as exc:
            print(f"export failed: {exc}", file=sys.stderr)
            return 2
        print(f"{args.to} -> {out} ({len(files)} files)")
        return 0

    if args.command == "bench":
        cmd = [c for c in args.cmd if c != "--"]
        if not cmd:
            parser.error("bench needs a command after --")
        before = {p.name for p in args.runs_root.glob("r-*")}
        env = dict(os.environ, TESTENCE_RUNS_ROOT=str(args.runs_root))
        roots = args.reload_root or [Path("src"), Path("tests"), Path("examples")]
        roots = [root for root in roots if root.exists()]
        try:
            warm_runner = _WarmPytestRunner(cmd, roots, env=env) if args.warm else None
        except ValueError as exc:
            parser.error(str(exc))
        try:
            for i in range(args.iterations):
                print(f"[bench] iteration {i + 1}/{args.iterations}")
                if warm_runner is not None:
                    warm_runner.run()
                else:
                    subprocess.run(cmd, env=env, check=False)
        finally:
            if warm_runner is not None:
                warm_runner.close()
        new_dirs = sorted(
            p for p in args.runs_root.glob("r-*") if p.name not in before and p.is_dir()
        )
        out = args.runs_root / "metrics.json"
        doc = write_metrics(new_dirs, out)
        print(f"[bench] {len(new_dirs)} runs -> {out}")
        print(doc)
        return 0

    if args.command == "watch":
        cmd = [c for c in args.cmd if c != "--"]
        if not cmd:
            parser.error("watch needs a command after --")
        roots = args.watch or [Path("src"), Path("tests"), Path("examples")]
        roots = [r for r in roots if r.exists()]
        if not roots:
            parser.error("nothing to watch: pass -w with a directory that exists")
        if args.warm:
            try:
                _pytest_args(cmd)
            except ValueError as exc:
                parser.error(str(exc))
        return _watch(roots, args.pattern or ["*.py"], cmd, warm=args.warm)

    if args.command == "plan":
        if args.plan_command == "validate":
            from .contracts import load_plan
            from .contracts._validation import ContractError

            try:
                plan = load_plan(args.path)
            except ContractError as exc:
                print(f"plan invalid: {exc}", file=sys.stderr)
                return 2
            summary = plan.summary()
            if args.json_output:
                print(json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
            else:
                print(
                    f"plan valid: {plan.id} ({len(plan.claims)} claims, "
                    f"{len(plan.scenarios)} scenarios)"
                )
            return 0

        from .contracts._validation import ContractError
        from .readiness import ReadinessError, prepare_plan

        try:
            result = prepare_plan(
                args.path,
                args.project,
                profile=args.profile,
                backend=args.backend,
                apply_fixes=args.apply_fixes,
            )
        except (ContractError, OSError, ReadinessError, ValueError) as exc:
            print(f"plan prepare failed: {exc}", file=sys.stderr)
            return 2
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        else:
            for fix in result["fixes"]:
                print(
                    f"{fix['status']:7} fix for {fix['check_id']}: "
                    f"recheck={'ok' if fix['check_ok_after'] else 'failed'}"
                )
            for scenario in result["scenarios"]:
                print(f"{scenario['status']:7} {scenario['id']}")
                for blocker in scenario["blockers"]:
                    print(f"         {blocker['detail']}")
            summary = result["summary"]
            print(
                f"{summary['ready']}/{summary['total']} scenarios ready "
                f"in {result['timings']['total_ms']:.1f} ms"
            )
        return 0 if result["status"] == "ready" else 3

    if args.command == "verdict" and args.verdict_command == "validate":
        from .contracts import load_plan, load_verdict
        from .contracts._validation import ContractError

        try:
            verdict_plan = load_plan(args.plan) if args.plan else None
            verdict = load_verdict(
                args.path,
                pack_dir=args.pack or args.path.parent,
                plan=verdict_plan,
            )
        except ContractError as exc:
            print(f"verdict invalid: {exc}", file=sys.stderr)
            return 2
        summary = verdict.summary_document()
        if args.json_output:
            print(json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
        else:
            label = verdict.verdict or "blocked"
            print(
                f"verdict valid: {label} for {verdict.test_id} "
                f"({len(verdict.claim_results)} claims)"
            )
        return 0

    if args.command == "verdict" and args.verdict_command == "submit":
        from .application import ApplicationError, submit_verdict
        from .contracts._validation import ContractError

        try:
            result = submit_verdict(
                args.path,
                plan_path=args.plan,
                pack_dir=args.pack,
                output_path=args.out,
            )
        except (ApplicationError, ContractError, OSError) as exc:
            print(f"verdict submit failed: {exc}", file=sys.stderr)
            return 2
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        else:
            print(f"verdict submitted: {result['output']} ({result['verdict_digest']})")
        return 0

    if args.command == "repair" and args.repair_command == "validate":
        from .contracts import load_plan, load_repair, load_verdict, validate_repair
        from .contracts._validation import ContractError

        try:
            repair_plan = load_plan(args.plan)
            repair_verdict = load_verdict(
                args.verdict,
                pack_dir=args.pack or args.verdict.parent,
                plan=repair_plan,
            )
            proposal = load_repair(args.path)
            validate_repair(
                proposal,
                verdict=repair_verdict,
                verdict_path=args.verdict,
                plan=repair_plan,
                base_path=args.base,
                evidence_root=args.evidence_root,
            )
        except ContractError as exc:
            print(f"repair invalid: {exc}", file=sys.stderr)
            return 2
        summary = proposal.summary_document()
        if args.json_output:
            print(json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
        else:
            print(f"repair valid: {proposal.kind} for {proposal.case_id}")
        return 0

    if args.command == "delivery" and args.delivery_command == "run":
        from .ci import CIError, run_delivery

        command = [part for part in args.cmd if part != "--"]
        try:
            delivery_result = run_delivery(
                run_dir=args.run_dir,
                run_id=args.run_id,
                project_id=args.project_id,
                launch_id=args.launch_id,
                job_run_id=args.job_run_id,
                artifact_dir=args.artifact_dir,
                receipt_path=args.receipt,
                command=command,
                retries=args.retries,
                timeout_s=args.timeout,
            )
        except CIError as exc:
            print(f"delivery invalid: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(delivery_result.receipt, ensure_ascii=False, separators=(",", ":")))
        return delivery_result.exit_code

    if args.command == "ci" and args.ci_command == "evaluate":
        from .ci import CIError, evaluate_ci, write_ci_receipt

        try:
            receipt = evaluate_ci(
                run_dir=args.run_dir,
                run_id=args.run_id,
                test_exit=args.test_exit,
                quality_mode=args.quality_mode,
                delivery_receipt=args.delivery_receipt,
                ctrf_path=args.ctrf,
                junit_path=args.junit,
                allow_empty=args.allow_empty,
                testplan_unresolved=args.testplan_unresolved,
            )
            write_ci_receipt(args.out, receipt)
        except CIError as exc:
            print(f"ci invalid: {exc}", file=sys.stderr)
            return 2
        if args.json_output:
            print(json.dumps(receipt, ensure_ascii=False, separators=(",", ":")))
        else:
            print(
                f"ci -> {args.out}: test={receipt['test']['exit_code']} "
                f"quality={receipt['quality']['exit_code']} "
                f"delivery={receipt['delivery']['exit_code']} final={receipt['final_exit']}"
            )
        return int(receipt["final_exit"])

    return 1


if __name__ == "__main__":
    sys.exit(main())
