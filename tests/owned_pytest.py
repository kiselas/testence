"""Nested pytest runs own their descendants and retain bounded timeout diagnostics."""

from __future__ import annotations

import subprocess
from collections.abc import Mapping
from pathlib import Path

from testence._process import run_owned


def run_pytest(
    command: list[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout: float = 300,
) -> subprocess.CompletedProcess[str]:
    result = run_owned(command, cwd=cwd, env=env, timeout=timeout, output_limit=12_000)
    if result.timed_out:
        # Preserve the suite's timeout report hook and never turn a deadline into
        # a normal pytest failure or a retry.
        raise subprocess.TimeoutExpired(
            command, timeout, output=result.stdout, stderr=result.stderr
        )
    assert result.returncode is not None
    return subprocess.CompletedProcess(command, result.returncode, result.stdout, result.stderr)
