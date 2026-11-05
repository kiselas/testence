"""``stop()`` has a deadline per step, and only kills what this engine started.

Playwright's sync calls cannot be cancelled. A wedged driver used to hold the suite
forever; now each step of the close (context, browser, driver) has a deadline, and a
step that outlives it ends the driver and browser the engine recorded when it started
them. The driver here is a real process tree, so what dies and what survives is observed
at the operating-system level, not mocked.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest

from testence._process import ProcessTree, descendants
from testence.engine.playwright_cdp import PlaywrightCdpEngine, _close_deadline, _driver_pid

from .process_driver import Driver, Step, is_alive, wait_dead


def engine_with(driver: Driver, *, hang: str | None, attached: bool = False, deadline: float = 1.0):
    calls: list[str] = []
    engine = PlaywrightCdpEngine(
        "http://127.0.0.1:9", cdp_url="http://127.0.0.1:9" if attached else None
    )
    engine.close_deadline_s = deadline
    engine._driver_tree = driver.tree
    engine._pw = Step(driver if hang == "driver.stop" else None, calls, "driver.stop")
    engine._browser = Step(driver if hang == "browser.process_close" else None, calls, "browser")
    engine._context = Step(driver if hang == "context.close" else None, calls, "context")
    engine._owns_context = True
    engine._launched_here = not attached
    return engine, calls


@pytest.mark.parametrize("hung_step", ["context.close", "browser.process_close", "driver.stop"])
def test_a_hung_step_ends_the_engines_own_browser_and_driver_within_the_deadline(
    tmp_path, hung_step
):
    driver = Driver(tmp_path)
    bystander = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
    try:
        browser = driver.launch_browser()
        engine, calls = engine_with(driver, hang=hung_step, deadline=1.0)
        started = time.monotonic()
        engine.stop()
        elapsed = time.monotonic() - started

        assert 0.9 <= elapsed < 8, f"stop() took {elapsed:.2f}s with a 1s deadline"
        assert wait_dead(driver.process.pid) and wait_dead(browser)
        assert bystander.poll() is None, "a process the engine did not start was killed"
        # The remaining steps still ran, against the dead driver, and stop() finished.
        assert calls == ["context", "browser", "driver.stop"]
        exceeded = [w for w in engine.wait_ledger() if w["op"] == "close.deadline_exceeded"]
        assert [w["detail"] for w in exceeded] == [hung_step]
        assert exceeded[0]["ok"] is False and exceeded[0]["ms"] >= 900
        assert engine._driver_tree is None and engine._pw is None
    finally:
        bystander.kill()
        bystander.wait(timeout=10)
        driver.cleanup()


def test_an_attached_browser_is_never_killed_even_when_the_close_hangs(tmp_path):
    """The driver is ours; the browser a CDP client attached to is its launcher's.

    The stand-in browser here is even a child of the driver, the worst case: with
    ``cdp_url`` the engine adopts the driver alone and the child must survive.
    """
    driver = Driver(tmp_path, tree=False)
    attached_browser = None
    try:
        attached_browser = driver.launch_browser()
        engine, calls = engine_with(driver, hang="driver.stop", attached=True, deadline=1.0)
        engine._owns_context = False  # an attached context belongs to the launcher
        engine._context = None
        engine.stop()

        assert wait_dead(driver.process.pid)
        assert is_alive(attached_browser), "the attached browser was killed"
        # No browser close for a browser this engine did not launch.
        assert calls == ["driver.stop"]
        assert [
            w["detail"] for w in engine.wait_ledger() if w["op"] == "close.deadline_exceeded"
        ] == ["driver.stop"]
    finally:
        driver.cleanup()
        if attached_browser is not None:
            ProcessTree(attached_browser, descendants=False).kill()


def test_an_engine_that_opens_an_attached_session_adopts_only_the_driver(monkeypatch):
    seen = []

    class Recorder:
        def __init__(self, pid, *, descendants=True):
            seen.append((pid, descendants))

        def close(self):
            pass

    class Boom(Exception):
        pass

    class FakePlaywright:
        class _Impl:
            class _Connection:
                class _Transport:
                    class _Proc:
                        pid = 4242

                    _proc = _Proc()

                _transport = _Transport()

            _connection = _Connection()

        _impl_obj = _Impl()

        class chromium:
            @staticmethod
            def connect_over_cdp(url):
                raise Boom

        class selectors:
            @staticmethod
            def set_test_id_attribute(name):
                pass

        def stop(self):
            pass

    class Starter:
        def start(self):
            return FakePlaywright()

    monkeypatch.setattr("testence.engine.playwright_cdp.ProcessTree", Recorder)
    monkeypatch.setattr("testence.engine.playwright_cdp.sync_playwright", lambda: Starter())
    attached = PlaywrightCdpEngine("http://127.0.0.1:9", cdp_url="http://127.0.0.1:9222")
    with pytest.raises(Boom):
        attached.start()
    launched = PlaywrightCdpEngine("http://127.0.0.1:9")
    with pytest.raises(AttributeError):
        launched.start()  # the fake has no launch(); we only look at what was adopted
    assert seen == [(4242, False), (4242, True)]


def test_a_healthy_close_leaves_the_tree_alone_and_records_nothing(tmp_path):
    driver = Driver(tmp_path)
    try:
        driver.launch_browser()
        engine, calls = engine_with(driver, hang=None, deadline=1.0)
        time.sleep(1.3)  # a late timer would have fired by now if it were not cancelled
        engine.stop()
        time.sleep(1.3)
        assert calls == ["context", "browser", "driver.stop"]
        assert driver.process.poll() is None, "a healthy close killed the driver"
        assert not [w for w in engine.wait_ledger() if w["op"] == "close.deadline_exceeded"]
    finally:
        driver.cleanup()


def test_a_sibling_that_finishes_in_time_does_not_touch_the_shared_driver(tmp_path):
    driver = Driver(tmp_path)
    try:
        browser = driver.launch_browser()
        parent, _ = engine_with(driver, hang=None, deadline=1.0)
        calls: list[str] = []
        sibling = PlaywrightCdpEngine("http://127.0.0.1:9")
        sibling.close_deadline_s = 1.0
        sibling._driver_tree = driver.tree
        sibling._shares_driver = True
        sibling._context = Step(None, calls, "context")
        sibling._owns_context = True
        sibling.stop()
        time.sleep(1.3)
        assert calls == ["context"]
        assert driver.process.poll() is None and is_alive(browser)
        assert parent._driver_tree is driver.tree, "a sibling must not release the parent's tree"
    finally:
        driver.cleanup()


def test_the_deadline_comes_from_the_environment_when_it_is_sane(monkeypatch):
    monkeypatch.delenv("TESTENCE_CLOSE_DEADLINE_S", raising=False)
    default = _close_deadline()
    for bad in ("", "soon", "0", "-3"):
        monkeypatch.setenv("TESTENCE_CLOSE_DEADLINE_S", bad)
        assert _close_deadline() == default
    monkeypatch.setenv("TESTENCE_CLOSE_DEADLINE_S", "2.5")
    assert _close_deadline() == 2.5


def test_an_unknown_driver_means_no_deadline_rather_than_a_guess():
    assert _driver_pid(object()) is None


def test_a_real_engine_records_its_driver_and_leaves_no_process_behind(tmp_path):
    engine = PlaywrightCdpEngine("http://127.0.0.1:9", headed=False)
    # Some hosts close a browser slowly; whether the deadline fires is not under test
    # here, only that the processes this engine recorded are gone afterwards.
    engine.close_deadline_s = 15.0
    engine.start()
    try:
        tree = engine._driver_tree
        assert tree is not None and tree.pid == _driver_pid(engine._pw)
        pid = tree.pid
        assert is_alive(pid)
        browser = descendants(pid) if os.name != "nt" else [0]
        assert browser, "the browser should sit below the driver"
    finally:
        engine.stop()
    assert wait_dead(pid)
    assert all(wait_dead(child) for child in browser if child)
