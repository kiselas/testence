"""``testence`` CLI: metrics, reports, benchmarks and fast authoring loops.

Cross-platform by construction: pure Python entry points, no shell wrappers
(Windows dev machines and Linux CI are both first-class platforms).
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
    parser = argparse.ArgumentParser(prog="testence")
    sub = parser.add_subparsers(dest="command", required=True)

    p_metrics = sub.add_parser("metrics", help="aggregate metrics.json from run dirs")
    p_metrics.add_argument("run_dirs", nargs="+", type=Path)
    p_metrics.add_argument("-o", "--out", type=Path, default=Path("metrics.json"))

    p_report = sub.add_parser("report", help="render a self-contained HTML report")
    p_report.add_argument("run_dir", type=Path)
    p_report.add_argument("-o", "--out", type=Path, default=None)

    p_export = sub.add_parser("export", help="render an integration format from a run")
    p_export.add_argument("run_dir", nargs="?", type=Path)
    p_export.add_argument(
        "--to", default=None, metavar="EXPORTER", help="exporter name (see --list)"
    )
    p_export.add_argument("-o", "--out", type=Path, default=None)
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
    p_plan_validate.add_argument("path", type=Path)
    p_plan_validate.add_argument("--json", dest="json_output", action="store_true")

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
            files = export_run(args.run_dir, args.to, out)
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

    if args.command == "plan" and args.plan_command == "validate":
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

    return 1


if __name__ == "__main__":
    sys.exit(main())
