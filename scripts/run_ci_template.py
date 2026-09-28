"""Run the documented GitHub Actions template's shell steps, as written.

The repository's CI calls this on a project made by ``testence init`` so the template
users copy (``docs/examples/github-actions.yml``) is exercised verbatim: ``uses:``
steps are the runner's job, every ``run:`` step executes with ``${{ ... }}`` resolved
the way GitHub resolves it for this template, and ``if: always()`` steps run after a
failure as they would there.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml  # type: ignore[import-untyped]

_EXPRESSION = re.compile(r"\$\{\{\s*([^}]+?)\s*\}\}")


def _resolve(text: str, run_id: str) -> str:
    def value(match: re.Match[str]) -> str:
        name = match.group(1)
        if name == "github.run_id":
            return run_id
        if name.startswith("secrets."):
            return ""
        raise SystemExit(f"unsupported expression in the template: {name}")

    return _EXPRESSION.sub(value, text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID", "local"))
    args = parser.parse_args(argv)
    workflow = yaml.safe_load(args.template.read_text(encoding="utf-8"))
    (job,) = workflow["jobs"].values()
    env = dict(os.environ)
    env.update(
        {key: _resolve(str(value), args.run_id) for key, value in job.get("env", {}).items()}
    )
    bash = shutil.which("bash")
    # On Windows the bare name resolves to System32's WSL launcher first, which would
    # run the template inside a different system (and install into it).
    if bash is None or Path(bash).parent.name.lower() == "system32":
        raise SystemExit(f"need a native bash on PATH (Git Bash on Windows), found {bash}")
    failed = False
    for step in job["steps"]:
        if "run" not in step:
            continue
        condition = step.get("if")
        if failed and condition != "always()":
            continue
        script = _resolve(step["run"], args.run_id)
        print(f"::group::{step.get('name', script.splitlines()[0])}", flush=True)
        completed = subprocess.run(
            [bash, "-e", "-c", script], cwd=args.project, env=env, check=False
        )
        print("::endgroup::", flush=True)
        if completed.returncode != 0:
            print(f"step failed with exit code {completed.returncode}", file=sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
