"""Heal proposals: where did the element go, and is it a drift or a bug?

The industry consensus this follows (mabl, testRigor, Healenium all land here) is
that self-healing must be a *motion*, not runtime magic: the framework proposes a
reviewable edit to the test, a human or agent accepts it, and the accepted change
lives in git. Silently rebinding a locator at runtime hides product bugs.

The distinction that matters most is cheap to state and easy to get wrong:

- the element **moved or was renamed** → ``ui_change``, propose a new address;
- the element is **gone** → ``real_bug``, propose nothing.

A framework that heals its way around a deleted button reports green while the
feature is broken. Hence the score floor below: no candidate above it means gone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from testence import kernels
from testence.engine import Engine, Target

#: Below this similarity, the best candidate is not "the same element, moved" —
#: it is a different element, i.e. the original is gone. Pre-registered; the
#: corpus (H6 metrics) is what may move it, not intuition.
MIN_SCORE = 0.6

#: Two candidates this close are indistinguishable; propose the winner but say so,
#: because an ambiguous heal is exactly where a reviewer must look.
AMBIGUOUS_MARGIN = 0.05


@dataclass
class HealProposal:
    intent: str
    old_target: str
    verdict_hint: str
    score: float = 0.0
    new_target: dict[str, Any] | None = None
    runner_up: float | None = None
    ambiguous: bool = False
    rationale: str = ""
    suggested_edit: str = ""
    considered: list[dict[str, Any]] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "old_target": self.old_target,
            "verdict_hint": self.verdict_hint,
            "score": self.score,
            "new_target": self.new_target,
            "runner_up": self.runner_up,
            "ambiguous": self.ambiguous,
            "rationale": self.rationale,
            "suggested_edit": self.suggested_edit,
            "considered": self.considered[:5],
        }


def _target_expression(target: dict[str, Any]) -> str:
    kind, value, name = target.get("kind"), target.get("value"), target.get("name")
    if name:
        return f"Target({kind!r}, {value!r}, name={name!r})"
    return f"Target({kind!r}, {value!r})"


def _explain(known: dict[str, Any], candidate: dict[str, Any]) -> str:
    """Name what changed and what held, so a reviewer can judge in one read."""
    changed, kept = [], []
    for attribute in ("testid", "ariaLabel", "role", "text", "tag", "id"):
        before, after = known.get(attribute), candidate.get(attribute)
        if before in (None, "") and after in (None, ""):
            continue
        if before == after:
            kept.append(attribute)
        else:
            changed.append(f"{attribute}: {before!r} -> {after!r}")
    parts = []
    if changed:
        parts.append("changed " + "; ".join(changed))
    if kept:
        parts.append("unchanged " + ", ".join(kept))
    return "; ".join(parts) or "no comparable attributes"


def propose(
    engine: Engine,
    intent: str,
    failed_target: Target,
    known_fingerprint: dict[str, Any] | None,
) -> HealProposal | None:
    """Look for the element the step meant to touch.

    Returns ``None`` when no judgement is possible (no memory of a green run) —
    silence is correct there; a guess without a baseline is noise.
    """
    if not known_fingerprint:
        return None

    # A selector may encode a product-state assertion, not just an address.
    # Fingerprint similarity cannot prove checked/value/type/expanded state;
    # replacing such a selector with a plain role would erase the claim.
    if failed_target.kind == "css" and re.search(
        r":(?:checked|disabled|enabled|required|optional|valid|invalid|read-only|read-write)\b"
        r"|\[\s*(?:type|value|checked|disabled|selected|hidden|aria-checked|aria-selected|aria-expanded)\b",
        failed_target.value,
        re.IGNORECASE,
    ):
        return None

    candidates = engine.candidate_elements()
    if not candidates:
        return HealProposal(
            intent=intent,
            old_target=failed_target.describe(),
            verdict_hint="real_bug",
            rationale="page exposes no addressable elements — nothing to match against",
        )

    fingerprints = [c.get("fingerprint", {}) for c in candidates]
    scores = kernels.score_candidates(known_fingerprint, fingerprints)
    ranked = sorted(zip(scores, candidates), key=lambda pair: pair[0], reverse=True)
    best_score, best = ranked[0]
    runner_up = ranked[1][0] if len(ranked) > 1 else None
    considered = [{"score": score, "target": item.get("target")} for score, item in ranked[:5]]

    if best_score < MIN_SCORE:
        return HealProposal(
            intent=intent,
            old_target=failed_target.describe(),
            verdict_hint="real_bug",
            score=best_score,
            runner_up=runner_up,
            rationale=(
                f"no element resembles the one this step used to touch "
                f"(best match {best_score:.2f} < {MIN_SCORE}); it looks gone, "
                f"not moved — that is a product bug, not a locator drift"
            ),
            considered=considered,
        )

    new_target = best.get("target") or {}
    ambiguous = runner_up is not None and (best_score - runner_up) < AMBIGUOUS_MARGIN
    rationale = _explain(known_fingerprint, best.get("fingerprint", {}))
    if ambiguous:
        rationale += (
            f" (ambiguous: runner-up scores {runner_up:.2f} against {best_score:.2f} — "
            "review before accepting)"
        )
    return HealProposal(
        intent=intent,
        old_target=failed_target.describe(),
        verdict_hint="ui_change",
        score=best_score,
        new_target=new_target,
        runner_up=runner_up,
        ambiguous=ambiguous,
        rationale=rationale,
        suggested_edit=(
            f"# step: {intent}\n- {failed_target.describe()}\n+ {_target_expression(new_target)}"
        ),
        considered=considered,
    )
