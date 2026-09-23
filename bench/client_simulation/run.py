"""Emulate two client layouts from an installed wheel, with frozen visual controls.

Run using an isolated wheel Python: python -I bench/client_simulation/run.py ...
This is controlled client-contract simulation, not independent human/model trials.
"""

from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import os
import platform
import secrets
import shutil
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from testence.application import inspect_run
from testence.distribution import verify_installed_wheel
from testence.loopback import LoopbackHTTPServer

HERE = Path(__file__).resolve().parent
PHASES = ("healthy", "shift", "invisible", "mobile-clip", "dom-only", "restored")
STYLES = {
    "shift": "main{transform:translateX(28px)}",
    "invisible": ".value{color:transparent}",
    "mobile-clip": "@media(max-width:600px){main{min-width:760px}}",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen_files(project: Path) -> dict[str, str]:
    paths = [project / name for name in ("test_ui.py", "plan.md", "baselines.json")]
    paths += sorted((project / "baselines").rglob("*"))
    return {path.relative_to(project).as_posix(): sha(path) for path in paths if path.is_file()}


def invoke(command: list[str], project: Path, log: Path, env: dict[str, str]) -> tuple[int, float]:
    started = time.perf_counter()
    with log.open("w", encoding="utf-8") as stream:
        try:
            result = subprocess.run(
                command, cwd=project, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=90
            )
            code = result.returncode
        except subprocess.TimeoutExpired:
            stream.write("\nHarness deadline: 90 seconds; attempt not retried.\n")
            code = 124
    return code, round((time.perf_counter() - started) * 1000, 1)


def grade(junit: Path, inspection: dict, code: int, defect: bool) -> bool:
    try:
        cases = list(ET.parse(junit).iter("testcase"))
    except (OSError, ET.ParseError):
        return False
    failures = [case.find("failure") for case in cases if case.find("failure") is not None]
    return (
        code == (1 if defect else 0)
        and len(cases) == 2
        and not any(
            case.find("error") is not None or case.find("skipped") is not None for case in cases
        )
        and len(failures) == (2 if defect else 0)
        and all("visual mismatch:" in failure.get("message", "") for failure in failures)
        and inspection.get("assurance") == ({"violated": 2} if defect else {"verified": 2})
        and not inspection.get("integrity_errors")
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--distribution", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=2)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("repeats must be positive")
    binding = verify_installed_wheel(args.distribution.resolve())
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    mode = {"phase": "healthy"}
    raw = (HERE / "panel.html").read_text(encoding="utf-8")

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            body = raw.replace("/* harness-style */", STYLES.get(mode["phase"], ""))
            if mode["phase"] == "dom-only":
                body = body.replace('id="invite"', 'id="invite-refactored" data-build="next"')
            data = body.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = LoopbackHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    # Deliberately do not inherit developer Testence settings or source import paths.
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("TESTENCE_", "PYTHONPATH", "PYTEST_"))
    }
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    receipt = {
        "schema": "testence/client-visual-simulation/1",
        "scope": "Installed wheel, two adapter layouts, one scripted actor; no independent Claude/Codex execution claimed",
        "distribution": binding,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "sources": {path.name: sha(path) for path in HERE.iterdir() if path.is_file()},
        "provisioning": [],
        "projects": [],
        "records": [],
        "status": "incomplete",
    }

    def checkpoint():
        (output / "result.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    checkpoint()
    try:
        for client in ("codex", "claude"):
            for profile, width, height in (("desktop", 1280, 900), ("mobile", 390, 844)):
                project = output / f"{client}-{profile}"
                project.mkdir()
                (project / "pytest.ini").write_text("[pytest]\ntestpaths = .\n", encoding="utf-8")
                for name in ("test_ui.py", "plan.md", "provision.py", "judge.py"):
                    shutil.copyfile(HERE / name, project / name)
                (project / "testence.json").write_text(
                    json.dumps(
                        {
                            "project_id": "client-simulation",
                            "base_url": f"http://127.0.0.1:{server.server_port}",
                            "headed": False,
                            "debug_port": 0,
                            "timeout_ms": 5000,
                            "capture_policy": {"screenshots": True},
                            "viewport": {"width": width, "height": height},
                        }
                    ),
                    encoding="utf-8",
                )
                commands = [
                    [
                        "-m",
                        "testence.cli",
                        "agent",
                        "install",
                        "--project",
                        str(project),
                        "--client",
                        client,
                        "--json",
                    ],
                    ["-m", "testence.cli", "agent", "verify", "--project", str(project), "--json"],
                    ["-m", "testence.cli", "doctor", "--root", str(project), "--json"],
                    ["-m", "testence.cli", "plan", "validate", "plan.md", "--json"],
                    ["provision.py"],
                ]
                mode["phase"] = "healthy"
                for number, command in enumerate(commands):
                    code, elapsed = invoke(
                        [sys.executable, "-I", *command],
                        project,
                        project / f"setup-{number}.log",
                        env,
                    )
                    receipt["provisioning"].append(
                        {
                            "client": client,
                            "profile": profile,
                            "command": command,
                            "exit_code": code,
                            "wall_ms": elapsed,
                        }
                    )
                    checkpoint()
                    if code:
                        raise RuntimeError(f"client setup failed: {project.name}, command {number}")
                frozen = frozen_files(project)
                receipt["projects"].append(
                    {"client": client, "profile": profile, "frozen_files": frozen}
                )
                for phase in PHASES:
                    mode["phase"] = phase
                    defect = (
                        phase in {"shift", "invisible"}
                        or phase == "mobile-clip"
                        and profile == "mobile"
                    )
                    for repeat in range(args.repeats):
                        # Expected labels belong to the grader, not the judge's pack/path.
                        run_id = "sample-" + secrets.token_hex(6)
                        junit = project / f"{run_id}.xml"
                        command = [
                            sys.executable,
                            "-I",
                            "-m",
                            "pytest",
                            "-p",
                            "testence.pytest_plugin",
                            "test_ui.py",
                            "-q",
                            "--testence-headless",
                            "--testence-runs-root",
                            str(project / "runs"),
                            f"--junitxml={junit}",
                        ]
                        code, elapsed = invoke(
                            command,
                            project,
                            project / f"{run_id}.log",
                            dict(env, TESTENCE_RUN_ID=run_id),
                        )
                        try:
                            inspection = inspect_run(project / "runs" / run_id)
                        except (OSError, ValueError) as exc:
                            inspection = {"integrity_errors": [str(exc)]}
                        unchanged = frozen == frozen_files(project)
                        judgments = []
                        if defect and grade(junit, inspection, code, defect):
                            for index, pack in enumerate(
                                sorted((project / "runs" / run_id).glob("*/pack/pack.json"))
                            ):
                                judge_code, judge_ms = invoke(
                                    [sys.executable, "-I", "judge.py", str(pack.parent)],
                                    project,
                                    project / f"{run_id}-judge-{index}.log",
                                    env,
                                )
                                judgments.append({"exit_code": judge_code, "wall_ms": judge_ms})
                        record = {
                            "client": client,
                            "profile": profile,
                            "phase": phase,
                            "repeat": repeat + 1,
                            "run_id": run_id,
                            "exit_code": code,
                            "wall_ms": elapsed,
                            "expected_defect": defect,
                            "assurance": inspection.get("assurance"),
                            "integrity_errors": inspection.get("integrity_errors"),
                            "frozen_unchanged": unchanged,
                            "judgments": judgments,
                            "passed": unchanged and grade(junit, inspection, code, defect),
                        }
                        record["passed"] = record["passed"] and (
                            not defect
                            or len(judgments) == 2
                            and all(item["exit_code"] == 0 for item in judgments)
                        )
                        receipt["records"].append(record)
                        checkpoint()
                        print(
                            f"{project.name}/{run_id}: {'OK' if record['passed'] else 'MISMATCH'} {elapsed} ms",
                            flush=True,
                        )
                        if not record["passed"]:
                            raise RuntimeError(
                                f"unexpected outcome: {project.name}/{run_id}; preserve this attempt"
                            )
        receipt["status"] = (
            "passed" if all(row["passed"] for row in receipt["records"]) else "failed"
        )
    except Exception as exc:
        receipt["error"] = f"{type(exc).__name__}: {exc}"
        receipt["status"] = "failed"
        raise
    finally:
        checkpoint()
        server.shutdown()
        server.server_close()
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
