"""Negative controls and negative proof (ADR-0033).

A *control* is a project-declared way to break the target so that named claims become
false. ``testence run --control NAME`` activates one for a whole run; the run records it
in ``run.start``. A *negative proof* of a claim is a recorded run with a control that
targets the claim, in which the same test (same test and plan digests) failed an
assertion bound to that claim.

Testence never knows how to break a product: the project's test code or fixtures apply
the control when ``testence_control`` names it. This module only declares, activates and
evaluates.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from testence.contracts._validation import IDENTIFIER_RE

if TYPE_CHECKING:
    from testence.export._model import LoadedRun, Test

#: Per-claim outcomes, most informative first after ``proven``. ``proven`` wins over every
#: other piece of evidence for the same claim; among the rest the first listed is reported.
OUTCOMES = ("proven", "stayed_green", "wrong_reason", "inconclusive", "stale", "no_control")

#: ADR-0033 tripwire: a control whose failures are mostly on claims it does not target is
#: too blunt for ``proven`` to carry information. The warning triggers above this share.
BLUNT_SHARE = 0.5


class ControlError(ValueError):
    """A control declaration or activation that cannot be used."""


@dataclass(frozen=True)
class Control:
    """One declared negative control."""

    name: str
    description: str
    claims: tuple[str, ...]

    def targets(self, claim_id: str) -> bool:
        return claim_id in self.claims

    def to_json(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "claims": list(self.claims)}

    @classmethod
    def from_json(cls, document: Mapping[str, Any]) -> Control:
        """The control a run recorded in ``run.start``; validated like a declaration."""
        return _parse(str(document.get("name") or ""), document, where="run.start control")


def _parse(name: str, spec: Any, *, where: str) -> Control:
    if not IDENTIFIER_RE.fullmatch(name):
        raise ControlError(
            f"{where}: control name {name!r} must use lowercase letters, digits, dots, "
            "underscores or hyphens"
        )
    if not isinstance(spec, Mapping):
        raise ControlError(f"{where} {name!r} must be an object with description and claims")
    unknown = sorted(set(spec) - {"name", "description", "claims"})
    if unknown:
        raise ControlError(f"{where} {name!r}: unknown field(s): " + ", ".join(unknown))
    description = spec.get("description")
    if not isinstance(description, str) or not description.strip():
        raise ControlError(f"{where} {name!r}: description must say what the control breaks")
    claims = spec.get("claims")
    if not isinstance(claims, list) or not claims:
        raise ControlError(f"{where} {name!r}: claims must list the claims it makes false")
    bad = [
        claim
        for claim in claims
        if not isinstance(claim, str) or not IDENTIFIER_RE.fullmatch(claim)
    ]
    if bad:
        raise ControlError(f"{where} {name!r}: invalid claim id(s): {bad!r}")
    if len(set(claims)) != len(claims):
        raise ControlError(f"{where} {name!r}: claims must not repeat")
    return Control(name=name, description=description.strip(), claims=tuple(claims))


def declared_controls(extra: Mapping[str, Any]) -> dict[str, Control]:
    """The ``controls`` object of the settings file, validated."""
    raw = extra.get("controls")
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise ControlError("controls must be an object of name -> {description, claims}")
    return {str(name): _parse(str(name), spec, where="controls") for name, spec in raw.items()}


def resolve_control(extra: Mapping[str, Any], name: str | None) -> Control | None:
    """The control ``--control NAME`` asks for, or ``None`` when none is asked for."""
    if not name:
        return None
    controls = declared_controls(extra)
    if name not in controls:
        known = ", ".join(sorted(controls)) or "none declared in testence.json"
        raise ControlError(f"unknown control {name!r}; declared: {known}")
    return controls[name]


def run_control(run: LoadedRun) -> Control | None:
    """The control a run was executed with, or ``None`` for an ordinary run."""
    for event in run.events:
        if event.get("kind") == "run.start" and isinstance(event.get("control"), Mapping):
            return Control.from_json(event["control"])
    return None


@dataclass(frozen=True)
class ProofAttempt:
    """What proof accounting needs to know about one test's final attempt."""

    nodeid: str
    assurance: str
    test_digest: str
    plan_digest: str
    required_claims: frozenset[str]
    failed_claims: frozenset[str]
    repeated: bool


_IDENTITY = ("project_id", "case_id", "variant_id", "attempt_id")


def _event_key(event: Mapping[str, Any], aliases: dict[str, str]) -> str:
    """The attempt an event belongs to, keyed the way ``LoadedRun`` keys its tests."""
    parts = [str(event.get(field) or "") for field in _IDENTITY]
    if all(parts):
        return "|".join(parts)
    raw = str(event.get("test") or "")
    return str(event.get("nodeid") or aliases.get(raw) or raw)


def _test_key(test: Test) -> str:
    parts = [test.project_id, test.case_id, test.variant_id, test.attempt_id]
    return "|".join(parts) if all(parts) else test.nodeid


def proof_attempts(run: LoadedRun) -> dict[str, ProofAttempt]:
    starts: dict[str, dict[str, Any]] = {}
    failed: dict[str, set[str]] = {}
    aliases: dict[str, str] = {}
    for event in run.events:
        if not event.get("test"):
            continue
        if event.get("kind") == "test.start":
            key = _event_key(event, aliases)
            aliases[str(event["test"])] = key
            starts[key] = event
        elif event.get("kind") == "assertion" and event.get("outcome") == "failed":
            key = _event_key(event, aliases)
            failed.setdefault(key, set()).add(str(event.get("claim_id") or ""))
    attempts: dict[str, ProofAttempt] = {}
    for test in run.tests:
        key = _test_key(test)
        start = starts.get(key, {})
        required = frozenset(
            str(item.get("claim_id"))
            for item in start.get("assertions") or ()
            if isinstance(item, Mapping) and item.get("required", True) and item.get("claim_id")
        )
        attempts[test.nodeid] = ProofAttempt(
            nodeid=test.nodeid,
            assurance=test.assurance,
            test_digest=str(start.get("test_digest") or ""),
            plan_digest=str(start.get("plan_digest") or ""),
            required_claims=required,
            failed_claims=frozenset(failed.get(key, set()) - {""}),
            repeated=_repeated(test),
        )
    return attempts


def _repeated(test: Test) -> bool:
    return bool(test.reruns or test.flaky or test.rerun)


def _pair_outcome(
    claim: str, green: ProofAttempt, negative: ProofAttempt | None
) -> tuple[str, str]:
    """Outcome and a one-line reason for one test of ``G`` against one negative run."""
    if negative is None:
        return "inconclusive", "the test did not run with the control"
    if (negative.test_digest, negative.plan_digest) != (green.test_digest, green.plan_digest):
        return "stale", "the test or its plan changed between the green and the negative run"
    if negative.repeated:
        return "inconclusive", "the test was repeated in the negative run"
    if negative.assurance == "violated":
        if claim in negative.failed_claims:
            return "proven", "an assertion bound to the claim failed with the control active"
        failed = ", ".join(sorted(negative.failed_claims)) or "none"
        return "wrong_reason", f"the test failed on other claims: {failed}"
    if negative.assurance == "verified":
        return "stayed_green", "every assertion passed with the control active"
    return "inconclusive", f"assurance in the negative run was {negative.assurance}"


def collateral_report(run: LoadedRun, control: Control) -> dict[str, Any]:
    """How many of the claims that failed in a negative run the control does not target.

    The share is visible, never a gate: a blunt control still proves the claims it
    lists, and the warning tells a reviewer that ``proven`` says less than it seems to.
    """
    failed: set[str] = set()
    for attempt in proof_attempts(run).values():
        failed |= attempt.failed_claims
    collateral = sorted(failed - set(control.claims))
    report: dict[str, Any] = {"failed_claims": len(failed)}
    if collateral:
        report["collateral_claims"] = collateral
    if failed:
        share = round(len(collateral) / len(failed), 3)
        report["collateral_share"] = share
        report["blunt"] = share > BLUNT_SHARE
    return report


def blunt_warning(control_name: str, report: Mapping[str, Any]) -> str | None:
    """The sentence for a control whose failures are mostly collateral, else ``None``."""
    if not report.get("blunt"):
        return None
    return (
        f"control {control_name!r}: {len(report['collateral_claims'])} of "
        f"{report['failed_claims']} failed claims are not ones it targets "
        f"({report['collateral_share']:.0%}); it may be too blunt for proven (ADR-0033)"
    )


def evaluate_negative_proof(green: LoadedRun, negatives: Iterable[LoadedRun]) -> dict[str, Any]:
    """Per required claim of ``green``: its negative-proof outcome and the evidence."""
    green_attempts = proof_attempts(green)
    runs = [(run, run_control(run), proof_attempts(run)) for run in negatives]
    claims: dict[str, dict[str, Any]] = {}
    for attempt in green_attempts.values():
        for claim in sorted(attempt.required_claims):
            evidence = claims.setdefault(claim, {"evidence": []})["evidence"]
            for run, control, attempts in runs:
                if control is None or not control.targets(claim):
                    continue
                negative = attempts.get(attempt.nodeid)
                outcome, reason = _pair_outcome(claim, attempt, negative)
                collateral = (
                    sorted(negative.failed_claims - set(control.claims)) if negative else []
                )
                evidence.append(
                    {
                        "outcome": outcome,
                        "reason": reason,
                        "test": attempt.nodeid,
                        "run_id": run.run_id,
                        "control": control.name,
                        **({"collateral_claims": collateral} if collateral else {}),
                    }
                )
    for entry in claims.values():
        observed = {item["outcome"] for item in entry["evidence"]}
        entry["outcome"] = next(
            (outcome for outcome in OUTCOMES if outcome in observed), "no_control"
        )
    counts = {outcome: 0 for outcome in OUTCOMES}
    for entry in claims.values():
        counts[entry["outcome"]] += 1
    return {
        "runs": [
            {"run_id": run.run_id, "control": control.name if control else None}
            for run, control, _ in runs
        ],
        "controls": [
            {"run_id": run.run_id, "control": control.name, **collateral_report(run, control)}
            for run, control, _ in runs
            if control is not None
        ],
        "claims": dict(sorted(claims.items())),
        "counts": counts,
    }


__all__ = [
    "BLUNT_SHARE",
    "OUTCOMES",
    "Control",
    "ControlError",
    "ProofAttempt",
    "blunt_warning",
    "collateral_report",
    "declared_controls",
    "evaluate_negative_proof",
    "proof_attempts",
    "resolve_control",
    "run_control",
]
