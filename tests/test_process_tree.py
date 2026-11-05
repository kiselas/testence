"""``ProcessTree``: kill an adopted process and its descendants, and nothing else."""

from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest

from testence._process import ProcessTree, descendants

from .process_driver import Driver, is_alive, wait_dead


def test_kill_reaches_the_process_and_a_child_it_started_after_adoption(tmp_path):
    driver = Driver(tmp_path)
    bystander = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
    try:
        child = driver.launch_browser()
        driver.tree.kill()
        assert wait_dead(driver.process.pid) and wait_dead(child)
        assert bystander.poll() is None
    finally:
        bystander.kill()
        bystander.wait(timeout=10)
        driver.cleanup()


def test_without_descendants_only_the_adopted_process_dies(tmp_path):
    driver = Driver(tmp_path, tree=False)
    child = None
    try:
        child = driver.launch_browser()
        driver.tree.kill()
        assert wait_dead(driver.process.pid)
        assert is_alive(child)
    finally:
        driver.cleanup()
        if child is not None:
            ProcessTree(child, descendants=False).kill()


def test_kill_is_safe_after_exit_and_more_than_once(tmp_path):
    driver = Driver(tmp_path)
    try:
        driver.tree.kill()
        assert wait_dead(driver.process.pid)
        driver.tree.kill()
        driver.tree.close()
        driver.tree.kill()
    finally:
        driver.process.wait(timeout=10)


@pytest.mark.skipif(os.name == "nt", reason="Windows keeps the PID reserved through a handle")
def test_a_reused_pid_is_not_killed(tmp_path, monkeypatch):
    victim = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
    try:
        tree = ProcessTree(victim.pid)
        # The recorded start no longer matches: as if the PID now belongs to another process.
        monkeypatch.setattr(tree, "_started", "Thu Jan  1 00:00:00 1970")
        tree.kill()
        time.sleep(0.3)
        assert victim.poll() is None
    finally:
        victim.kill()
        victim.wait(timeout=10)


@pytest.mark.skipif(os.name == "nt", reason="reads the POSIX process table")
def test_descendants_lists_the_tree_below_a_pid(tmp_path):
    driver = Driver(tmp_path)
    try:
        child = driver.launch_browser()
        assert descendants(driver.process.pid) == [child]
        assert descendants(child) == []
    finally:
        driver.cleanup()
