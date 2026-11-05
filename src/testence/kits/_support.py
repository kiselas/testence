"""What every kit shares: reading the page in one evaluation, waiting on a predicate.

Kits drive the page only through ``ex``: a ``Target`` for a DSL step, or a recorded
``ex.step`` around an engine-protocol call (``eval_js``, ``wait_for_predicate_js``).
No kit imports the browser library, sleeps, or retries an interaction.
"""

from __future__ import annotations

import json
from typing import Any

from testence.engine import Capability, Target, require_capabilities


def call(function: str, *args: Any) -> str:
    """A JavaScript expression that applies ``function`` to JSON-encoded ``args``.

    The engine evaluates an expression, not a function with arguments, so the
    arguments travel as literals. JSON is a subset of JavaScript literal syntax, and
    escaping ``<`` keeps a value from ever closing a script context.
    """
    encoded = ", ".join(json.dumps(arg, ensure_ascii=False).replace("<", "\\u003c") for arg in args)
    return f"({function})({encoded})"


def read(ex: Any, intent: str, function: str, *args: Any, target: Target | None = None) -> Any:
    """Evaluate ``function(*args)`` once, as one recorded step, and return its value."""
    with ex.step(intent, target):
        require_capabilities(ex.engine, "kit read", Capability.JAVASCRIPT)
        return ex.engine.eval_js(call(function, *args))


def wait_until(
    ex: Any,
    intent: str,
    predicate: str,
    *args: Any,
    describe: str | None = None,
    target: Target | None = None,
    timeout_ms: int | None = None,
) -> None:
    """Wait for ``predicate(*args)`` to hold, as one recorded check.

    The engine polls the predicate on animation frames; nothing sleeps. Its wait
    reports a timeout and a broken page alike (``False``), so a ``False`` is settled by
    one direct evaluation: a predicate that now holds passes, one that cannot be
    evaluated (a JavaScript error, a destroyed context) raises that error, which is
    unavailable evidence, not a failed check. Only a predicate that evaluates and is
    false fails the step, with what ``describe(*args)`` reads at that moment.
    """
    with ex.step(intent, target, check=True):
        require_capabilities(ex.engine, "kit wait", Capability.JAVASCRIPT)
        expression = call(predicate, *args)
        if ex.engine.wait_for_predicate_js(expression, timeout_ms):
            return
        if ex.engine.eval_js(expression):
            return
        seen = ex.engine.eval_js(call(describe, *args)) if describe else None
        detail = f"; the page showed {json.dumps(seen, ensure_ascii=False)}" if describe else ""
        raise AssertionError(f"{intent}: the condition never held{detail}")


_DOCUMENT = "() => String(performance.timeOrigin)"


def stays_false(
    ex: Any,
    intent: str,
    predicate: str,
    *args: Any,
    within_ms: int,
    describe: str | None = None,
    target: Target | None = None,
) -> None:
    """Check that ``predicate(*args)`` stays false for ``within_ms``, as one check.

    A negative must not pass because the page could not be read, so it fails closed:
    the engine's wait returning ``False`` (timeout or error alike) is followed by a
    check that the page is still the same document and one direct evaluation, which
    raises when the page cannot be read. Proving a negative costs ``within_ms`` by
    construction; it must be at least 1 (0 would fall back to the step budget).
    """
    if type(within_ms) is not int or within_ms < 1:
        raise ValueError("within_ms must be a positive integer number of milliseconds")
    with ex.step(intent, target, check=True):
        require_capabilities(ex.engine, "kit wait", Capability.JAVASCRIPT)
        expression = call(predicate, *args)
        document = ex.engine.eval_js(_DOCUMENT)
        held = ex.engine.wait_for_predicate_js(expression, within_ms)
        if ex.engine.eval_js(_DOCUMENT) != document:
            raise RuntimeError(f"{intent}: the page navigated during the check; it proves nothing")
        if held or ex.engine.eval_js(expression):
            seen = ex.engine.eval_js(call(describe, *args)) if describe else None
            detail = f": {json.dumps(seen, ensure_ascii=False)}" if describe else ""
            raise AssertionError(f"{intent}: the condition held{detail}")


def xpath_literal(text: str) -> str:
    """``text`` as an XPath 1.0 string literal, whatever quotes it contains."""
    if '"' not in text:
        return f'"{text}"'
    if "'" not in text:
        return f"'{text}'"
    parts = text.split('"')
    return "concat(" + ", '\"', ".join(f'"{part}"' for part in parts) + ")"


def css_string(text: str) -> str:
    """``text`` as a double-quoted CSS string."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


__all__ = ["call", "css_string", "read", "stays_false", "wait_until", "xpath_literal"]
