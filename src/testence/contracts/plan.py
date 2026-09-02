"""PlanSpec: the semantic anchor between a requirement and executable proof."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._validation import (
    ContractError,
    identifier,
    known_fields,
    mapping,
    optional_text,
    string_list,
    text,
)

PLAN_SCHEMA = "testence/planspec/1"
ORACLE_KINDS = frozenset({"ui", "network", "api", "a11y", "visual", "custom"})

_PLAN_FENCE = re.compile(
    r"^```testence-planspec[ \t]*\r?\n(?P<body>.*?)^```[ \t]*$",
    re.MULTILINE | re.DOTALL,
)


@dataclass(frozen=True)
class Claim:
    id: str
    statement: str
    oracles: tuple[str, ...]
    required: bool = True


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    claims: tuple[str, ...]
    risk: str | None = None


@dataclass(frozen=True)
class PlanSpec:
    schema: str
    id: str
    title: str
    claims: tuple[Claim, ...]
    scenarios: tuple[Scenario, ...]
    source: str | None = None
    path: Path | None = None

    @property
    def claim_ids(self) -> tuple[str, ...]:
        return tuple(claim.id for claim in self.claims)

    def require_claims(self, claim_ids: tuple[str, ...] | list[str]) -> tuple[str, ...]:
        requested = tuple(claim_ids)
        if not requested:
            raise ContractError("a testence marker must bind at least one claim")
        if len(set(requested)) != len(requested):
            raise ContractError("a testence marker must not repeat claim IDs")
        unknown = sorted(set(requested) - set(self.claim_ids))
        if unknown:
            raise ContractError(f"plan {self.id!r} does not declare claim(s): {', '.join(unknown)}")
        return requested

    def summary(self) -> dict[str, Any]:
        return {
            "valid": True,
            "schema": self.schema,
            "id": self.id,
            "title": self.title,
            "claims": list(self.claim_ids),
            "scenarios": [scenario.id for scenario in self.scenarios],
            "path": str(self.path) if self.path else None,
        }

    @classmethod
    def from_dict(cls, value: Any, *, path: Path | None = None) -> PlanSpec:
        doc = mapping(value, "planspec")
        known_fields(doc, {"schema", "id", "title", "source", "claims", "scenarios"}, "planspec")
        schema = text(doc, "schema", "planspec", max_length=64)
        if schema != PLAN_SCHEMA:
            raise ContractError(f"unsupported PlanSpec schema: {schema!r}")
        plan_id = identifier(doc, "id", "planspec")
        title_value = text(doc, "title", "planspec", max_length=200)
        source = optional_text(doc, "source", "planspec", max_length=500)

        raw_claims = doc.get("claims")
        if not isinstance(raw_claims, list) or not raw_claims:
            raise ContractError("planspec.claims must be a non-empty array")
        claims = tuple(_claim(item, index) for index, item in enumerate(raw_claims))
        claim_ids = [claim.id for claim in claims]
        if len(set(claim_ids)) != len(claim_ids):
            raise ContractError("planspec.claims must have unique IDs")

        raw_scenarios = doc.get("scenarios")
        if not isinstance(raw_scenarios, list) or not raw_scenarios:
            raise ContractError("planspec.scenarios must be a non-empty array")
        scenarios = tuple(
            _scenario(item, index, frozenset(claim_ids)) for index, item in enumerate(raw_scenarios)
        )
        scenario_ids = [scenario.id for scenario in scenarios]
        if len(set(scenario_ids)) != len(scenario_ids):
            raise ContractError("planspec.scenarios must have unique IDs")

        covered = {claim for scenario in scenarios for claim in scenario.claims}
        missing_required = sorted(
            claim.id for claim in claims if claim.required and claim.id not in covered
        )
        if missing_required:
            raise ContractError(
                "required claim(s) are not covered by any scenario: " + ", ".join(missing_required)
            )
        return cls(schema, plan_id, title_value, claims, scenarios, source, path)


def _claim(value: Any, index: int) -> Claim:
    path = f"planspec.claims[{index}]"
    doc = mapping(value, path)
    known_fields(doc, {"id", "statement", "oracles", "required"}, path)
    claim_id = identifier(doc, "id", path)
    statement = text(doc, "statement", path, max_length=1000)
    oracles = string_list(doc.get("oracles"), f"{path}.oracles", non_empty=True)
    unknown = sorted(set(oracles) - ORACLE_KINDS)
    if unknown:
        raise ContractError(f"{path}.oracles has unsupported value(s): {', '.join(unknown)}")
    required = doc.get("required", True)
    if not isinstance(required, bool):
        raise ContractError(f"{path}.required must be a boolean")
    return Claim(claim_id, statement, oracles, required)


def _scenario(value: Any, index: int, plan_claims: frozenset[str]) -> Scenario:
    path = f"planspec.scenarios[{index}]"
    doc = mapping(value, path)
    known_fields(doc, {"id", "title", "claims", "risk"}, path)
    scenario_id = identifier(doc, "id", path)
    title_value = text(doc, "title", path, max_length=200)
    claims = string_list(doc.get("claims"), f"{path}.claims", non_empty=True, identifiers=True)
    unknown = sorted(set(claims) - plan_claims)
    if unknown:
        raise ContractError(f"{path} references unknown claim(s): {', '.join(unknown)}")
    risk = optional_text(doc, "risk", path, max_length=200)
    return Scenario(scenario_id, title_value, claims, risk)


def load_plan(path: Path | str) -> PlanSpec:
    source = Path(path)
    try:
        raw = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise ContractError(f"cannot read PlanSpec {source}: {exc}") from exc

    if source.suffix.lower() == ".json":
        body = raw
    else:
        matches = list(_PLAN_FENCE.finditer(raw))
        if len(matches) != 1:
            raise ContractError(
                f"{source} must contain exactly one ```testence-planspec JSON block"
            )
        body = matches[0].group("body")
    try:
        document = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ContractError(
            f"invalid PlanSpec JSON in {source}: line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    return PlanSpec.from_dict(document, path=source)
