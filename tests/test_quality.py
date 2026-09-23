from __future__ import annotations

import errno
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pytest

import testence.quality as quality_module
from testence.cli import main
from testence.evidence import EvidenceWriter
from testence.quality import (
    QUALITY_PACK_SCHEMA,
    QualityPackError,
    apply_quality_pack,
    load_quality_pack,
    quality_summary,
    rollback_quality_pack,
)


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _pack(root: Path, version: str, content: str) -> Path:
    root.mkdir(parents=True)
    policy = root / "quality" / "policy.json"
    policy.parent.mkdir(parents=True)
    policy.write_text(content, encoding="utf-8", newline="\n")
    manifest = {
        "schema": QUALITY_PACK_SCHEMA,
        "name": "web-r1",
        "version": version,
        "files": [{"path": "quality/policy.json", "sha256": _sha(policy.read_bytes())}],
        "policy": {
            "owners": ["qa-platform", "qa-service"],
            "risks": ["critical", "normal"],
            "selection": {"critical": "always"},
        },
    }
    (root / "quality-pack.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def _project(root: Path, project_id: str) -> Path:
    root.mkdir(parents=True)
    (root / "testence.json").write_text(json.dumps({"project_id": project_id}), encoding="utf-8")
    return root


def test_three_projects_update_override_conflict_and_rollback(tmp_path):
    pack_v1 = load_quality_pack(_pack(tmp_path / "pack-v1", "1.0.0", '{"level":"normal"}'))
    pack_v2_dir = _pack(tmp_path / "pack-v2", "1.1.0", '{"level":"strict"}')
    projects = [_project(tmp_path / name, name) for name in ("catalog", "billing", "admin")]
    first = [apply_quality_pack(pack_v1.root, project) for project in projects]
    assert [result["status"] for result in first] == ["applied"] * 3

    billing_policy = projects[1] / "quality" / "policy.json"
    billing_policy.write_text('{"level":"local"}', encoding="utf-8")
    override = {
        "overrides": [
            {
                "path": "quality/policy.json",
                "reason": "service migration",
                "owner": "qa-service",
                "expires": (date.today() + timedelta(days=7)).isoformat(),
            }
        ]
    }
    (projects[1] / ".testence" / "quality-overrides.json").write_text(
        json.dumps(override), encoding="utf-8"
    )
    admin_policy = projects[2] / "quality" / "policy.json"
    admin_policy.write_text('{"level":"unowned"}', encoding="utf-8")

    catalog = apply_quality_pack(pack_v2_dir, projects[0])
    billing = apply_quality_pack(pack_v2_dir, projects[1])
    admin = apply_quality_pack(pack_v2_dir, projects[2])

    assert catalog["changed"] == ["quality/policy.json"]
    assert billing["status"] == "applied" and billing["overrides"][0]["owner"] == "qa-service"
    assert billing_policy.read_text(encoding="utf-8") == '{"level":"local"}'
    assert admin["status"] == "conflict" and admin["conflicts"][0]["path"] == "quality/policy.json"
    assert apply_quality_pack(pack_v2_dir, projects[2])["status"] == "conflict"

    rollback = rollback_quality_pack(projects[0], pack_v1.digest)
    assert rollback["status"] == "rolled_back"
    assert (projects[0] / "quality" / "policy.json").read_text(
        encoding="utf-8"
    ) == '{"level":"normal"}'
    assert (projects[0] / ".testence" / "quality-pack-history").is_dir()


def test_quality_pack_rejects_digest_traversal_and_credentials(tmp_path):
    pack = _pack(tmp_path / "pack", "1", "safe")
    document = json.loads((pack / "quality-pack.json").read_text(encoding="utf-8"))
    document["files"][0]["sha256"] = "sha256:" + "0" * 64
    (pack / "quality-pack.json").write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(QualityPackError, match="digest mismatch"):
        load_quality_pack(pack)

    document["files"] = [{"path": "../outside", "sha256": "sha256:" + "0" * 64}]
    (pack / "quality-pack.json").write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(QualityPackError, match="escapes"):
        load_quality_pack(pack)


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("quality/A.json", "quality/a.json"),
        ("Quality/policy.json", "quality/policy.json"),
        # NFC and NFD spellings of the same name: one file on APFS.
        ("quality/café.json", "quality/café.json"),
    ],
)
def test_pack_rejects_paths_that_collide_on_case_insensitive_file_systems(
    tmp_path: Path, first: str, second: str
):
    root = tmp_path / "pack"
    source = root / first
    source.parent.mkdir(parents=True)
    source.write_bytes(b"{}")
    # Only the first spelling needs to exist: the collision is refused before the
    # second is read, so macOS and Windows see this error, not a digest mismatch.
    entries = [{"path": path, "sha256": _sha(b"{}")} for path in (first, second)]
    (root / "quality-pack.json").write_text(
        json.dumps(
            {
                "schema": QUALITY_PACK_SCHEMA,
                "name": "case",
                "version": "1",
                "files": entries,
                "policy": {"owners": [], "risks": [], "selection": {}},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(QualityPackError, match="name the same file on case-insensitive"):
        load_quality_pack(root)


def test_pack_accepts_distinct_names_that_only_share_a_prefix(tmp_path: Path):
    pack = _multi_pack(tmp_path / "pack", "1", {"quality/a.json": "a", "quality/ab.json": "b"})

    assert [item["path"] for item in load_quality_pack(pack).files] == [
        "quality/a.json",
        "quality/ab.json",
    ]


def test_rollback_rejects_a_corrupt_snapshot_before_changing_files(tmp_path: Path):
    pack_v1 = load_quality_pack(_pack(tmp_path / "pack-v1", "1.0.0", "first"))
    pack_v2 = _pack(tmp_path / "pack-v2", "2.0.0", "second")
    project = _project(tmp_path / "project", "catalog")
    apply_quality_pack(pack_v1.root, project)
    apply_quality_pack(pack_v2, project)
    active_before = (project / "quality/policy.json").read_bytes()
    snapshot = (
        project
        / ".testence/quality-pack-history"
        / pack_v1.digest.replace(":", "-")
        / "quality/policy.json"
    )
    snapshot.write_bytes(b"corrupt")

    with pytest.raises(QualityPackError, match="history digest mismatch"):
        rollback_quality_pack(project, pack_v1.digest)

    assert (project / "quality/policy.json").read_bytes() == active_before
    assert (
        json.loads((project / ".testence/quality-pack.lock.json").read_text())["version"] == "2.0.0"
    )


def _multi_pack(root: Path, version: str, values: dict[str, str]) -> Path:
    root.mkdir()
    files = []
    for relative, content in values.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        files.append({"path": relative, "sha256": _sha(target.read_bytes())})
    (root / "quality-pack.json").write_text(
        json.dumps(
            {
                "schema": QUALITY_PACK_SCHEMA,
                "name": "multi",
                "version": version,
                "files": files,
                "policy": {"owners": [], "risks": [], "selection": {}},
            }
        ),
        encoding="utf-8",
    )
    return root


def test_apply_preflights_all_files_before_the_first_change(tmp_path: Path):
    v1 = _multi_pack(tmp_path / "v1", "1", {"quality/a": "a1", "quality/b": "b1"})
    v2 = _multi_pack(tmp_path / "v2", "2", {"quality/a": "a2", "quality/b": "b2"})
    project = _project(tmp_path / "project", "catalog")
    apply_quality_pack(v1, project)
    (project / "quality/b").write_text("human", encoding="utf-8")

    result = apply_quality_pack(v2, project)

    assert result["status"] == "conflict"
    assert (project / "quality/a").read_text(encoding="utf-8") == "a1"
    assert (project / "quality/b").read_text(encoding="utf-8") == "human"


def test_dry_run_returns_the_full_plan_without_writing_state(tmp_path: Path):
    pack = _multi_pack(tmp_path / "pack", "1", {"quality/a": "a1", "quality/b": "b1"})
    project = _project(tmp_path / "project", "catalog")
    before = (project / "testence.json").read_bytes()

    result = apply_quality_pack(pack, project, dry_run=True)

    assert result["status"] == "planned"
    assert result["plan"] == {
        "add": ["quality/a", "quality/b"],
        "replace": [],
        "delete": [],
        "keep": [],
        "preserve": [],
        "conflicts": [],
    }
    assert (project / "testence.json").read_bytes() == before
    assert not (project / "quality").exists()
    assert not (project / ".testence/quality-sync.json").exists()


def test_apply_restores_every_file_if_commit_is_interrupted(tmp_path: Path, monkeypatch):
    v1 = _multi_pack(tmp_path / "v1", "1", {"quality/a": "a1", "quality/b": "b1"})
    v2 = _multi_pack(tmp_path / "v2", "2", {"quality/a": "a2", "quality/b": "b2"})
    project = _project(tmp_path / "project", "catalog")
    apply_quality_pack(v1, project)
    lock_before = (project / ".testence/quality-pack.lock.json").read_bytes()
    original = quality_module.atomic_write_bytes
    interrupted = False

    def fail_once(root: Path, relative: str, raw: bytes):
        nonlocal interrupted
        if relative == "quality/b" and not interrupted:
            interrupted = True
            raise OSError("simulated interruption")
        return original(root, relative, raw)

    monkeypatch.setattr(quality_module, "atomic_write_bytes", fail_once)

    with pytest.raises(OSError, match="simulated interruption"):
        apply_quality_pack(v2, project)

    assert (project / "quality/a").read_text(encoding="utf-8") == "a1"
    assert (project / "quality/b").read_text(encoding="utf-8") == "b1"
    assert (project / ".testence/quality-pack.lock.json").read_bytes() == lock_before
    transactions = project / ".testence/quality-transactions"
    assert not transactions.exists() or not list(transactions.iterdir())


def test_cleanup_retries_transient_windows_delete_without_reapplying(tmp_path: Path, monkeypatch):
    pack = _pack(tmp_path / "pack", "1", "safe")
    project = _project(tmp_path / "project", "catalog")
    original = quality_module.shutil.rmtree
    calls = []

    def busy_once(directory):
        calls.append(directory)
        if len(calls) == 1:
            error = OSError("directory still pending deletion")
            error.winerror = 145
            raise error
        return original(directory)

    monkeypatch.setattr(quality_module.shutil, "rmtree", busy_once)
    result = apply_quality_pack(pack, project)
    assert result["status"] == "applied"
    assert len(calls) == 2
    assert calls[0] == calls[1]
    assert not list((project / ".testence/quality-transactions").iterdir())


def test_cleanup_propagates_nontransient_errors(tmp_path: Path, monkeypatch):
    directory = tmp_path / ".testence/quality-transactions/failed"
    directory.mkdir(parents=True)

    def denied(_directory):
        raise PermissionError("denied")

    monkeypatch.setattr(quality_module.shutil, "rmtree", denied)
    with pytest.raises(PermissionError, match="denied"):
        quality_module._cleanup_transaction(tmp_path, ".testence/quality-transactions/failed")
    assert directory.exists()


def test_recovery_skips_file_manager_metadata_but_not_unknown_entries(tmp_path: Path):
    v1 = _multi_pack(tmp_path / "v1", "1", {"quality/a": "a1"})
    v2 = _multi_pack(tmp_path / "v2", "2", {"quality/a": "a2"})
    project = _project(tmp_path / "project", "catalog")
    apply_quality_pack(v1, project)
    transactions = project / ".testence/quality-transactions"
    transactions.mkdir(exist_ok=True)
    # Finder writes this as soon as someone opens the hidden folder on macOS.
    (transactions / ".DS_Store").write_bytes(b"Bud1")

    apply_quality_pack(v2, project)

    assert (project / "quality/a").read_text(encoding="utf-8") == "a2"
    (transactions / "stray").mkdir()
    with pytest.raises(QualityPackError, match="incomplete quality transaction journal: stray"):
        apply_quality_pack(v1, project)


def test_apply_rejects_a_concurrent_quality_operation(tmp_path: Path):
    pack = _pack(tmp_path / "pack", "1", "safe")
    project = _project(tmp_path / "project", "catalog").resolve()

    with quality_module._quality_lock(project):
        with pytest.raises(QualityPackError, match="operation is in progress"):
            apply_quality_pack(pack, project)


@pytest.mark.parametrize("code", [errno.ENOLCK, getattr(errno, "ENOTSUP", errno.EINVAL)])
def test_unsupported_file_locking_is_not_reported_as_a_concurrent_operation(
    tmp_path: Path, monkeypatch, code: int
):
    # An SMB or NFS mount can refuse flock outright. That is not "someone else holds
    # the lock", and saying so sends the user after a process that does not exist.
    pack = _pack(tmp_path / "pack", "1", "safe")
    project = _project(tmp_path / "project", "catalog").resolve()

    def unsupported(_fileno: int) -> None:
        raise OSError(code, os.strerror(code))

    monkeypatch.setattr(quality_module, "_try_lock", unsupported)

    with pytest.raises(QualityPackError, match="may not support file locks") as caught:
        apply_quality_pack(pack, project)
    assert "in progress" not in str(caught.value)
    assert not (project / "quality/policy.json").exists()


def test_recovery_preserves_a_human_change_and_keeps_snapshots(tmp_path: Path, monkeypatch):
    v1 = _multi_pack(tmp_path / "v1", "1", {"quality/a": "a1", "quality/b": "b1"})
    v2 = _multi_pack(tmp_path / "v2", "2", {"quality/a": "a2", "quality/b": "b2"})
    project = _project(tmp_path / "project", "catalog")
    apply_quality_pack(v1, project)
    original = quality_module.atomic_write_bytes
    interrupted = False

    def conflict_during_recovery(root: Path, relative: str, raw: bytes):
        nonlocal interrupted
        if relative == "quality/b" and not interrupted:
            interrupted = True
            (project / "quality/a").write_text("human-after-a2", encoding="utf-8")
            raise OSError("simulated interruption after human edit")
        return original(root, relative, raw)

    monkeypatch.setattr(quality_module, "atomic_write_bytes", conflict_during_recovery)
    with pytest.raises(QualityPackError, match="recovery conflicts"):
        apply_quality_pack(v2, project)
    monkeypatch.setattr(quality_module, "atomic_write_bytes", original)

    assert (project / "quality/a").read_text(encoding="utf-8") == "human-after-a2"
    transaction_root = project / ".testence/quality-transactions"
    journals = list(transaction_root.glob("*/journal.json"))
    assert len(journals) == 1
    assert json.loads(journals[0].read_text(encoding="utf-8"))["state"] == "conflict"
    assert list(transaction_root.glob("*/old/*.bin"))

    with pytest.raises(QualityPackError, match="recovery conflicts"):
        apply_quality_pack(v2, project)


def test_next_public_apply_recovers_after_a_real_process_kill(tmp_path: Path):
    v1 = _multi_pack(tmp_path / "v1", "1", {"quality/a": "a1", "quality/b": "b1"})
    v2 = _multi_pack(tmp_path / "v2", "2", {"quality/a": "a2", "quality/b": "b2"})
    project = _project(tmp_path / "project", "catalog")
    apply_quality_pack(v1, project)
    marker = tmp_path / "published-first-target"
    child = tmp_path / "kill_during_apply.py"
    child.write_text(
        """import os
import sys
import time
from pathlib import Path
import testence.quality as quality

pack, project, marker = map(Path, sys.argv[1:])
original = quality.atomic_write_bytes
def delayed(root, relative, raw):
    result = original(root, relative, raw)
    if relative == "quality/a":
        marker.write_text(str(os.getpid()), encoding="utf-8")
        time.sleep(60)
    return result
quality.atomic_write_bytes = delayed
quality.apply_quality_pack(pack, project)
""",
        encoding="utf-8",
    )
    process = subprocess.Popen(
        [sys.executable, str(child), str(v2), str(project), str(marker)],
        cwd=Path(__file__).parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        for _attempt in range(200):
            if marker.is_file():
                break
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                pytest.fail(f"child exited before kill point: {stdout}\n{stderr}")
            time.sleep(0.025)
        else:
            pytest.fail("child did not reach the transaction kill point")
        # Windows venv Python can be a redirector. Kill the worker that actually
        # holds the lock, not only its launcher process.
        os.kill(int(marker.read_text(encoding="utf-8")), signal.SIGTERM)
        process.wait(timeout=10)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)

    recovered = apply_quality_pack(v1, project)

    assert recovered["status"] == "applied"
    assert (project / "quality/a").read_text(encoding="utf-8") == "a1"
    assert (project / "quality/b").read_text(encoding="utf-8") == "b1"
    transactions = project / ".testence/quality-transactions"
    assert not transactions.exists() or not list(transactions.iterdir())


def test_quality_apply_refuses_a_junction_state_root(tmp_path: Path):
    if os.name != "nt":
        pytest.skip("Windows junction coverage")
    pack = _pack(tmp_path / "pack", "1", "safe")
    project = _project(tmp_path / "project", "catalog")
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel"
    sentinel.write_bytes(b"unchanged")
    link = project / ".testence"
    command = f"New-Item -ItemType Junction -Path '{link}' -Target '{outside}'"
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode:
        pytest.skip(f"junctions are unavailable: {completed.stderr.strip()}")
    try:
        with pytest.raises(QualityPackError, match="link or reparse"):
            apply_quality_pack(pack, project)
        assert sentinel.read_bytes() == b"unchanged"
        assert sorted(item.name for item in outside.iterdir()) == ["sentinel"]
    finally:
        os.rmdir(link)


def _run(root: Path, project: str, run_id: str, status: str) -> Path:
    writer = EvidenceWriter(root, run_id=run_id, worker="", project_id=project)
    writer.emit("run.start", testence="test")
    writer.emit(
        "test.start",
        test="tests/test_case.py::test_shared_name",
        case_id="shared-name",
        owner="qa-platform",
        risk="critical",
    )
    writer.emit(
        "test.end",
        test="tests/test_case.py::test_shared_name",
        case_id="shared-name",
        status=status,
        error="persistence mismatch" if status == "failed" else "",
    )
    writer.emit(
        "run.end",
        run_status="failed" if status == "failed" else "passed",
        exit_code=1 if status == "failed" else 0,
    )
    writer.close()
    return writer.run_dir


def test_summary_is_namespaced_filterable_and_contains_no_raw_artifacts(tmp_path, capsys):
    catalog = _run(tmp_path / "runs", "catalog", "r-catalog", "failed")
    billing = _run(tmp_path / "runs", "billing", "r-billing", "passed")

    result = quality_summary([catalog, billing])

    assert set(result["projects"]) == {"catalog", "billing"}
    assert {item["project_id"] for item in result["actionable"]} == {"catalog", "billing"}
    assert any(item["kind"] == "violation" for item in result["actionable"])
    assert any(item["kind"] == "missing_proof" for item in result["actionable"])
    assert "events" not in result and "artifacts" not in result

    assert (
        main(["quality", "summary", str(catalog), str(billing), "--project", "catalog", "--json"])
        == 0
    )
    filtered = json.loads(capsys.readouterr().out)
    assert set(filtered["projects"]) == {"catalog"}
    assert {item["project_id"] for item in filtered["actionable"]} == {"catalog"}
