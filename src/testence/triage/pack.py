"""Evidence-pack assembly: everything a triage agent needs, collected at failure time.

Design goal: most failures should be classifiable from the pack alone, without a
live browser. Composition is evaluated by corpus and ablation runs; budgets live in
``evidence.events.PACK_BUDGETS_TOKENS``. Sections are plain text files so any agent
can read them; ``pack.json`` is the machine index.

The verdict taxonomy is defined by ADR-0014.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from testence.engine import Engine, dump_net
from testence.evidence import EvidenceWriter, budgets_for, estimate_tokens

#: The answers a judge is allowed to give (ADR-0014).
#:
#: ``behaviour_change`` distinguishes coherent current behaviour from a broken
#: operation or locator drift. Intent still requires a specification, so the prompt
#: pairs the verdict with the explicit ``blocked_on`` abstention channel.
VERDICTS = ("real_bug", "behaviour_change", "ui_change", "flaky_timing", "environment")

_TRIAGE_PROMPT = """You are the judge for a failed browser test.
Read the sections of this evidence pack (aria.txt, network.jsonl, console.txt,
oracle.json if present) and return a verdict.

Verdict taxonomy (choose exactly one, with confidence 0..1):
- real_bug: the product misbehaves — the layers disagree with each other or with the
  product contract (a network response contradicts the page, an oracle diff, a 4xx/5xx
  on the action under test). Element GONE from the page is real_bug, not drift.
- behaviour_change: the product works coherently and does something different from
  what the test expects. The signature is agreement: the page, the network and the
  oracle all tell the same story, nothing errored, and the only disagreement is with
  the test's expectation. Report what the product does now, and say plainly that
  whether the change was intended cannot be read from this pack — the specification
  is not in it. Use this only with positive evidence that the layers agree; otherwise
  set `blocked_on` rather than inferring intent from the absence of an error.
- ui_change: the product works but the test's element addressing drifted
  (renamed label/role/text). Propose a minimal diff to the test as a motion.
  If heal.json is present it already contains a candidate edit and the framework's
  own moved-vs-gone reading; treat it as evidence to check, not as a conclusion.
- flaky_timing: evidence of async waits/races (action succeeded on the page but the
  assertion raced it). Propose a wait-condition fix, not a sleep.
- environment: the run met infrastructure it did not ask for — backend 5xx on
  unrelated calls, connection refused, browser died — OR the build under test is not
  the one the test was written against. Version skew belongs here.

Set `blocked_on` to the one thing that would settle the verdict if you cannot settle
it from the pack alone — most often the specification or ticket that says whether a
behaviour change was intended. A verdict with `blocked_on` set is provisional and
says so; that is a useful answer, and a confident wrong one is not.

If evidence is insufficient, say what is missing and attach to the live browser
named in browser.json before guessing.
"""


def _truncate(text: str, budget_tokens: int, full_path: Path) -> str:
    if estimate_tokens(text) <= budget_tokens:
        return text
    full_path.write_text(text, encoding="utf-8")
    clipped_chars = budget_tokens * 4
    return (
        text[:clipped_chars]
        + f"\n<truncated: full content in {full_path.name}, "
        + f"{estimate_tokens(text)} est. tokens total>"
    )


def assemble_pack(
    engine: Engine,
    writer: EvidenceWriter,
    test_id: str,
    error: str,
    oracle_diff: list[dict[str, Any]] | None = None,
    heal: Any = None,
) -> Path:
    pack_dir = writer.test_dir(test_id) / "pack"
    pack_dir.mkdir(parents=True, exist_ok=True)
    sections: dict[str, int] = {}

    def write_section(name: str, filename: str, content: str) -> None:
        text = _truncate(content, budgets_for(name), pack_dir / f"full-{filename}")
        (pack_dir / filename).write_text(text, encoding="utf-8", newline="\n")
        sections[name] = estimate_tokens(text)

    # Let in-flight requests land first: a snapshot taken mid-fetch describes a
    # page that never existed for the user, and that misleads triage.
    settled = engine.settle()
    try:
        write_section("aria", "aria.txt", engine.aria_snapshot())
    except Exception as exc:  # page may be gone — that fact is evidence too
        write_section("aria", "aria.txt", f"<aria snapshot unavailable: {exc}>")

    write_section("network", "network.jsonl", dump_net(engine.network_log()))
    write_section(
        "console",
        "console.txt",
        "\n".join(f"[{m['level']}] {m['text']}" for m in engine.console_log()) or "<empty>",
    )
    if oracle_diff:
        write_section("oracle", "oracle.json", json.dumps(oracle_diff, ensure_ascii=False, indent=1))

    try:
        engine.screenshot(str(pack_dir / "screenshot.png"))
    except Exception:
        pass  # screenshots are for humans; agents start from text

    if heal is not None:
        document = heal.to_json()
        (pack_dir / "heal.json").write_text(
            json.dumps(document, ensure_ascii=False, indent=1),
            encoding="utf-8",
            newline="\n",
        )
        sections["heal"] = estimate_tokens(json.dumps(document))

    manifest = engine.browser_manifest()
    (pack_dir / "browser.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    (pack_dir / "TRIAGE.md").write_text(_TRIAGE_PROMPT, encoding="utf-8", newline="\n")

    index = {
        "error": error,
        "page_url": manifest.get("page_url"),
        "page_settled": settled,
        "sections_est_tokens": sections,
        "verdicts": list(VERDICTS),
    }
    if heal is not None:
        # Surfaced in the index so a triage agent sees the framework's own reading
        # of "moved vs gone" before it opens any section.
        index["heal_hint"] = {"verdict_hint": heal.verdict_hint, "score": heal.score}
    (pack_dir / "pack.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    pack_event: dict[str, Any] = {
        "dir": str(pack_dir.relative_to(writer.run_dir)),
        "sections_est_tokens": sections,
        "error": error,
    }
    if heal is not None:
        # Carried in the ledger too, so the HTML report can show the proposal
        # without reading pack files (it renders from run.jsonl alone).
        pack_event["heal_hint"] = index["heal_hint"]
        pack_event["heal_rationale"] = heal.rationale
        pack_event["heal_edit"] = heal.suggested_edit
    writer.emit("pack", test=test_id, **pack_event)
    return pack_dir
