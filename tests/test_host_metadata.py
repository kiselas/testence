"""Metadata provider controls live only in isolated child interpreters."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from testence._process import run_owned

PROBE = """
import builtins, platform, sys, threading
from types import SimpleNamespace
mode = sys.argv[1]
calls = []
entered = threading.Event()
release = threading.Event()
def provider():
    calls.append(threading.current_thread().name)
    entered.set()
    if mode == 'error':
        raise OSError('synthetic metadata unavailable')
    if mode == 'concurrent':
        assert release.wait(3), 'probe release missing'
    return SimpleNamespace(system='SyntheticOS', release='R1')
real_uname = platform.uname
original_import = builtins.__import__
host_platform = SimpleNamespace(uname=provider, uname_result=platform.uname_result)
def scoped_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name == 'platform' and globals and globals.get('__name__') == 'testence.host':
        return host_platform
    return original_import(name, globals, locals, fromlist, level)
builtins.__import__ = scoped_import
try:
    import testence.pytest_plugin
    from testence import host
finally:
    builtins.__import__ = original_import
assert platform.uname is real_uname
assert builtins.__import__ is original_import
assert platform.system() != 'SyntheticOS'  # foreign calls cannot consume the host stub
assert calls == [], calls
assert not any(t.name == 'testence-host' for t in threading.enumerate())
if mode == 'values':
    assert host.system() == 'SyntheticOS'
    assert host.os_name() == 'SyntheticOS R1'
    assert calls == ['MainThread'], calls
elif mode == 'error':
    try:
        host.system()
    except OSError as error:
        assert str(error) == 'synthetic metadata unavailable'
    else:
        raise AssertionError('provider error hidden')
    assert calls == ['MainThread'], calls
elif mode == 'concurrent':
    results = []
    threads = [threading.Thread(target=lambda: results.append(host.os_name())) for _ in range(8)]
    for thread in threads:
        thread.start()
    assert entered.wait(3), 'provider not called'
    release.set()
    for thread in threads:
        thread.join(3)
    assert not any(t.is_alive() for t in threads)
    assert results == ['SyntheticOS R1'] * 8, results
    assert len(calls) == 1, calls
elif mode != 'import':
    raise AssertionError(mode)
print('metadata control passed:', mode)
"""


@pytest.mark.parametrize("mode", ["import", "values", "error", "concurrent"])
def test_host_metadata_is_lazy_exact_and_shared(mode):
    root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(root / "src")
    result = run_owned(
        [sys.executable, "-B", "-c", PROBE, mode],
        cwd=root,
        env=environment,
        timeout=15,
        output_limit=16000,
    )
    assert not result.timed_out, result.stdout + result.stderr
    assert result.returncode == 0, result.stdout + result.stderr
