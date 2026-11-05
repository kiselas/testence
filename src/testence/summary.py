"""A Markdown summary of what a run proved, for a CI job summary or a pull request.

The headline is proof, not a pass count: required claims backed by verified assertions,
tests whose proof is not verified, and, when negative runs are supplied, claims with a
negative proof (ADR-0033). The number of passed tests comes last and is labelled as what
it is: a test can pass without checking anything.

ASCII only, so a Windows console on cp866 or cp1251 prints it unmangled.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from testence.controls import (
    blunt_warning,
    collateral_report,
    evaluate_negative_proof,
    proof_attempts,
    run_control,
)
from testence.export import LoadedRun
from testence.metrics import load_run

#: Longest list the summary prints before saying how many more there are.
LIST_LIMIT = 10


def _load(run_dir: Path | str) -> LoadedRun:
    root = Path(run_dir)
    return LoadedRun.from_events(load_run(root), root)


def _listed(items: list[str]) -> list[str]:
    shown = [f"- `{item}`" for item in items[:LIST_LIMIT]]
    if len(items) > LIST_LIMIT:
        shown.append(f"- and {len(items) - LIST_LIMIT} more")
    return shown


def render_summary(run_dir: Path | str, negative_runs: Iterable[Path | str] = ()) -> str:
    """Markdown for one run directory, optionally checked against negative runs."""
    return summarize(_load(run_dir), [_load(path) for path in negative_runs])


def summarize(run: LoadedRun, negatives: list[LoadedRun]) -> str:
    """Markdown for one loaded run, optionally checked against negative runs."""
    control = run_control(run)
    attempts = proof_attempts(run)

    tests_by_claim: dict[str, list[str]] = {}
    for attempt in attempts.values():
        for claim in attempt.required_claims:
            tests_by_claim.setdefault(claim, []).append(attempt.assurance)
    claims = sorted(tests_by_claim)
    verified_claims = [
        claim for claim in claims if all(state == "verified" for state in tests_by_claim[claim])
    ]
    not_verified = [
        f"{test.nodeid} ({test.assurance})" for test in run.tests if test.assurance != "verified"
    ]
    flaky = [test.nodeid for test in run.tests if test.flaky]

    lines = [f"### Testence: what run `{run.run_id}` proved", ""]
    if control is not None:
        lines += [
            f"**Negative run** with control `{control.name}`: {control.description}. "
            "A failure here shows that a test can fail for its claim; it is not a verdict "
            "on the product.",
            "",
        ]
        outcomes = evaluate_negative_proof(run, [run])["claims"]
        lines += ["| Targeted claim | Outcome |", "|---|---|"]
        for claim in control.claims:
            outcome = outcomes[claim]["outcome"] if claim in outcomes else "not_run"
            lines.append(f"| `{claim}` | {outcome} |")
        lines.append("")
        if warning := blunt_warning(control.name, collateral_report(run, control)):
            lines += [f"**Warning:** {warning}.", ""]
    else:
        lines += ["| | |", "|---|---|"]
        lines.append(
            f"| Required claims backed by verified assertions | "
            f"{len(verified_claims)} of {len(claims)} |"
        )
        proof = evaluate_negative_proof(run, negatives) if negatives else None
        if proof is not None:
            lines.append(
                f"| Claims with negative proof | {proof['counts']['proven']} of {len(claims)} |"
            )
        lines.append(f"| Tests whose proof is not verified | {len(not_verified)} |")
        lines.append(f"| Flaky tests (passed only after a rerun) | {len(flaky)} |")
        if run.integrity_errors:
            lines.append(f"| Integrity errors | {len(run.integrity_errors)} |")
        lines.append("")
        if not_verified:
            lines += ["**Not verified:**", *_listed(not_verified), ""]
        if proof is not None:
            missing = [
                f"{claim} ({entry['outcome']})"
                for claim, entry in proof["claims"].items()
                if entry["outcome"] != "proven"
            ]
            if missing:
                lines += ["**Without negative proof:**", *_listed(missing), ""]
            for item in proof["controls"]:
                if warning := blunt_warning(str(item["control"]), item):
                    lines += [f"**Warning:** {warning}.", ""]
        if flaky:
            lines += ["**Flaky:**", *_listed(flaky), ""]

    lines.append(
        f"<sub>Tests passed: {run.passed} of {len(run.tests)}. A pass count is not an "
        "argument: a test can pass without checking anything.</sub>"
    )
    return "\n".join(lines) + "\n"


__all__ = ["LIST_LIMIT", "render_summary", "summarize"]
