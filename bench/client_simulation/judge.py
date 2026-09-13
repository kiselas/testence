"""A narrow scripted judge for the fixed simulation contract, not an LLM/client trial.

Consumes only the failure pack. Never receives the harness phase/expected label.
The fixed PlanSpec makes an unapproved stable pixel change a violated visual claim.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack", type=Path)
    args = parser.parse_args()
    pack = args.pack.resolve()
    document = json.loads((pack / "verdict.template.json").read_text())
    comparisons = [(path, json.loads(path.read_text())) for path in pack.glob("visual-*.json")]
    failed = [(path, result) for path, result in comparisons if result.get("outcome") == "failed"]
    if document["plan_id"] != "workspace.visual" or len(failed) != 1:
        raise ValueError(
            "scripted judge only supports the fixed visual contract and one completed mismatch"
        )
    reference, result = failed[0]
    document.update(
        verdict="real_bug",
        confidence=1.0,
        summary="Stable viewport violates the fixed accepted visual contract; root cause is not inferred.",
        blocked_on=[],
    )
    for claim in document["claim_results"]:
        claim.update(
            status="failed",
            reason=f"{result['changed_pixels']} changed pixels exceed the accepted allowance {result['max_changed_pixels']}.",
            evidence=[reference.name, result["artifacts"]["diff"]["path"]],
        )
    verdict = pack / "verdict.json"
    verdict.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            "-I",
            "-m",
            "testence.cli",
            "verdict",
            "submit",
            str(verdict),
            "--pack",
            str(pack),
            "--plan",
            str(Path.cwd() / "plan.md"),
            "--out",
            str(pack / "submitted-verdict.json"),
            "--json",
        ],
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
