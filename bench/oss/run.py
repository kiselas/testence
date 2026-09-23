"""Run pinned third-party UI controls with healthy, defect and harmless controls."""

from __future__ import annotations

import argparse
import functools
import hashlib
import http.server
import importlib.metadata
import json
import os
import platform
import statistics
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from testence.application import inspect_run
from testence.loopback import LoopbackHTTPServer

ROOT = Path(__file__).resolve().parents[2]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/oss-panels")
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("repeats must be positive")
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("output must be empty; preserve earlier evidence in its own directory")
    output.mkdir(parents=True, exist_ok=True)
    targets = json.loads((ROOT / "bench/oss/targets.json").read_text())["targets"]
    servers = []
    env = dict(os.environ, TESTENCE_HEADED="false", TESTENCE_PROJECT_ID="oss-panels")
    mode = {"value": "healthy"}

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            path = Path(self.translate_path(self.path))
            if path.suffix != ".html" or not path.is_file():
                return super().do_GET()
            body = path.read_text(encoding="utf-8")
            if mode["value"] == "defect":
                body = body.replace(
                    'id="exampleCheck1"', 'id="exampleCheck1" onchange="this.checked=false"'
                )
                body = body.replace(
                    'data-password-toggle="signin-password"',
                    'data-disabled-toggle="signin-password"',
                )
            elif mode["value"] == "restyle":
                body = body.replace(
                    "</head>", "<style>.card{border-radius:18px!important}</style></head>"
                )
            raw = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    records = []
    try:
        for target in targets:
            checkout = ROOT / target["checkout"]
            revision = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=checkout, text=True
            ).strip()
            if revision != target["revision"]:
                raise RuntimeError(f"{target['name']}: checkout revision differs from targets.json")
            if subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=checkout, text=True
            ).strip():
                raise RuntimeError(f"{target['name']}: upstream checkout has modifications")
            web_root = checkout / target["web_root"]
            if not (web_root / "index.html").is_file():
                raise RuntimeError(f"Build {target['name']} first; see bench/oss/README.md")
            license_path = checkout / target["license"]
            target["license_sha256"] = digest(license_path)
            material = hashlib.sha256()
            for asset in sorted(web_root.rglob("*")):
                if asset.is_file():
                    material.update(asset.relative_to(web_root).as_posix().encode() + b"\0")
                    material.update(bytes.fromhex(digest(asset)))
            target["built_tree_sha256"] = material.hexdigest()
            (output / f"{target['name']}-LICENSE").write_bytes(license_path.read_bytes())
            handler = functools.partial(Handler, directory=str(web_root))
            server = LoopbackHTTPServer(("127.0.0.1", 0), handler)
            servers.append(server)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            env["OSS_" + target["name"].upper()] = f"http://127.0.0.1:{server.server_port}"
        for phase in ("healthy", "defect", "restored", "restyle"):
            mode["value"] = phase
            for repeat in range(args.repeats):
                run_id = f"oss-{phase}-{repeat + 1}"
                junit = output / f"{run_id}.xml"
                run_env = dict(env, TESTENCE_RUN_ID=run_id)
                command = [
                    sys.executable,
                    "-m",
                    "pytest",
                    "bench/oss/test_panels.py",
                    "-q",
                    "--testence-headless",
                    "--testence-runs-root",
                    str(output / "runs"),
                    f"--junitxml={junit}",
                ]
                started = time.perf_counter()
                timed_out = False
                with (output / f"{run_id}.log").open("w", encoding="utf-8") as log:
                    try:
                        completed = subprocess.run(
                            command,
                            cwd=ROOT,
                            env=run_env,
                            stdout=log,
                            stderr=subprocess.STDOUT,
                            text=True,
                            timeout=120,
                        )
                        exit_code = completed.returncode
                    except subprocess.TimeoutExpired:
                        # A failed attempt remains evidence. Never retry it into green.
                        timed_out = True
                        exit_code = 124
                        log.write("\nHarness deadline exceeded (120 seconds).\n")
                elapsed = (time.perf_counter() - started) * 1000
                try:
                    cases = list(ET.parse(junit).iter("testcase")) if junit.exists() else []
                except ET.ParseError:
                    cases = []
                failed = {
                    case.attrib["name"]: case.find("failure").attrib.get("message", "")
                    for case in cases
                    if case.find("failure") is not None
                }
                errors = sum(
                    case.find("error") is not None or case.find("skipped") is not None
                    for case in cases
                )
                expected = (
                    {
                        "test_admin_checkbox": "Selection is visibly checked",
                        "test_tabler_password": "Password is revealed",
                    }
                    if phase == "defect"
                    else {}
                )
                passed = (
                    exit_code == (1 if expected else 0)
                    and len(cases) == 4
                    and errors == 0
                    and set(failed) == set(expected)
                    and all(reason in failed[name] for name, reason in expected.items())
                )
                try:
                    inspection = inspect_run(output / "runs" / run_id)
                except (OSError, ValueError) as exc:
                    inspection = {"assurance": {}, "integrity_errors": [str(exc)]}
                expected_assurance = {"verified": 2, "violated": 2} if expected else {"verified": 4}
                passed = (
                    passed
                    and inspection["assurance"] == expected_assurance
                    and not inspection["integrity_errors"]
                )
                record = {
                    "phase": phase,
                    "repeat": repeat + 1,
                    "wall_ms": round(elapsed, 1),
                    "exit_code": exit_code,
                    "timed_out": timed_out,
                    "passed": passed,
                    "failures": failed,
                    "junit": junit.name,
                    "run_id": run_id,
                    "assurance": inspection["assurance"],
                    "integrity_errors": inspection["integrity_errors"],
                }
                records.append(record)
                (output / "checkpoint.json").write_text(
                    json.dumps({"complete": False, "records": records}, indent=2) + "\n",
                    encoding="utf-8",
                )
                print(f"{run_id}: {'OK' if passed else 'MISMATCH'} {elapsed:.0f} ms", flush=True)
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()
    summary = {}
    for phase in ("healthy", "defect", "restored", "restyle"):
        samples = sorted(row["wall_ms"] for row in records if row["phase"] == phase)
        summary[phase] = {
            "n": len(samples),
            "p50_ms": statistics.median(samples),
            "max_ms": max(samples),
        }
    receipt = {
        "schema": "testence/oss-ui-smoke/1",
        "scope": "UI-only synthetic controls; not frozen R1 corpus acceptance or independent client proof",
        "revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "dirty": bool(
            subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
        ),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "playwright": importlib.metadata.version("playwright"),
        "targets": targets,
        "tests_sha256": digest(ROOT / "bench/oss/test_panels.py"),
        "plan_sha256": digest(ROOT / "bench/oss/plan.md"),
        "records": records,
        "summary": summary,
        "passed": all(row["passed"] for row in records),
    }
    (output / "result.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
