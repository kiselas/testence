"""Run the corpus and score what can be scored without an LLM.

    .venv/Scripts/python bench/corpus/run.py
    .venv/Scripts/python bench/corpus/run.py --only D-40-first-interaction-swallowed
    .venv/Scripts/python bench/corpus/run.py --repeats 3

One pytest process per item, each against its own store on one shared target. What
comes out is the mechanical half of the benchmark — outcome accuracy, false greens,
false reds, whether the run went red *for the right reason*, and whether drift
carried a proposal. Verdict accuracy needs a judge and is a separate pass over the
packs this run leaves behind.

Outcomes are read from the run ledger rather than from pytest's exit code, because
the score needs per-claim detail and the ledger already carries it (ADR-0003). That
also means the corpus is scored through the framework's own evidence, which is the
honest way round: if the ledger is wrong, the benchmark should be wrong too, loudly.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent
SUT = ROOT / "bench" / "sut"
RESULTS = HERE / "results"

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

from items import CLAIMS, ITEMS, Item  # noqa: E402

from testence.metrics import load_run  # noqa: E402
from testence.status import execution_passed, normalize_execution_status  # noqa: E402

CLAIM_OF_TEST = {test: claim for claim, test in CLAIMS.items()}


def _listening(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.3)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def start_target(port: int) -> subprocess.Popen | None:
    """Reuse a target that is already up; otherwise start one and own it."""
    if _listening(port):
        print(f"target already listening on {port}", flush=True)
        return None
    if not (SUT / "static" / "index.html").exists():
        raise SystemExit(
            "the target bundle is not built.\n"
            "  npm ci --prefix bench/sut/app && npm run build --prefix bench/sut/app"
        )
    process = subprocess.Popen(
        [sys.executable, str(SUT / "server.py"), "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    for _ in range(50):
        if _listening(port):
            print(f"target started on {port}", flush=True)
            return process
        time.sleep(0.1)
    process.kill()
    raise SystemExit("the target did not come up")


def run_item(item: Item, port: int, runs_root: Path, attempt: int, session: str) -> dict:
    run_id = f"{item.id}-{attempt}"
    run_dir = runs_root / run_id
    # Evidence from a previous invocation would be merged into this one's
    # outcomes, so the directory is cleared rather than appended to.
    shutil.rmtree(run_dir, ignore_errors=True)
    # The target keeps one store per key, and a key that repeats across
    # invocations accumulates the rows earlier runs created: the collection grew
    # 45 -> 46 -> 47 and a claim about how many rows carry one status stopped
    # holding. The store key therefore carries a per-invocation nonce, while the
    # evidence directory keeps its readable name.
    store_key = f"{run_id}-{session}"
    env = {
        **os.environ,
        "TESTENCE_BASE_URL": f"http://127.0.0.1:{port}",
        "TESTENCE_AUTH": "none",
        "TESTENCE_HEADED": "false",
        "TESTENCE_RUNS_ROOT": str(runs_root),
        "TESTENCE_RUN_ID": run_id,
        "TESTENCE_SUT_DEFECTS": ",".join(item.defects),
        "TESTENCE_SUT_RUN": store_key,
        "PYTHONPATH": str(ROOT / "src"),
    }
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(HERE / "spec_collection.py"),
            "--testence-headless",
            "-q",
            "-p",
            "no:cacheprovider",
            "--rootdir",
            str(HERE),
            "-c",
            str(HERE / "pytest.ini"),
        ],
        cwd=str(HERE),
        env=env,
        capture_output=True,
        text=True,
        timeout=900,
    )
    outcomes: dict[str, str] = {}
    run_ends: list[dict] = []
    if run_dir.exists():
        for event in load_run(run_dir):
            if event["kind"] == "test.end":
                nodeid = str(event.get("nodeid") or event["test"])
                test_name = nodeid.rsplit("::", 1)[-1].split("[", 1)[0]
                outcomes[test_name] = normalize_execution_status(event.get("status"))
            elif event["kind"] == "run.end":
                run_ends.append(event)
    failed = sorted(
        CLAIM_OF_TEST.get(test, test)
        for test, status in outcomes.items()
        if not execution_passed(status)
    )
    heals = (
        sorted(path.parent.parent.name for path in run_dir.glob("*/pack/heal.json"))
        if run_dir.exists()
        else []
    )
    expected_tests = set(CLAIM_OF_TEST)
    observed_tests = set(outcomes)
    incomplete_reasons: list[str] = []
    if process.returncode not in (0, 1):
        incomplete_reasons.append(f"pytest exit code {process.returncode}")
    if observed_tests != expected_tests:
        missing = sorted(expected_tests - observed_tests)
        extra = sorted(observed_tests - expected_tests)
        if missing:
            incomplete_reasons.append("missing tests: " + ", ".join(missing))
        if extra:
            incomplete_reasons.append("unexpected tests: " + ", ".join(extra))
    if len(run_ends) != 1:
        incomplete_reasons.append(f"expected one logical run.end, got {len(run_ends)}")
    elif run_ends[0].get("run_status") in {
        "incomplete",
        "interrupted",
        "internal_error",
        "usage_error",
        "unknown",
    }:
        incomplete_reasons.append(f"run status {run_ends[0].get('run_status')}")
    return {
        "run": run_id,
        "exit_code": process.returncode,
        "claims_seen": len(outcomes),
        "complete": not incomplete_reasons,
        "incomplete_reasons": incomplete_reasons,
        "failed_claims": failed,
        "heal_proposals": heals,
        "stdout_tail": process.stdout[-400:] if process.returncode not in (0, 1) else "",
    }


def evaluate(item: Item, result: dict) -> dict:
    went_red = bool(result["failed_claims"])
    complete = bool(result.get("complete", False))
    expected = set(item.expect_claims)
    failed = set(result["failed_claims"])
    checks: dict[str, object] = {
        "outcome_ok": complete and went_red == item.expect_failure,
        "observed": "incomplete" if not complete else ("red" if went_red else "green"),
        "expected": "red" if item.expect_failure else "green",
        "failed_claims": sorted(failed),
        "complete": complete,
    }
    if item.expect_failure:
        # Red is not enough: the run has to break the claim the defect actually
        # falsifies. A failure elsewhere is an accident that coincided with one.
        checks["right_reason"] = expected.issubset(failed)
        checks["missing_claims"] = sorted(expected - failed)
        checks["collateral_claims"] = sorted(failed - expected)
    if item.expect_heal:
        checks["heal_proposed"] = bool(result["heal_proposals"])
    if not complete:
        checks["incomplete_reasons"] = list(result.get("incomplete_reasons") or ())
    return checks


def summarize(records: list[dict]) -> dict:
    def ratio(part: list, whole: list) -> float | None:
        return round(len(part) / len(whole), 3) if whole else None

    seeded = [r for r in records if r["expected"] == "red"]
    controls = [r for r in records if r["expected"] == "green"]
    false_green = [r for r in seeded if r["observed"] == "green"]
    false_red = [r for r in controls if r["observed"] == "red"]
    caught = [r for r in seeded if r["observed"] == "red"]
    right = [r for r in caught if r.get("right_reason")]
    heal_expected = [r for r in records if "heal_proposed" in r]
    heal_got = [r for r in heal_expected if r["heal_proposed"]]

    by_stratum: dict[str, dict[str, int]] = {}
    for record in seeded:
        bucket = by_stratum.setdefault(record["stratum"] or "-", {"caught": 0, "total": 0})
        bucket["total"] += 1
        bucket["caught"] += 1 if record["observed"] == "red" else 0

    return {
        "items": len(records),
        "outcome_accuracy": ratio([r for r in records if r["outcome_ok"]], records),
        "false_green_rate": ratio(false_green, seeded),
        "false_red_rate": ratio(false_red, controls),
        "right_reason_rate": ratio(right, caught),
        "heal_recall": ratio(heal_got, heal_expected),
        "detection_by_stratum": by_stratum,
        "collateral": {
            r["item"]: r["collateral_claims"] for r in caught if r.get("collateral_claims")
        },
        "misses": [r["item"] for r in records if not r["outcome_ok"]],
        "wrong_reason": [r["item"] for r in caught if not r.get("right_reason")],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", action="append", default=None)
    parser.add_argument("--port", type=int, default=8800)
    parser.add_argument(
        "--repeats",
        type=int,
        default=1,
        help="runs per item; timing items are not decided by one sample",
    )
    args = parser.parse_args()

    items = [i for i in ITEMS if not args.only or i.id in args.only]
    runs_root = ROOT / "runs" / "corpus"
    runs_root.mkdir(parents=True, exist_ok=True)

    session = time.strftime("%H%M%S")
    target = start_target(args.port)
    records: list[dict] = []
    try:
        for index, item in enumerate(items, start=1):
            for attempt in range(1, args.repeats + 1):
                label = f"{item.id}" + (f" #{attempt}" if args.repeats > 1 else "")
                print(f"[{index}/{len(items)}] {label}", flush=True)
                result = run_item(item, args.port, runs_root, attempt, session)
                checks = evaluate(item, result)
                records.append(
                    {
                        "item": item.id,
                        "attempt": attempt,
                        "verdict_truth": item.verdict,
                        "stratum": item.stratum,
                        "note": item.note,
                        **checks,
                        "run_dir": result["run"],
                    }
                )
                mark = "ok  " if checks["outcome_ok"] else "MISS"
                detail = f"{checks['observed']} (expected {checks['expected']})"
                if checks.get("failed_claims"):
                    detail += f"  failed: {', '.join(checks['failed_claims'])}"
                print(f"      {mark} {detail}", flush=True)
                if result["stdout_tail"]:
                    print(f"      ! {result['stdout_tail'].strip()[:300]}", flush=True)
    finally:
        if target is not None:
            target.terminate()

    summary = summarize(records)
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "collection.json").write_text(
        json.dumps({"summary": summary, "records": records}, indent=1, ensure_ascii=False),
        encoding="utf-8",
        newline="\n",
    )
    print("\n" + json.dumps(summary, indent=1, ensure_ascii=False))

    flakes = Counter((r["item"], r["observed"]) for r in records)
    unstable = sorted(
        {
            item
            for (item, _), _ in flakes.items()
            if len({obs for (i, obs), _ in flakes.items() if i == item}) > 1
        }
    )
    if unstable:
        print(f"\nunstable across repeats: {unstable}")


if __name__ == "__main__":
    main()
