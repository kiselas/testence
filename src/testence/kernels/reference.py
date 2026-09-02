"""Reference (pure-Python) kernel backend — normative semantics.

Everything here is deliberately straightforward: this implementation defines what
"correct" means, so it optimizes for readability over speed. Native backends chase
the speed; the conformance suite keeps them honest.
"""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from typing import Any

from .contracts import KERNEL_ABI

name = "reference"
abi = KERNEL_ABI

#: ``- button "add" [level=2]`` → depth from indent, role, accessible name.
_ARIA_LINE = re.compile(r'^(?P<indent>\s*)-\s*(?P<role>[\w-]+)(?:\s+"(?P<name>[^"]*)")?')

# Weighted by how much *identity* an attribute carries versus how likely it is to
# be the thing that drifted. Renaming a button changes its text and aria-label —
# precisely the attributes a test addresses it by — while tag, role and id hold.
# Weighting the volatile attributes highest would make every rename look like a
# deletion, which is the worst error this scoring can make (corpus item
# ui_change_button_renamed exists to keep that honest).
_FP_WEIGHTS = {
    "testid": 0.30,
    "id": 0.20,
    "ariaLabel": 0.15,
    "role": 0.15,
    "tag": 0.10,
    "text": 0.10,
    "classes": 0.05,
}


def parse_ledger(data: bytes) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for raw in data.split(b"\n"):
        if not raw.strip():
            continue
        events.append(json.loads(raw))
    return events


def estimate_tokens(text: str) -> int:
    # ~4 bytes per token for mixed Latin/Cyrillic prose and JSON.
    return max(1, len(text.encode("utf-8")) // 4)


def percentiles(values: list[float], pcts: list[float]) -> list[float | None]:
    if not values:
        return [None] * len(pcts)
    ordered = sorted(values)
    out: list[float | None] = []
    for pct in pcts:
        k = (len(ordered) - 1) * pct / 100
        lower = int(k)
        upper = min(lower + 1, len(ordered) - 1)
        frac = k - lower
        out.append(round(ordered[lower] * (1 - frac) + ordered[upper] * frac, 2))
    return out


def _parse_aria(snapshot: str) -> list[tuple[int, str, str]]:
    nodes: list[tuple[int, str, str]] = []
    for line in snapshot.splitlines():
        match = _ARIA_LINE.match(line)
        if not match:
            continue
        depth = len(match.group("indent")) // 2
        nodes.append((depth, match.group("role"), match.group("name") or ""))
    return nodes


def diff_aria(before: str, after: str) -> dict[str, Any]:
    old, new = _parse_aria(before), _parse_aria(after)
    matcher = SequenceMatcher(a=old, b=new, autojunk=False)
    added: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    same = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            same += i2 - i1
            continue
        for depth, role, node_name in old[i1:i2]:
            removed.append({"depth": depth, "role": role, "name": node_name})
        for depth, role, node_name in new[j1:j2]:
            added.append({"depth": depth, "role": role, "name": node_name})
    # A node present on both sides but at a different position moved rather than
    # appeared: a triage agent should not read reordering as a disappearance.
    removed_keys = {(n["role"], n["name"]) for n in removed}
    added_keys = {(n["role"], n["name"]) for n in added}
    moved_keys = removed_keys & added_keys
    return {
        "added": [n for n in added if (n["role"], n["name"]) not in moved_keys],
        "removed": [n for n in removed if (n["role"], n["name"]) not in moved_keys],
        "moved": len(moved_keys),
        "same": same,
    }


def _text_similarity(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(a=a, b=b, autojunk=False).ratio()


def score_candidates(target: dict[str, Any], candidates: list[dict[str, Any]]) -> list[float]:
    scores: list[float] = []
    wanted_testid = target.get("testid")
    for candidate in candidates:
        # A test id is not one signal among many: a human put it there precisely to
        # say "this is the element the test means". If it survived, the element
        # survived — even if the component was rewritten around it (tag, role,
        # text and classes may all differ after a refactor).
        if wanted_testid and candidate.get("testid") == wanted_testid:
            scores.append(1.0)
            continue
        total = 0.0
        weight_sum = 0.0
        for field, weight in _FP_WEIGHTS.items():
            expected, actual = target.get(field), candidate.get(field)
            if expected in (None, "", []) and actual in (None, "", []):
                continue  # field absent on both sides carries no signal
            weight_sum += weight
            if field == "classes":
                left, right = set(expected or []), set(actual or [])
                union = left | right
                total += weight * (len(left & right) / len(union) if union else 0.0)
            elif field == "text":
                total += weight * _text_similarity(str(expected or ""), str(actual or ""))
            elif expected == actual:
                total += weight
        scores.append(round(total / weight_sum, 4) if weight_sum else 0.0)
    return scores
