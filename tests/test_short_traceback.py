"""A failure traceback starts at the test (stage 6, T01).

A failed ``ex.click`` printed 191 lines with the test's own line 94th: Playwright's
stack, the step's cause chain and the step machinery came first. The plugin now hides
the frames of Testence and Playwright below the test's deepest own frame and says how
many it hid; ``--testence-full-trace``, ``TESTENCE_FULL_TRACE=1`` and pytest's
``--full-trace`` keep them.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import _pytest
import playwright
import pytest

import testence
from testence.dsl.steps import StepFailed
from testence.evidence import RUN_ID_ENV
from testence.tracebacks import FULL_TRACE_ENV, FULL_TRACE_HINT, shorten
from tests.mock_app import PASSWORD, MockApp
from tests.mock_app import USER as LOGIN
from tests.owned_pytest import run_pytest

ROOT = Path(__file__).parents[1]

RUNNER = str(Path(_pytest.__file__).parent / "synthetic_runner.py")
TESTENCE = str(Path(testence.__file__).parent / "synthetic_step.py")
PLAYWRIGHT = str(Path(playwright.__file__).parent / "synthetic_locator.py")
OWN = str(ROOT / "synthetic_project" / "helpers.py")
GENERATED = "<string>"
STEP_MACHINERY = os.path.join("dsl", "steps.py")


def _function(filename: str, source: str, **names: Any) -> Any:
    namespace: dict[str, Any] = dict(names)
    exec(compile(source, filename, "exec"), namespace)  # noqa: S102 - synthetic frames
    return namespace["frame"]


def _excinfo(*filenames: str) -> pytest.ExceptionInfo[BaseException]:
    """An exception raised through one frame per file, caught where pytest's runner
    would catch it."""
    call = None
    for filename in reversed(filenames):
        call = _function(
            filename,
            "def frame():\n    if after is None:\n        raise ValueError('boom')\n    after()\n",
            after=call,
        )
    catch = _function(
        RUNNER,
        "def frame(call):\n    try:\n        call()\n    except BaseException as exc:\n"
        "        return exc\n",
    )
    return pytest.ExceptionInfo.from_exception(catch(call))


def _files(excinfo: pytest.ExceptionInfo[BaseException]) -> list[str]:
    files = []
    tb = excinfo.tb
    while tb is not None:
        files.append(tb.tb_frame.f_code.co_filename)
        tb = tb.tb_next
    return files


@pytest.mark.parametrize(
    ("chain", "kept", "hidden"),
    [
        # The step and Playwright below the test go.
        ((OWN, TESTENCE, PLAYWRIGHT), [RUNNER, OWN], 2),
        # The deepest own frame stays, even when Testence called back into it.
        ((OWN, TESTENCE, OWN, TESTENCE), [RUNNER, OWN, TESTENCE, OWN], 1),
        # Generated code (a dataclass __init__) is not the project's own frame.
        ((OWN, GENERATED, TESTENCE), [RUNNER, OWN], 2),
    ],
)
def test_frames_below_the_deepest_own_frame_are_hidden(chain, kept, hidden):
    excinfo = _excinfo(*chain)

    assert shorten(excinfo) == hidden
    assert _files(excinfo) == kept
    assert len(excinfo.traceback) == len(kept)


@pytest.mark.parametrize(
    "chain",
    [
        # Playwright called directly: Testence took no part, its trace is not ours to cut.
        (OWN, PLAYWRIGHT),
        # A failure inside a Testence fixture has no frame of the project to start at.
        (TESTENCE, PLAYWRIGHT),
        # A plain assertion in the test.
        (OWN,),
    ],
)
def test_a_trace_testence_did_not_shape_is_left_alone(chain):
    excinfo = _excinfo(*chain)

    assert shorten(excinfo) == 0
    assert _files(excinfo) == [RUNNER, *chain]


def test_a_failed_step_drops_its_displayed_cause_and_keeps_it_on_the_exception():
    locate = _function(PLAYWRIGHT, "def frame():\n    raise TimeoutError('Locator.click')\n")
    step = _function(
        TESTENCE,
        "def frame():\n    try:\n        locate()\n    except Exception as exc:\n"
        "        raise StepFailed('click it', exc) from exc\n",
        locate=locate,
        StepFailed=StepFailed,
    )
    test = _function(OWN, "def frame():\n    step()\n", step=step)
    catch = _function(
        RUNNER,
        "def frame(call):\n    try:\n        call()\n    except BaseException as exc:\n"
        "        return exc\n",
    )
    excinfo = pytest.ExceptionInfo.from_exception(catch(test))
    cause = excinfo.value.cause  # type: ignore[attr-defined]

    # The step's own frame, then the cause's two frames.
    assert shorten(excinfo) == 3
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__suppress_context__
    assert isinstance(cause, TimeoutError)
    assert "TimeoutError: Locator.click" in str(excinfo.value)


def _env(**extra: str) -> dict[str, str]:
    env = os.environ.copy()
    env.pop(RUN_ID_ENV, None)
    env.pop(FULL_TRACE_ENV, None)
    env.update(PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTHONPATH=str(ROOT / "src"), **extra)
    return env


def _pytest_command(project: Path, *extra: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "pytest",
        "-p",
        "testence.pytest_plugin",
        "--rootdir",
        str(project),
        "-p",
        "no:cacheprovider",
        *extra,
    ]


def _section(output: str, test: str) -> str:
    start = output.index(f" {test} _")
    rest = output[start:]
    ends = [rest.find(marker, 1) for marker in ("\n____", "\n====") if rest.find(marker, 1) > 0]
    return rest[: min(ends)] if ends else rest


BROWSER_SUITE = """
from helpers import press
from testence.engine import Target

MISSING = Target("role", "button", name="Does not exist")


def test_missing_button(ex):
    ex.goto("/app")
    ex.click(MISSING)  # THE-TEST-LINE


def test_through_a_helper(ex):
    ex.goto("/app")
    press(ex, MISSING)  # THE-CALLER-LINE


def test_plain_assert(ex):
    assert 1 == 2  # THE-ASSERT-LINE
"""

HELPERS = """
def press(ex, target):
    ex.click(target)  # THE-HELPER-LINE
"""


def test_a_failed_step_prints_the_test_line_first_and_the_ledger_keeps_it(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "test_buttons.py").write_text(BROWSER_SUITE.lstrip(), encoding="utf-8")
    (project / "helpers.py").write_text(HELPERS.lstrip(), encoding="utf-8")
    (project / "testence.json").write_text(
        json.dumps({"auth": "form", "login_path": "/login", "success_url_contains": "/app"}),
        encoding="utf-8",
    )
    with MockApp() as app:
        result = run_pytest(
            _pytest_command(project, "--testence-headless", "-q"),
            cwd=project,
            env=_env(
                TESTENCE_BASE_URL=app.base_url,
                TESTENCE_USER=LOGIN,
                TESTENCE_PASSWORD=PASSWORD,
                TESTENCE_TIMEOUT_MS="2000",
            ),
            timeout=300,
        )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "3 failed" in result.stdout

    direct = _section(result.stdout, "test_missing_button")
    lines = direct.splitlines()
    assert next(i for i, line in enumerate(lines) if "THE-TEST-LINE" in line) < 10, direct
    assert "step failed: click role='button'" in direct
    assert "waiting for get_by_role" in direct  # Playwright's call log, in the message
    assert "playwright" not in direct.replace("Playwright", ""), direct
    assert STEP_MACHINERY not in direct, direct
    assert FULL_TRACE_HINT in direct

    helper = _section(result.stdout, "test_through_a_helper")
    assert "THE-CALLER-LINE" in helper and "THE-HELPER-LINE" in helper, helper
    assert STEP_MACHINERY not in helper, helper

    plain = _section(result.stdout, "test_plain_assert")
    assert "THE-ASSERT-LINE" in plain
    assert FULL_TRACE_HINT not in plain

    run_dir = next((project / "runs").glob("*/run.jsonl")).parent
    ledger = "".join(path.read_text(encoding="utf-8") for path in run_dir.glob("run*.jsonl"))
    traces = [
        trace
        for doc in map(json.loads, ledger.splitlines())
        for trace in [_find(doc, "error_trace")]
        if trace and "THE-TEST-LINE" in trace
    ]
    assert traces, ledger
    assert FULL_TRACE_HINT in traces[0]
    assert STEP_MACHINERY not in traces[0]


def _find(doc: Any, key: str) -> Any:
    if isinstance(doc, dict):
        if key in doc:
            return doc[key]
        for value in doc.values():
            found = _find(value, key)
            if found is not None:
                return found
    if isinstance(doc, list):
        for value in doc:
            found = _find(value, key)
            if found is not None:
                return found
    return None


NO_BROWSER_SUITE = """
from testence.engine import Target


def test_bad_target():
    Target("nonsense", "x")  # THE-TEST-LINE
"""


@pytest.mark.parametrize(
    ("arguments", "extra_env", "full"),
    [
        ((), {}, False),
        (("--testence-full-trace",), {}, True),
        ((), {FULL_TRACE_ENV: "1"}, True),
        (("--full-trace",), {}, True),
    ],
    ids=["default", "flag", "env", "pytest-full-trace"],
)
def test_the_full_trace_switches_keep_testence_frames(
    tmp_path: Path, arguments: tuple[str, ...], extra_env: dict[str, str], full: bool
):
    project = tmp_path / "project"
    project.mkdir()
    (project / "test_target.py").write_text(NO_BROWSER_SUITE.lstrip(), encoding="utf-8")
    result = run_pytest(
        _pytest_command(project, *arguments),
        cwd=project,
        env=_env(**extra_env),
        timeout=120,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    # One test: the whole output is its failure. A full trace can exceed what the
    # owned runner keeps, so the output is not split into sections.
    output = result.stdout
    assert "THE-TEST-LINE" in output
    assert "unknown target kind: 'nonsense'" in output
    assert ("protocol.py" in output) is full, output
    assert (FULL_TRACE_HINT in output) is not full, output
