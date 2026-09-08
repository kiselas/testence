"""PlanSpec: the semantic anchor between a requirement and executable proof."""

from __future__ import annotations

import hashlib
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

PLAN_SCHEMA = "testence/planspec/2"
LEGACY_PLAN_SCHEMA = "testence/planspec/1"
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
    capabilities: tuple[str, ...] = ()


@dataclass(frozen=True)
class AssertionSpec:
    id: str
    claim_id: str
    oracle: str
    required: bool = True
    expected: str | None = None


@dataclass(frozen=True)
class TraceLink:
    id: str
    url: str | None = None


@dataclass(frozen=True)
class PlanSpec:
    schema: str
    project_id: str
    id: str
    title: str
    claims: tuple[Claim, ...]
    scenarios: tuple[Scenario, ...]
    assertions: tuple[AssertionSpec, ...] = ()
    source: str | None = None
    path: Path | None = None
    digest: str = "unknown"
    source_schema: str | None = None
    extensions: dict[str, Any] | None = None
    owner: str | None = None
    requirements: tuple[TraceLink, ...] = ()
    issues: tuple[TraceLink, ...] = ()

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

    def resolve_case(self, case_id: str | None, claim_ids: tuple[str, ...]) -> str:
        """Resolve the stable logical case bound by a pytest marker."""

        if case_id:
            match = next((scenario for scenario in self.scenarios if scenario.id == case_id), None)
            if match is None:
                raise ContractError(f"plan {self.id!r} does not declare case {case_id!r}")
            if not set(claim_ids).issubset(match.claims):
                raise ContractError(f"case {case_id!r} does not cover every bound claim")
            return match.id
        matches = [
            scenario.id for scenario in self.scenarios if set(claim_ids).issubset(scenario.claims)
        ]
        if len(matches) != 1:
            raise ContractError(
                "case_id is required when bound claims do not select exactly one case"
            )
        return matches[0]

    def summary(self) -> dict[str, Any]:
        return {
            "valid": True,
            "schema": self.schema,
            "project_id": self.project_id,
            "id": self.id,
            "title": self.title,
            "claims": list(self.claim_ids),
            "scenarios": [scenario.id for scenario in self.scenarios],
            "assertions": [assertion.id for assertion in self.assertions],
            "digest": self.digest,
            "path": str(self.path) if self.path else None,
        }

    @classmethod
    def from_dict(
        cls, value: Any, *, path: Path | None = None, digest: str = "unknown"
    ) -> PlanSpec:
        doc = mapping(value, "planspec")
        allowed = {
            "schema",
            "project_id",
            "id",
            "title",
            "source",
            "claims",
            "scenarios",
            "assertions",
            "owner",
            "requirements",
            "issues",
        }
        schema = text(doc, "schema", "planspec", max_length=64)
        if schema not in (PLAN_SCHEMA, LEGACY_PLAN_SCHEMA):
            raise ContractError(f"unsupported PlanSpec schema: {schema!r}")
        project_id = (
            identifier(doc, "project_id", "planspec") if schema == PLAN_SCHEMA else "legacy"
        )
        plan_id = identifier(doc, "id", "planspec")
        title_value = text(doc, "title", "planspec", max_length=200)
        source = optional_text(doc, "source", "planspec", max_length=500)
        owner = optional_text(doc, "owner", "planspec", max_length=200)
        requirements = _trace_links(doc.get("requirements", []), "planspec.requirements")
        issues = _trace_links(doc.get("issues", []), "planspec.issues")

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
        raw_assertions = doc.get("assertions", [])
        if not isinstance(raw_assertions, list):
            raise ContractError("planspec.assertions must be an array")
        assertions = tuple(
            _assertion(item, index, frozenset(claim_ids))
            for index, item in enumerate(raw_assertions)
        )
        assertion_ids = [assertion.id for assertion in assertions]
        if len(set(assertion_ids)) != len(assertion_ids):
            raise ContractError("planspec.assertions must have unique IDs")
        if schema == PLAN_SCHEMA:
            claims_with_required_proof = {
                assertion.claim_id for assertion in assertions if assertion.required
            }
            missing_proof = sorted(
                claim.id
                for claim in claims
                if claim.required and claim.id not in claims_with_required_proof
            )
            if missing_proof:
                raise ContractError(
                    "required claim(s) have no required assertion: " + ", ".join(missing_proof)
                )
        return cls(
            schema=PLAN_SCHEMA,
            project_id=project_id,
            id=plan_id,
            title=title_value,
            claims=claims,
            scenarios=scenarios,
            assertions=assertions,
            source=source,
            path=path,
            digest=digest,
            source_schema=schema if schema != PLAN_SCHEMA else None,
            extensions={key: doc[key] for key in doc if key not in allowed} or None,
            owner=owner,
            requirements=requirements,
            issues=issues,
        )


def _trace_links(value: Any, path: str) -> tuple[TraceLink, ...]:
    if not isinstance(value, list):
        raise ContractError(f"{path} must be an array")
    result: list[TraceLink] = []
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        doc = mapping(item, item_path)
        known_fields(doc, {"id", "url"}, item_path)
        result.append(
            TraceLink(
                id=text(doc, "id", item_path, max_length=200),
                url=optional_text(doc, "url", item_path, max_length=1000),
            )
        )
    if len({item.id for item in result}) != len(result):
        raise ContractError(f"{path} must have unique IDs")
    return tuple(result)


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
    known_fields(doc, {"id", "title", "claims", "risk", "capabilities"}, path)
    scenario_id = identifier(doc, "id", path)
    title_value = text(doc, "title", path, max_length=200)
    claims = string_list(doc.get("claims"), f"{path}.claims", non_empty=True, identifiers=True)
    unknown = sorted(set(claims) - plan_claims)
    if unknown:
        raise ContractError(f"{path} references unknown claim(s): {', '.join(unknown)}")
    risk = optional_text(doc, "risk", path, max_length=200)
    capabilities = string_list(doc.get("capabilities", []), f"{path}.capabilities")
    from testence.engine.capabilities import WEB_CAPABILITIES

    unsupported = sorted(set(capabilities) - WEB_CAPABILITIES)
    if unsupported:
        raise ContractError(
            f"{path}.capabilities has unsupported value(s): {', '.join(unsupported)}"
        )
    return Scenario(scenario_id, title_value, claims, risk, capabilities)


def _assertion(value: Any, index: int, plan_claims: frozenset[str]) -> AssertionSpec:
    path = f"planspec.assertions[{index}]"
    doc = mapping(value, path)
    known_fields(doc, {"id", "claim_id", "oracle", "required", "expected"}, path)
    assertion_id = identifier(doc, "id", path)
    claim_id = identifier(doc, "claim_id", path)
    if claim_id not in plan_claims:
        raise ContractError(f"{path} references unknown claim {claim_id!r}")
    oracle = text(doc, "oracle", path, max_length=32)
    if oracle not in ORACLE_KINDS:
        raise ContractError(f"{path}.oracle has unsupported value: {oracle!r}")
    required = doc.get("required", True)
    if not isinstance(required, bool):
        raise ContractError(f"{path}.required must be a boolean")
    expected = optional_text(doc, "expected", path, max_length=1000)
    return AssertionSpec(assertion_id, claim_id, oracle, required, expected)


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
    digest = "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return PlanSpec.from_dict(document, path=source, digest=digest)
