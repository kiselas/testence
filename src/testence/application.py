"""Application services behind onboarding and inspection CLI commands."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import re
import subprocess
import sys
from importlib.resources import files
from pathlib import Path
from typing import Any

from testence import __version__
from testence.config import Settings, default_browser_channel
from testence.contracts import SCHEMA_INVENTORY, load_plan, load_verdict
from testence.contracts.versions import DEMO_RUN_SCHEMA, SCAFFOLD_SCHEMA, SUBMISSION_SCHEMA
from testence.export import LoadedRun
from testence.managed_paths import ManagedPathError, atomic_write_bytes, checked_member
from testence.metrics import load_run


class ApplicationError(ValueError):
    pass


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _managed(project: Path, relative: str) -> Path:
    try:
        return checked_member(project, relative)
    except ManagedPathError as exc:
        raise ApplicationError(str(exc)) from exc


def _atomic_write(project: Path, relative: str, raw: bytes) -> Path:
    try:
        return atomic_write_bytes(project, relative, raw)
    except (ManagedPathError, OSError) as exc:
        raise ApplicationError(f"cannot write managed file {relative!r}: {exc}") from exc


def _project_id(root: Path) -> str:
    value = re.sub(r"[^a-z0-9._-]+", "-", root.name.lower()).strip("-._")
    return value[:128] or "testence-project"


def _scaffold(project_id: str) -> dict[str, bytes]:
    settings = {
        "project_id": project_id,
        "base_url": "http://127.0.0.1:8000",
        "auth": "none",
        "headed": False,
        "runs_root": "runs",
        "extra": {
            "capture_policy": {
                "network_bodies": False,
                "screenshots": True,
                "body_content_types": ["application/json"],
                "body_cap_bytes": 65536,
            },
            # `plan prepare` is strict on purpose: a scenario with no declared
            # prerequisites is a scenario nobody has thought about. The scaffold
            # therefore ships the mapping it needs, so the generated plan reports
            # `ready` instead of teaching new projects that the gate always blocks.
            # The onboarding run owns its loopback server, so the only real
            # prerequisite is the generated test file itself.
            "readiness": {
                "schema": "testence/readiness/1",
                "oracle_adapters": ["custom"],
                "checks": [
                    {
                        "id": "onboarding-test",
                        "type": "file",
                        "path": ".testence/examples/test_onboarding.py",
                    }
                ],
                "scenarios": {
                    "synthetic-proof": ["onboarding-test"],
                    "intentional-failure": ["onboarding-test"],
                    "harmless-change": ["onboarding-test"],
                },
            },
        },
    }
    plan = f'''# Testence synthetic proof

```testence-planspec
{{
  "schema": "testence/planspec/2",
  "project_id": "{project_id}",
  "id": "onboarding.synthetic-proof",
  "title": "Verify the Testence proof loop",
  "source": "local onboarding scaffold",
  "owner": "project-qa",
  "claims": [
    {{
      "id": "onboarding.proof.recorded",
      "statement": "The required assertion is recorded and verified.",
      "oracles": ["custom"],
      "required": true
    }},
    {{
      "id": "onboarding.defect.detected",
      "statement": "A visible success must agree with authoritative state.",
      "oracles": ["custom"],
      "required": true
    }},
    {{
      "id": "onboarding.harmless.accepted",
      "statement": "A harmless presentation change preserves persisted state.",
      "oracles": ["custom"],
      "required": true
    }}
  ],
  "assertions": [
    {{
      "id": "assert.onboarding.proof",
      "claim_id": "onboarding.proof.recorded",
      "oracle": "custom",
      "required": true
    }},
    {{
      "id": "assert.onboarding.defect",
      "claim_id": "onboarding.defect.detected",
      "oracle": "custom",
      "required": true
    }},
    {{
      "id": "assert.onboarding.harmless",
      "claim_id": "onboarding.harmless.accepted",
      "oracle": "custom",
      "required": true
    }}
  ],
  "scenarios": [
    {{
      "id": "synthetic-proof",
      "title": "Record one deterministic proof",
      "claims": ["onboarding.proof.recorded"],
      "risk": "onboarding evidence is incomplete"
    }},
    {{
      "id": "intentional-failure",
      "title": "Expose a false green with an independent observation",
      "claims": ["onboarding.defect.detected"],
      "risk": "the UI reports success without persisted state"
    }},
    {{
      "id": "harmless-change",
      "title": "Accept a presentation change with preserved semantics",
      "claims": ["onboarding.harmless.accepted"],
      "risk": "presentation changes are misclassified as product defects"
    }}
  ]
}}
```
'''
    conftest = """import json
import threading
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit

import pytest

from testence.loopback import LoopbackHTTPServer


@pytest.fixture
def demo_server():
    state = {"id": "item-42", "state": "missing", "revision": 1}

    class Handler(BaseHTTPRequestHandler):
        def send_json(self, value, status=200):
            raw = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            parsed = urlsplit(self.path)
            if parsed.path == "/api/item/item-42":
                self.send_json(state)
                return
            mode = parse_qs(parsed.query).get("mode", ["healthy"])[0]
            wrapper = '<section class="new-layout">' if mode == "harmless" else "<section>"
            html = f'''<!doctype html><meta charset="utf-8"><title>Testence demo</title>
            {wrapper}<h1>Deterministic save</h1>
            <button id="save">Save</button><p id="status">pending</p></section>
            <script>
            document.getElementById('save').addEventListener('click', async () => {{
              await fetch('/api/save?mode={mode}', {{method: 'POST'}});
              document.getElementById('status').textContent = 'saved';
            }});
            </script>'''.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)

        def do_POST(self):
            mode = parse_qs(urlsplit(self.path).query).get("mode", ["healthy"])[0]
            if mode != "buggy":
                state.update(id="item-42", state="saved", revision=2)
            self.send_json({"accepted": True})

        def log_message(self, format, *args):
            return

    server = LoopbackHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
"""
    test = """import json
from urllib.request import urlopen

import pytest

from testence.engine import Target
from testence.oracle import verify


@pytest.mark.testence(
    plan=".testence/specs/onboarding.md",
    case_id="synthetic-proof",
    claims=["onboarding.proof.recorded"],
)
def test_testence_synthetic_proof(demo_server, ex, testence_writer, request):
    expected = {"id": "item-42", "state": "saved", "revision": 2}
    ex.goto(demo_server + "/?mode=healthy", intent="open the healthy save target")
    ex.click(Target("role", "button", name="Save"), intent="save item-42 once")
    ex.expect_text(Target("css", "#status"), "saved", intent="visible save confirmation")
    actual = json.load(urlopen(demo_server + "/api/item/item-42", timeout=2))
    verify(
        testence_writer,
        request.node.nodeid,
        "authoritative item state after one save",
        expected,
        actual,
        assertion_id="assert.onboarding.proof",
        claim_id="onboarding.proof.recorded",
        oracle_kind="custom",
    )
"""
    failure_test = """import json
from urllib.request import urlopen

import pytest

from testence.engine import Target
from testence.oracle import verify


@pytest.mark.testence(
    plan=".testence/specs/onboarding.md",
    case_id="intentional-failure",
    claims=["onboarding.defect.detected"],
)
def test_testence_exposes_intentional_false_green(demo_server, ex, testence_writer, request):
    expected = {"id": "item-42", "state": "saved", "revision": 2}
    ex.goto(demo_server + "/?mode=buggy", intent="open the buggy save target")
    ex.click(Target("role", "button", name="Save"), intent="save item-42 once")
    ex.expect_text(Target("css", "#status"), "saved", intent="visible save confirmation")
    actual = json.load(urlopen(demo_server + "/api/item/item-42", timeout=2))
    verify(
        testence_writer,
        request.node.nodeid,
        "visible success agrees with persisted state",
        expected,
        actual,
        assertion_id="assert.onboarding.defect",
        claim_id="onboarding.defect.detected",
        oracle_kind="custom",
    )
"""
    harmless_test = """import json
from urllib.request import urlopen

import pytest

from testence.engine import Target
from testence.oracle import verify


@pytest.mark.testence(
    plan=".testence/specs/onboarding.md",
    case_id="harmless-change",
    claims=["onboarding.harmless.accepted"],
)
def test_testence_accepts_harmless_layout_change(demo_server, ex, testence_writer, request):
    expected = {"id": "item-42", "state": "saved", "revision": 2}
    ex.goto(demo_server + "/?mode=harmless", intent="open the harmless layout variant")
    ex.click(Target("role", "button", name="Save"), intent="save item-42 once")
    ex.expect_text(Target("css", "#status"), "saved", intent="visible save confirmation")
    actual = json.load(urlopen(demo_server + "/api/item/item-42", timeout=2))
    verify(
        testence_writer,
        request.node.nodeid,
        "authoritative state survives presentation change",
        expected,
        actual,
        assertion_id="assert.onboarding.harmless",
        claim_id="onboarding.harmless.accepted",
        oracle_kind="custom",
    )
"""
    readme = """# Testence onboarding files

Run the synthetic proof explicitly with `testence run`. This hidden directory is not
added to your project's normal pytest paths, so initialization does not opt the existing
suite into Testence.
"""
    return {
        "testence.json": (json.dumps(settings, indent=2) + "\n").encode(),
        ".testence/specs/onboarding.md": plan.encode(),
        ".testence/examples/conftest.py": conftest.encode(),
        ".testence/examples/test_onboarding.py": test.encode(),
        ".testence/examples/test_demo_failure.py": failure_test.encode(),
        ".testence/examples/test_demo_harmless.py": harmless_test.encode(),
        ".testence/README.md": readme.encode(),
    }


def init_project(root: Path | str) -> dict[str, Any]:
    from testence.quality import QualityPackError, managed_writer

    project = Path(root).absolute()
    project.mkdir(parents=True, exist_ok=True)
    project = project.resolve(strict=True)
    try:
        with managed_writer(project) as commit:
            content = _scaffold(_project_id(project))
            artifacts = [
                {"path": relative, "sha256": _sha256(raw), "bytes": len(raw)}
                for relative, raw in sorted(content.items())
            ]
            manifest = {
                "schema": SCAFFOLD_SCHEMA,
                "testence_version": __version__,
                "project_id": _project_id(project),
                "artifacts": artifacts,
            }
            raw_manifest = (json.dumps(manifest, ensure_ascii=False, indent=1) + "\n").encode()
            desired = {**content, ".testence/scaffold-manifest.json": raw_manifest}
            conflicts: list[str] = []
            created: list[str] = []
            operations: list[tuple[str, bytes | None]] = []
            for relative, raw in desired.items():
                target = _managed(project, relative)
                if target.exists() and (not target.is_file() or target.read_bytes() != raw):
                    conflicts.append(relative)
                elif not target.exists():
                    operations.append((relative, raw))
                    if relative != ".testence/scaffold-manifest.json":
                        created.append(relative)
            if conflicts:
                raise ApplicationError(
                    "scaffold conflicts with existing file(s): " + ", ".join(conflicts)
                )
            commit(operations)
            manifest_path = _managed(project, ".testence/scaffold-manifest.json")
            return {**manifest, "created": created, "manifest": str(manifest_path)}
    except QualityPackError as exc:
        raise ApplicationError(f"cannot initialize project transaction: {exc}") from exc


#: `playwright._impl._errors.Error: BrowserType.launch: Executable doesn't exist ...`
_EXCEPTION_LINE = re.compile(r"^(?:[\w.]+\.)?\w*(?:Error|Exception):\s*(.+)$")


def _browser_failure(stderr: str) -> str:
    """The one line of a Playwright launch failure worth putting in a report.

    The message sits at the end of the traceback, before Playwright's advice box,
    so scan backwards for the exception rather than forwards into stack frames.
    """

    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    for line in reversed(lines):
        match = _EXCEPTION_LINE.match(line)
        if match:
            return match.group(1)[:200]
    for line in lines:
        if not line.startswith(("Traceback", "File ", "╔", "║", "╚")):
            return line[:200]
    return "browser did not start"


def _browser_fix(channel: str) -> str:
    if channel in {"chromium", "chromium-headless-shell"}:
        return f"python -m playwright install {channel}"
    return (
        f"install the {channel!r} browser, or point Testence at another one with "
        "TESTENCE_BROWSER_CHANNEL"
    )


def doctor(root: Path | str) -> dict[str, Any]:
    project = Path(root).resolve()
    checks: list[dict[str, Any]] = []
    browser_channel = default_browser_channel()

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    check("python", sys.version_info >= (3, 10), platform_python())
    try:
        settings = Settings.load(project)
        browser_channel = settings.browser_channel
        check("settings", True, f"project_id={settings.project_id or 'unconfigured'}")
    except Exception as exc:
        check("settings", False, f"{type(exc).__name__}: {exc}")
    try:
        schema_root = files("testence.contracts").joinpath("schemas")
        packaged = len(list(schema_root.iterdir()))
        check("schemas", packaged >= len(SCHEMA_INVENTORY), f"{packaged} packaged schema files")
    except Exception as exc:
        check("schemas", False, f"{type(exc).__name__}: {exc}")
    try:
        version = importlib.metadata.version("playwright")
        # Start the browser the project is configured to use, rather than checking that
        # a bundled executable path exists. A present file that cannot launch is the
        # failure people actually hit, and a project on `chrome`/`msedge` was reported
        # as broken while its runs worked.
        browser_probe = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys\n"
                "from playwright.sync_api import sync_playwright\n"
                "with sync_playwright() as p:\n"
                "    browser = p.chromium.launch(channel=sys.argv[1], headless=True)\n"
                "    print(browser.version)\n"
                "    browser.close()\n",
                browser_channel,
            ],
            text=True,
            capture_output=True,
            check=False,
            timeout=90,
        )
        started = browser_probe.returncode == 0
        detail = f"playwright={version}; channel={browser_channel}"
        if started:
            detail += f"; {browser_probe.stdout.strip()}"
        else:
            detail += (
                f"; {_browser_failure(browser_probe.stderr)}; fix: {_browser_fix(browser_channel)}"
            )
        check("browser", started, detail)
    except Exception as exc:
        check("browser", False, f"{type(exc).__name__}: {exc}")
    try:
        relative_probe = f".testence/doctor-{os.getpid()}.tmp"
        workspace_probe = _atomic_write(project, relative_probe, b"ok")
        workspace_probe.unlink()
        check("workspace", True, str(project))
    except OSError as exc:
        check("workspace", False, str(exc))
    return {"ok": all(item["ok"] for item in checks), "checks": checks}


def platform_python() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def inspect_run(run_dir: Path | str) -> dict[str, Any]:
    root = Path(run_dir)
    try:
        run = LoadedRun.from_events(load_run(root), root)
    except (OSError, ValueError) as exc:
        raise ApplicationError(f"cannot inspect run {root}: {exc}") from exc
    assurance: dict[str, int] = {}
    execution: dict[str, int] = {}
    for test in run.tests:
        assurance[test.assurance] = assurance.get(test.assurance, 0) + 1
        execution[test.status] = execution.get(test.status, 0) + 1
    return {
        "run_id": run.run_id,
        "project_id": run.project_id,
        "schema": run.schema,
        "run_status": run.run_status,
        "tests": len(run.tests),
        "execution": execution,
        "assurance": assurance,
        "integrity_errors": run.integrity_errors,
        "packs": [test.pack_dir for test in run.tests if test.pack_dir],
    }


def run_demo(root: Path | str, *, run_prefix: str | None = None) -> dict[str, Any]:
    """Run the portable healthy/failure demo and render both local reports."""
    from testence.evidence import RUN_ID_ENV, new_run_id
    from testence.report.html import render_report

    project = Path(root).resolve()
    initialized = init_project(project)
    prefix = run_prefix or new_run_id().removeprefix("r-")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}", prefix):
        raise ApplicationError("demo run prefix must contain only letters, digits, '.', '_' or '-'")

    scenarios = (
        ("healthy", ".testence/examples/test_onboarding.py", 0, "passed", "verified"),
        ("intentional_failure", ".testence/examples/test_demo_failure.py", 1, "failed", "violated"),
        ("harmless_change", ".testence/examples/test_demo_harmless.py", 0, "passed", "verified"),
    )
    run_ids = [f"r-{prefix}-{name.replace('_', '-')}" for name, *_rest in scenarios]
    conflicts = [run_id for run_id in run_ids if (project / "runs" / run_id).exists()]
    if conflicts:
        raise ApplicationError("demo run id already exists: " + ", ".join(conflicts))
    results: list[dict[str, Any]] = []
    for name, test_path, expected_exit, expected_status, expected_assurance in scenarios:
        run_id = f"r-{prefix}-{name.replace('_', '-')}"
        environment = dict(os.environ)
        environment[RUN_ID_ENV] = run_id
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "--rootdir", str(project), test_path, "-q"],
            cwd=project,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        run_dir = project / "runs" / run_id
        summary = inspect_run(run_dir)
        report = render_report(run_dir, run_dir / "report.html")
        pack_indexes = sorted(run_dir.glob("*/pack/pack.json"))
        pack_dir = pack_indexes[0].parent if len(pack_indexes) == 1 else None
        pack_files = (
            sorted(path.name for path in pack_dir.iterdir() if path.is_file())
            if pack_dir is not None
            else []
        )
        required_pack_files = {
            "TRIAGE.md",
            "aria.txt",
            "browser.json",
            "manifest.json",
            "oracle.json",
            "pack.json",
            "screenshot.png",
        }
        pack_accepted = (
            not pack_indexes
            if name != "intentional_failure"
            else len(pack_indexes) == 1 and required_pack_files <= set(pack_files)
        )
        accepted = (
            completed.returncode == expected_exit
            and summary["run_status"] == expected_status
            and summary["assurance"] == {expected_assurance: 1}
            and pack_accepted
        )
        artifact_paths = [report]
        if pack_dir is not None:
            artifact_paths.extend(path for path in pack_dir.iterdir() if path.is_file())
        artifacts = [
            {
                "path": path.relative_to(project).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": _sha256(path.read_bytes()),
            }
            for path in sorted(artifact_paths)
        ]
        results.append(
            {
                "name": name,
                "run_id": run_id,
                "expected_exit": expected_exit,
                "test_exit": completed.returncode,
                "accepted": accepted,
                "summary": summary,
                "report": str(report),
                "pack": str(pack_dir) if pack_dir is not None else None,
                "pack_files": pack_files,
                "artifacts": artifacts,
                "cleanup": {"pytest_process_exited": True},
            }
        )
    return {
        "schema": DEMO_RUN_SCHEMA,
        "testence_version": __version__,
        "project_id": initialized["project_id"],
        "project": str(project),
        "status": "passed" if all(item["accepted"] for item in results) else "failed",
        "runs": results,
    }


def submit_verdict(
    candidate_path: Path | str,
    *,
    plan_path: Path | str,
    pack_dir: Path | str,
    output_path: Path | str | None = None,
) -> dict[str, Any]:
    candidate = Path(candidate_path)
    pack = Path(pack_dir).resolve()
    output = Path(output_path).absolute() if output_path is not None else pack / "verdict.json"
    try:
        output_relative = output.relative_to(pack).as_posix()
    except ValueError as exc:
        raise ApplicationError("submitted verdict path must stay inside the evidence pack") from exc
    output = _managed(pack, output_relative)
    plan = load_plan(plan_path)
    verdict = load_verdict(candidate, pack_dir=pack, plan=plan)
    raw = candidate.read_bytes()
    if output.exists() and output.read_bytes() != raw:
        raise ApplicationError("submitted verdict already exists with different content")
    _atomic_write(pack, output_relative, raw)
    receipt = {
        "schema": SUBMISSION_SCHEMA,
        "project_id": verdict.project_id,
        "run_id": verdict.run_id,
        "case_id": verdict.case_id,
        "attempt_id": verdict.attempt_id,
        "proof_id": verdict.proof_id,
        "verdict_digest": _sha256(raw),
        "output": output.relative_to(pack).as_posix(),
    }
    receipt_path = pack / "verdict.submission.json"
    _atomic_write(
        pack,
        "verdict.submission.json",
        (json.dumps(receipt, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode(),
    )
    return {**receipt, "receipt": str(receipt_path)}
