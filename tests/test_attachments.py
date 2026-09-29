"""A test's own files travel with its evidence (product review 2026-09-28, P1-6).

A payload the test built, a server log excerpt or a picture had nowhere to go: the pack
held only what Testence collected. ``ex.attach`` and ``allure.attach`` keep them,
redacted when they are text, and every exporter ships them under its attachment policy.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from testence.evidence import RUN_ID_ENV, EvidenceWriter
from testence.evidence.writer import MAX_ATTACHMENT_BYTES

ROOT = Path(__file__).parents[1]
PNG = b"\x89PNG\r\n\x1a\n" + b"not really a picture"
PASSWORD = "hunter2-attached"


def _writer(tmp_path: Path) -> EvidenceWriter:
    return EvidenceWriter(tmp_path, run_id="r-attach", worker="")


def test_text_is_redacted_and_kept(tmp_path):
    writer = _writer(tmp_path)
    try:
        fields = writer.attach(
            "t::a", "payload.json", json.dumps({"password": PASSWORD, "name": "edge"})
        )
    finally:
        writer.close()
    stored = (writer.run_dir / fields["path"]).read_text(encoding="utf-8")
    assert PASSWORD not in stored and "edge" in stored
    assert fields["redaction"] == "redacted" and fields["media_type"] == "application/json"


def test_a_secret_known_at_run_time_is_masked_in_free_text(tmp_path):
    writer = _writer(tmp_path)
    writer.remember_secret("run-time-token-9876")
    try:
        fields = writer.attach("t::a", "server.log", "GET /x token=run-time-token-9876 ok")
    finally:
        writer.close()
    assert "run-time-token-9876" not in (writer.run_dir / fields["path"]).read_text(
        encoding="utf-8"
    )


def test_a_binary_file_is_stored_as_given_and_says_so(tmp_path):
    writer = _writer(tmp_path)
    try:
        fields = writer.attach("t::a", "shot.png", PNG)
    finally:
        writer.close()
    assert (writer.run_dir / fields["path"]).read_bytes() == PNG
    assert fields["redaction"] == "none" and fields["media_type"] == "image/png"


def test_names_do_not_collide_and_stay_inside_the_run(tmp_path):
    writer = _writer(tmp_path)
    try:
        first = writer.attach("t::a", "../../out.txt", "one")
        second = writer.attach("t::a", "../../out.txt", "two")
    finally:
        writer.close()
    assert first["path"] != second["path"]
    for fields in (first, second):
        assert (writer.run_dir / fields["path"]).resolve().is_relative_to(writer.run_dir.resolve())


def test_refusals_are_readable(tmp_path):
    writer = _writer(tmp_path)
    try:
        with pytest.raises(ValueError, match="needs a name"):
            writer.attach("t::a", "  ", "x")
        with pytest.raises(ValueError, match="limit"):
            writer.attach("t::a", "big.bin", b"0" * (MAX_ATTACHMENT_BYTES + 1))
        with pytest.raises(ValueError, match="not UTF-8"):
            writer.attach("t::a", "odd.txt", b"\xff\xfe\x00", "text/plain")
    finally:
        writer.close()


SUITE = f"""
import allure
from types import SimpleNamespace

from testence.dsl import Actions


def test_it_attaches(testence_writer, request):
    ex = Actions(SimpleNamespace(), testence_writer, request.node.nodeid)
    ex.attach("payload.json", '{{"password": "{PASSWORD}", "name": "edge"}}')
    ex.attach("shot.png", {PNG!r})
    allure.attach("a server line", name="server.log", attachment_type=allure.attachment_type.TEXT)
"""


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop(RUN_ID_ENV, None)
    env.update(PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTHONPATH=str(ROOT / "src"))
    return env


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory) -> Path:
    project = tmp_path_factory.mktemp("attached")
    (project / "test_attach.py").write_text(SUITE.lstrip(), encoding="utf-8")
    (project / "testence.json").write_text("{}", encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "testence.pytest_plugin",
            "-p",
            "allure_commons",
            "--rootdir",
            str(project),
            "-p",
            "no:cacheprovider",
            "-q",
        ],
        cwd=project,
        env=_env(),
        text=True,
        capture_output=True,
        check=False,
        timeout=300,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return next((project / "runs").iterdir())


def _events(run: Path) -> list[dict]:
    lines = (run / "run.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def test_the_run_records_ex_and_allure_attachments(run_dir):
    kept = [event for event in _events(run_dir) if event["kind"] == "attachment"]
    assert sorted(event["name"] for event in kept) == ["payload.json", "server.log", "shot.png"]
    assert PASSWORD not in (run_dir / "run.jsonl").read_text(encoding="utf-8")


def _export(run: Path, target: str, out: Path, policy: str) -> Path:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "testence.cli",
            "export",
            str(run),
            "--to",
            target,
            "-o",
            str(out),
            "--attachments",
            policy,
        ],
        env=_env(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return out


def _shipped(out: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in out.rglob("*") if path.is_file()}


@pytest.mark.parametrize("target", ["allure", "ctrf", "junit"])
def test_a_full_export_ships_all_three(run_dir, tmp_path, target):
    files = _shipped(_export(run_dir, target, tmp_path / target, "full"))
    joined = b"".join(files.values())
    assert b"a server line" in joined and b"edge" in joined
    assert PNG in files.values()
    assert PASSWORD.encode() not in joined


@pytest.mark.parametrize("target", ["allure", "ctrf", "junit"])
def test_minimal_ships_the_text_and_not_the_picture(run_dir, tmp_path, target):
    files = _shipped(_export(run_dir, target, tmp_path / target, "minimal"))
    joined = b"".join(files.values())
    assert b"a server line" in joined
    assert PNG not in files.values()


@pytest.mark.parametrize("target", ["allure", "ctrf", "junit"])
def test_none_ships_nothing_of_it(run_dir, tmp_path, target):
    files = _shipped(_export(run_dir, target, tmp_path / target, "none"))
    joined = b"".join(files.values())
    assert b"a server line" not in joined and PNG not in files.values()


def test_an_allure_result_names_the_attachments(run_dir, tmp_path):
    out = _export(run_dir, "allure", tmp_path / "allure", "full")
    result = json.loads(next(out.glob("*-result.json")).read_text(encoding="utf-8"))
    names = {item["name"] for item in result["attachments"]}
    assert {"payload.json", "shot.png", "server.log"} <= names
