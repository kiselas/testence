"""Run the failure corpus and score what can be scored without an LLM.

    python corpus/run.py            # all items
    python corpus/run.py --only ui_change_button_renamed

For each item: materialize the mutated page, establish a baseline green run (so the
heal proposer has a memory of "working"), run the suite against the mutation,
then check the mechanical expectations.

The baseline matters and is easy to get wrong: a heal proposal without a green
baseline is a guess, so the corpus measures the framework as it actually operates —
second run onwards — not a cold start.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from items import ITEMS, CorpusItem  # noqa: E402

TARGET_PAGE = ROOT / "bench" / "target" / "index.html"
RESULTS = Path(__file__).parent / "results"


def _run_suite(page: Path, runs_root: Path, store_root: Path) -> dict:
    """One pytest invocation against one page; returns parsed evidence."""
    # Inherit the real environment: browser discovery needs platform variables
    # (PROGRAMFILES, LOCALAPPDATA, ...), and a hand-picked subset silently breaks
    # Chrome launching with a confusing "distribution not found" error.
    env = {
        **os.environ,
        "TESTENCE_CORPUS_PAGE": page.resolve().as_uri(),
        "TESTENCE_RUNS_ROOT": str(runs_root),
        "TESTENCE_HEADED": "false",
        "TESTENCE_BASE_URL": "",
        "TESTENCE_AUTH": "none",
        "PYTHONPATH": str(ROOT / "src"),
    }
    before = {p.name for p in runs_root.glob("r-*")} if runs_root.exists() else set()
    # The plugin loads via its pytest11 entry point; passing -p as well would be a
    # double registration and pytest refuses that outright.
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(Path(__file__).parent / "spec.py"),
         "--testence-headless", "-q", "--rootdir", str(store_root),
         "-p", "no:cacheprovider"],
        cwd=store_root, env=env, capture_output=True, text=True, timeout=600,
    )
    new_runs = sorted(p for p in runs_root.glob("r-*")
                      if p.name not in before and p.is_dir())
    run_dir = new_runs[-1] if new_runs else None
    return {"exit_code": proc.returncode, "run_dir": run_dir,
            "stdout_tail": proc.stdout[-600:]}


def _read_packs(run_dir: Path | None) -> list[dict]:
    if run_dir is None:
        return []
    packs = []
    for pack_json in sorted(run_dir.glob("*/pack/pack.json")):
        document = json.loads(pack_json.read_text(encoding="utf-8"))
        heal_path = pack_json.parent / "heal.json"
        if heal_path.exists():
            document["heal"] = json.loads(heal_path.read_text(encoding="utf-8"))
        document["_test"] = pack_json.parent.parent.name
        packs.append(document)
    return packs


def _evaluate(item: CorpusItem, result: dict, packs: list[dict]) -> dict:
    failed = result["exit_code"] != 0
    checks: dict[str, object] = {
        "failed_as_expected": failed == item.expect_failure,
        "observed": "fail" if failed else "pass",
        "expected": "fail" if item.expect_failure else "pass",
    }

    heals = [p["heal"] for p in packs if "heal" in p]
    if item.expect_heal:
        def acceptable(proposed: dict | None) -> bool:
            if not proposed:
                return False
            return any(
                all(proposed.get(key) == value for key, value in accepted.items())
                for accepted in item.expect_heal or []
            )

        matched = [h for h in heals if acceptable(h.get("new_target"))]
        checks["heal_proposed"] = bool(heals)
        checks["heal_correct"] = bool(matched)
        checks["heal_hint"] = [h.get("verdict_hint") for h in heals]
        checks["heal_targets"] = [h.get("new_target") for h in heals]
        checks["heal_scores"] = [h.get("score") for h in heals]
    if item.expect_no_heal:
        proposed = [h for h in heals if h.get("new_target")]
        checks["refused_to_heal"] = not proposed
        checks["heal_hint"] = [h.get("verdict_hint") for h in heals]
        checks["heal_scores"] = [h.get("score") for h in heals]

    checks["packs"] = len(packs)
    checks["pack_tokens"] = [sum(p.get("sections_est_tokens", {}).values()) for p in packs]
    return checks


def run_item(item: CorpusItem, keep: bool = False) -> dict:
    workspace = Path(tempfile.mkdtemp(prefix=f"testence-corpus-{item.name}-"))
    try:
        page = workspace / "page.html"
        original = TARGET_PAGE.read_text(encoding="utf-8")
        runs_root = workspace / "runs"

        # 1. baseline on the pristine page: gives the proposer a memory of "working"
        page.write_text(original, encoding="utf-8", newline="\n")
        baseline = _run_suite(page, runs_root, workspace)

        # 2. the mutation
        page.write_text(item.mutate(original), encoding="utf-8", newline="\n")
        result = _run_suite(page, runs_root, workspace)
        packs = _read_packs(result["run_dir"])

        evaluation = _evaluate(item, result, packs)
        evaluation["baseline_green"] = baseline["exit_code"] == 0
        if not evaluation["baseline_green"]:
            evaluation["warning"] = "baseline run was not green; item result is unreliable"
        return {"item": item.name, "verdict_truth": item.verdict, "note": item.note,
                "checks": evaluation}
    finally:
        if not keep:
            shutil.rmtree(workspace, ignore_errors=True)


def summarize(records: list[dict]) -> dict:
    outcome_ok = [r for r in records if r["checks"]["failed_as_expected"]]
    seeded = [r for r in records if r["checks"]["expected"] == "fail"]
    false_green = [r for r in seeded if r["checks"]["observed"] == "pass"]
    controls = [r for r in records if r["checks"]["expected"] == "pass"]
    false_red = [r for r in controls if r["checks"]["observed"] == "fail"]

    heal_expected = [r for r in records if "heal_correct" in r["checks"]]
    heal_correct = [r for r in heal_expected if r["checks"]["heal_correct"]]
    heal_proposed = [r for r in heal_expected if r["checks"]["heal_proposed"]]
    refusals = [r for r in records if "refused_to_heal" in r["checks"]]
    refused = [r for r in refusals if r["checks"]["refused_to_heal"]]

    def ratio(part: list, whole: list) -> float | None:
        return round(len(part) / len(whole), 3) if whole else None

    return {
        "items": len(records),
        "outcome_accuracy": ratio(outcome_ok, records),
        "false_green_rate": ratio(false_green, seeded),
        "false_red_rate": ratio(false_red, controls),
        "heal_recall": ratio(heal_proposed, heal_expected),
        "heal_precision": ratio(heal_correct, heal_proposed),
        "disappearance_discrimination": ratio(refused, refusals),
        "failures": [r["item"] for r in records if not r["checks"]["failed_as_expected"]],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", action="append", default=None)
    parser.add_argument("--keep", action="store_true", help="keep workspaces for inspection")
    args = parser.parse_args()

    items = [i for i in ITEMS if not args.only or i.name in args.only]
    records = []
    for index, item in enumerate(items, start=1):
        print(f"[{index}/{len(items)}] {item.name} (truth: {item.verdict})", flush=True)
        record = run_item(item, keep=args.keep)
        records.append(record)
        checks = record["checks"]
        mark = "ok " if checks["failed_as_expected"] else "MISS"
        print(f"      {mark} observed={checks['observed']} expected={checks['expected']}"
              + (f" heal_correct={checks.get('heal_correct')}" if "heal_correct" in checks else "")
              + (f" refused_heal={checks.get('refused_to_heal')}" if "refused_to_heal" in checks else ""),
              flush=True)

    summary = summarize(records)
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "corpus.json").write_text(
        json.dumps({"summary": summary, "records": records}, indent=1, ensure_ascii=False),
        encoding="utf-8", newline="\n")
    print("\n" + json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
