"""A small real-React workflow used by ``bench/react_latency.py``.

This is deliberately separate from the correctness corpus. It uses the same SUT
and the same public ``Actions`` path, but repeats controlled-input work so latency
has enough samples to describe a distribution. There are no injected defects and
no sleeps: the mutation synchronizes on its exact POST response and React's visible
counter commit.
"""

from __future__ import annotations

from testence.engine import Target

TOTAL = Target("css", "[data-testid='total']")
SKELETONS = Target("css", "tbody tr.skeleton")
NEW_ROW = Target("placeholder", "new row name")
CREATE = Target("role", "button", name="Create")

INPUT_PAIRS = 8


def test_real_react_input_and_mutation_latency(ex, sut):
    ex.goto(sut.url(), intent="open the real React collection")
    ex.engine.wait_while_visible(SKELETONS, timeout_ms=2_000)

    # Alternate the paths so a warming browser or a busy host cannot favour one
    # whole group merely because it ran second.
    for index in range(INPUT_PAIRS):
        ex.fill(
            NEW_ROW,
            f"safe-{index}",
            intent=f"controlled fill safe {index:02d}",
        )
        ex.fill(
            NEW_ROW,
            f"fast-{index}",
            intent=f"controlled fill fast {index:02d}",
            fast=True,
        )

    before = int(ex.engine.read_text(TOTAL))
    with ex.step("mutation round trip"):
        ex.fill(NEW_ROW, "latency-probe", intent="prepare mutation", fast=True)
        mark = ex.engine.net_mark()
        ex.click(CREATE, intent="submit mutation", fast=True)
        response = ex.engine.wait_for_response(
            "/api/rows", method="POST", since=mark, timeout_ms=2_000
        )
        assert response is not None, "the create request produced no response"
        assert response.status == 201, f"create returned HTTP {response.status}"
        ex.expect_text(
            TOTAL,
            str(before + 1),
            intent="React committed the created row",
        )

    # Keep every engine sample, not only the five slowest entries from the normal
    # test.waits summary. The benchmark driver consumes this note after pytest exits.
    ex.note(
        "real React latency samples",
        benchmark="react_latency",
        samples=ex.engine.wait_ledger(),
    )
