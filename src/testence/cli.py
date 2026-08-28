"""``testence`` CLI: metrics aggregation, HTML report, bench loops, watch mode.

Cross-platform by construction: pure Python entry points, no shell wrappers
(Windows dev machines and Linux CI are both first-class platforms).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

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


def _watch(watch_roots: list[Path], patterns: list[str], cmd: list[str]) -> int:
    """Re-run ``cmd`` whenever a watched file changes, until interrupted.

    This exists because of where a suite's wall-clock actually goes: across a
    29-minute authoring session the runner accounted for 16 % of it, and the rest
    was the gap between saving a file and asking for a run. Pair it with an
    attached browser (``python -m testence.dev_browser`` plus a ``*-attached``
    profile) and the whole loop is the run itself.
    """
    print(f"[watch] {' '.join(cmd)}")
    print(f"[watch] roots: {', '.join(str(r) for r in watch_roots)} "
          f"({', '.join(patterns)}) — Ctrl+C to stop")
    state = _snapshot(watch_roots, patterns)
    runs = 0
    try:
        while True:
            runs += 1
            print(f"[watch] run {runs}")
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
    p_export.add_argument("--to", default=None, metavar="EXPORTER",
                          help="exporter name (see --list)")
    p_export.add_argument("-o", "--out", type=Path, default=None)
    p_export.add_argument("--list", dest="list_", action="store_true",
                          help="list registered exporters and exit")

    p_bench = sub.add_parser("bench", help="run a command N times, then aggregate")
    p_bench.add_argument("-n", "--iterations", type=int, default=10)
    p_bench.add_argument("--runs-root", type=Path, default=Path("runs"))
    p_bench.add_argument("cmd", nargs=argparse.REMAINDER,
                         help="command to repeat (prefix with --)")

    p_watch = sub.add_parser("watch", help="re-run a command whenever a file changes")
    p_watch.add_argument("-w", "--watch", type=Path, action="append", default=None,
                         help="directory to watch (repeatable; default: src, tests, examples)")
    p_watch.add_argument("-p", "--pattern", action="append", default=None,
                         help="glob to watch (repeatable; default: *.py)")
    p_watch.add_argument("cmd", nargs=argparse.REMAINDER,
                         help="command to re-run (prefix with --)")

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
        before = set(p.name for p in args.runs_root.glob("r-*"))
        env = dict(os.environ, TESTENCE_RUNS_ROOT=str(args.runs_root))
        for i in range(args.iterations):
            print(f"[bench] iteration {i + 1}/{args.iterations}")
            subprocess.run(cmd, env=env, check=False)
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
        return _watch(roots, args.pattern or ["*.py"], cmd)

    return 1


if __name__ == "__main__":
    sys.exit(main())
