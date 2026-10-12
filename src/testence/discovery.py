"""Bounded, redacted discovery shared by the CLI and persistent MCP session."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from testence.config import Settings
from testence.engine import Engine, Target, create_engine
from testence.evidence.sanitize import sanitize, sanitize_text


def python_target(target: dict[str, Any]) -> str:
    parts = [repr(target["kind"]), repr(target["value"])]
    for key in ("name", "nth", "exact"):
        if target.get(key) is not None:
            parts.append(f"{key}={target[key]!r}")
    if target.get("within") is not None:
        parts.append(f"within={python_target(target['within'])}")
    return f"Target({', '.join(parts)})"


def snapshot(
    engine: Engine, settings: Settings, *, limit: int = 60, rows: bool = False
) -> dict[str, Any]:
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError("limit must be an integer from 1 to 200")
    engine.settle(1_500)
    elements: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for candidate in engine.candidate_elements():
        target = candidate["target"]
        key = (target["kind"], target["value"], target.get("name") or "")
        if key in seen:
            continue
        seen.add(key)
        spec = {k: target[k] for k in ("kind", "value", "name") if target.get(k)}
        count = engine.count(Target(spec["kind"], spec["value"], name=spec.get("name")))
        elements.append({"target": spec, "matches": count, "unique": count == 1})
        if len(elements) == limit:
            break
    result: dict[str, Any] = {
        "url": engine.current_url(),
        "aria": engine.aria_snapshot(),
        "elements": elements,
    }
    if rows:
        result["rows"] = engine.eval_js(
            """() => Array.from(document.querySelectorAll('[data-key]'))
                .filter(el => el.getClientRects().length > 0).slice(0, 200)
                .map(el => ({key: (el.getAttribute('data-key') || '').slice(0, 300),
                            text: (el.innerText || '').slice(0, 300)}))"""
        )
    cleaned: dict[str, Any] = sanitize(
        result,
        secrets=settings.redaction_values(),
        policy=settings.redaction_policy(),
        limit=20_000,
    )
    for element in cleaned["elements"]:
        # Build snippets only from already redacted fields.
        element["python"] = python_target(element["target"])
    return cleaned


def explore(
    project: Path, url: str, *, profile: str = "", headed: bool = False, limit: int = 60
) -> dict[str, Any]:
    """One configured, read-only navigation and map. This is discovery, not test proof."""
    from testence.auth import from_settings

    settings = Settings.load(project, profile=profile) if profile else Settings.load(project)
    settings.headed = headed
    try:
        settings.redaction_policy()
    except ValueError as exc:
        raise ValueError("cannot explore: fix the project's redaction configuration") from exc
    # Validate before launching or navigating.
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError("limit must be an integer from 1 to 200")
    engine = create_engine(settings)
    try:
        engine.start()
        if str(settings.auth or "none").strip().lower() != "none":
            from_settings(settings).authenticate(engine)
        engine.goto(url)
        return snapshot(engine, settings, limit=limit, rows=True)
    except Exception as exc:
        raise ValueError(
            sanitize_text(
                str(exc),
                secrets=settings.redaction_values(),
                policy=settings.redaction_policy(),
                limit=2000,
            )
        ) from exc
    finally:
        engine.stop()
