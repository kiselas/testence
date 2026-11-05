"""Kit waits fail closed: an engine that cannot read the page never yields a pass."""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from testence.kits import _support


class _Engine:
    """``wait_for_predicate_js`` answers like the real one: False on timeout *and* on
    error. ``eval_js`` raises when the page cannot be read."""

    def __init__(self, *, waited: bool = False, value: object = False, broken: bool = False):
        self.waited, self.value, self.broken = waited, value, broken
        self.documents = ["doc-1", "doc-1"]

    def wait_for_predicate_js(self, _expression, _timeout_ms=None):
        return self.waited

    def eval_js(self, expression):
        if "timeOrigin" in expression:
            return self.documents.pop(0) if len(self.documents) > 1 else self.documents[0]
        if self.broken:
            raise RuntimeError("Execution context was destroyed")
        return self.value


class _Ex:
    def __init__(self, engine):
        self.engine = engine

    @contextmanager
    def step(self, _intent, _target=None, **_kwargs):
        yield


def test_a_wait_that_cannot_read_the_page_is_unavailable_not_failed_nor_passed():
    with pytest.raises(RuntimeError, match="destroyed"):
        _support.wait_until(_Ex(_Engine(broken=True)), "ready", "() => true")


def test_a_wait_settles_its_false_with_one_direct_read():
    _support.wait_until(_Ex(_Engine(value=True)), "ready", "() => true")
    with pytest.raises(AssertionError, match="never held"):
        _support.wait_until(_Ex(_Engine(value=False)), "ready", "() => true")


def test_a_negative_on_an_unreadable_page_does_not_pass():
    with pytest.raises(RuntimeError, match="destroyed"):
        _support.stays_false(_Ex(_Engine(broken=True)), "no toast", "() => x", within_ms=10)


def test_a_negative_across_a_navigation_proves_nothing():
    engine = _Engine()
    engine.documents = ["doc-1", "doc-2"]
    with pytest.raises(RuntimeError, match="navigated"):
        _support.stays_false(_Ex(engine), "no toast", "() => x", within_ms=10)


def test_a_negative_fails_when_the_condition_held_or_holds_now():
    with pytest.raises(AssertionError, match="held"):
        _support.stays_false(_Ex(_Engine(waited=True)), "no toast", "() => x", within_ms=10)
    with pytest.raises(AssertionError, match="held"):
        _support.stays_false(_Ex(_Engine(value=True)), "no toast", "() => x", within_ms=10)
    _support.stays_false(_Ex(_Engine()), "no toast", "() => x", within_ms=10)


@pytest.mark.parametrize("window", [0, -5, 1.5, None])
def test_a_negative_needs_a_positive_window(window):
    with pytest.raises(ValueError, match="within_ms"):
        _support.stays_false(_Ex(_Engine()), "no toast", "() => x", within_ms=window)
