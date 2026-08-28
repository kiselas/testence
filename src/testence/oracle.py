"""API-oracle helpers: the FE/BE-divergence detector.

The single most valuable practice from manual agent-driven runs: after every UI save,
re-read the entity through the API and diff it against what the UI claims. It catches
both silent misclicks (panel closed without saving, looking like success) and the bug
class UI tests exist for — client logic diverging from server logic.
"""

from __future__ import annotations

from typing import Any, Callable

from testence.evidence import EvidenceWriter


def diff_views(ui_view: dict[str, Any], api_view: dict[str, Any]) -> list[dict[str, Any]]:
    """Compare only keys the UI claims to display; extra API fields are not drift."""
    diffs: list[dict[str, Any]] = []
    for key, ui_value in ui_view.items():
        api_value = api_view.get(key, "<missing>")
        if _norm(ui_value) != _norm(api_value):
            diffs.append({"field": key, "ui": ui_value, "api": api_value})
    return diffs


def _norm(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


class OracleFailed(AssertionError):
    def __init__(self, name: str, diffs: list[dict[str, Any]]) -> None:
        fields = ", ".join(d["field"] for d in diffs)
        super().__init__(f"oracle {name!r}: UI and API disagree on: {fields}")
        self.diffs = diffs


def save_and_verify(
    actions: Any,
    save_target: Any,
    *,
    name: str,
    ui_view: Callable[[], dict[str, Any]],
    api_view: Callable[[], dict[str, Any]],
    expect_request: str | None = None,
    settle_ms: int = 3_000,
) -> list[dict[str, Any]]:
    """Click save, then prove the save actually happened and agrees with the UI.

    This is the practice that produced every finding of the manual agent-driven
    runs, turned into one call. It guards two different failures at once:

    - **The click that did nothing.** A panel can close without saving and look
      exactly like success. Re-reading the entity through the API is the only way
      to tell those apart.
    - **Front end and back end disagreeing.** Client-side logic is a copy of
      server-side logic, and copies drift silently. Comparing the two views after
      each save is what makes a UI test worth more than an API test.

    ``expect_request`` additionally asserts the request left the browser, which
    distinguishes "the server rejected it" from "the front end never asked".
    Returns the diff (empty when consistent); raises :class:`OracleFailed` on
    divergence, so a test does not have to remember to assert.
    """
    actions.click(save_target, intent=f"save {name}")
    if expect_request and not actions.engine.wait_for_request(expect_request):
        raise AssertionError(
            f"saving {name} sent no request matching {expect_request!r} — "
            "the UI accepted the click but nothing reached the server"
        )
    actions.settle(settle_ms)

    observed_ui = ui_view()
    observed_api = api_view()
    diffs = diff_views(observed_ui, observed_api)
    actions.writer.emit(
        "oracle", test=actions.test_id, name=name, ok=not diffs,
        diff=diffs or None, ui=observed_ui, api=observed_api,
    )
    if diffs:
        raise OracleFailed(name, diffs)
    return diffs


def verify(
    writer: EvidenceWriter,
    test_id: str,
    name: str,
    ui_view: dict[str, Any],
    api_view: dict[str, Any],
) -> None:
    """Emit an oracle event; raise OracleFailed on divergence."""
    diffs = diff_views(ui_view, api_view)
    writer.emit("oracle", test=test_id, name=name, ok=not diffs, diff=diffs or None)
    if diffs:
        raise OracleFailed(name, diffs)
