"""Allure results streamed as tests end, for ``allurectl watch`` (L09, ADR-0026)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from testence.evidence import RUN_ID_ENV
from testence.export import export_run

ROOT = Path(__file__).parents[1]

_SUITE = """
import json
import os
from pathlib import Path

RESULTS = Path(os.environ["TESTENCE_ALLURE_RESULTS"])


def _names():
    return sorted(
        json.loads(path.read_text(encoding="utf-8"))["fullName"]
        for path in RESULTS.glob("*-result.json")
    )


def test_1_first():
    assert _names() == []


def test_2_second():
    # The first result is already on disk while the run is still going.
    assert _names() == ["test_stream#test_1_first"]


def test_3_fails():
    assert 1 == 2
"""


def _run(tmp_path: Path, suite: str, *args: str) -> tuple[subprocess.CompletedProcess, Path]:
    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    (project / "test_stream.py").write_text(suite, encoding="utf-8")
    (project / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    results = tmp_path / "allure-results"
    env = os.environ.copy()
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env.pop(RUN_ID_ENV, None)
    env["TESTENCE_ALLURE_RESULTS"] = str(results)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "src"), value] if (value := env.get("PYTHONPATH")) else [str(ROOT / "src")]
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "testence.pytest_plugin",
            "--rootdir",
            str(project),
            "--testence-runs-root",
            str(tmp_path / "runs"),
            "-p",
            "no:cacheprovider",
            "-q",
            *args,
        ],
        cwd=project,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    return result, results


def _files(directory: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in sorted(directory.iterdir()) if path.is_file()}


def test_results_appear_one_by_one_and_match_the_post_run_export(tmp_path):
    result, streamed = _run(tmp_path, _SUITE)
    # test_1 and test_2 prove the order from inside the run; test_3 fails on purpose.
    assert "1 failed, 2 passed" in result.stdout, result.stdout + result.stderr

    (run_dir,) = [path for path in (tmp_path / "runs").iterdir() if path.is_dir()]
    export_run(run_dir, "allure", tmp_path / "post")
    assert _files(streamed) == _files(tmp_path / "post")
    names = {
        json.loads(data)["fullName"]
        for name, data in _files(streamed).items()
        if name.endswith("-result.json")
    }
    assert names == {f"test_stream#test_{n}" for n in ("1_first", "2_second", "3_fails")}
    assert (streamed / "environment.properties").is_file()
    assert not list(tmp_path.glob(".allure-results.staging-*")), "no staging directory remains"


def test_a_killed_run_keeps_the_results_it_finished(tmp_path):
    suite = (
        "import os\n\n"
        "def test_1(): assert True\n\n"
        "def test_2(): assert True\n\n"
        "def test_3(): os._exit(1)\n\n"
        "def test_4(): assert True\n"
    )
    result, streamed = _run(tmp_path, suite)
    assert result.returncode == 1
    documents = [
        json.loads(path.read_text(encoding="utf-8")) for path in streamed.glob("*-result.json")
    ]
    assert sorted(doc["fullName"] for doc in documents) == [
        "test_stream#test_1",
        "test_stream#test_2",
    ]
    assert all(doc["status"] == "passed" for doc in documents)


def test_parallel_workers_stream_each_result_once(tmp_path):
    suite = "\n".join(f"def test_{n}(): assert True\n" for n in range(6))
    result, streamed = _run(tmp_path, suite, "-p", "xdist.plugin", "-n", "2")
    assert result.returncode == 0, result.stdout + result.stderr
    names = [
        json.loads(path.read_text(encoding="utf-8"))["fullName"]
        for path in streamed.glob("*-result.json")
    ]
    assert sorted(names) == sorted(f"test_stream#test_{n}" for n in range(6))
