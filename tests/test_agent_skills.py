"""Distribution and drift checks for the portable Testence skill pack."""

from __future__ import annotations

import re

from testence import SCHEMA_VERSION
from testence.agent import SKILL_PACK_SCHEMA, bundled_skills, load_skill_pack
from testence.contracts import PLAN_SCHEMA, VERDICT_KINDS, VERDICT_SCHEMA


def _read(root, relative: str) -> str:
    return root.joinpath(*relative.split("/")).read_text(encoding="utf-8")


def _frontmatter(text: str) -> str:
    assert text.startswith("---\n")
    _, header, body = text.split("---", 2)
    assert body.strip()
    return header


def test_skill_pack_declares_the_public_workflow_contracts():
    pack = load_skill_pack()

    assert pack["schema"] == SKILL_PACK_SCHEMA
    assert pack["version"] == "0.1.0"
    assert pack["contracts"] == {
        "plan": PLAN_SCHEMA,
        "evidence": SCHEMA_VERSION,
        "verdict": VERDICT_SCHEMA,
    }
    assert [entry["phase"] for entry in pack["skills"]] == [
        "plan",
        "author",
        "triage",
        "repair",
    ]
    assert pack["install"]["update_strategy"] == "replace-unmodified-preserve-modified"


def test_every_manifest_skill_is_complete_and_self_identifying():
    pack = load_skill_pack()
    assets = bundled_skills()

    assert list(assets) == [entry["name"] for entry in pack["skills"]]
    for name, root in assets.items():
        skill = _read(root, "SKILL.md")
        header = _frontmatter(skill)
        assert re.search(rf"^name: {re.escape(name)}$", header, re.MULTILINE)
        description = re.search(r"^description: (.+)$", header, re.MULTILINE)
        assert description and 40 <= len(description.group(1)) <= 500

        metadata = _read(root, "agents/openai.yaml")
        assert f'${name}' in metadata
        assert "allow_implicit_invocation: true" in metadata
        assert 'display_name: "Testence ' in metadata


def test_skill_references_track_runtime_contracts_and_taxonomy():
    assets = bundled_skills()
    plan_text = _read(assets["testence-plan"], "references/planspec-v1.md")
    author_text = _read(assets["testence-author"], "references/proof-gates.md")
    triage_text = _read(assets["testence-triage"], "references/verdict-v1.md")
    repair_text = _read(assets["testence-repair"], "references/repair-gates.md")

    assert PLAN_SCHEMA in plan_text and "testence plan validate" in plan_text
    assert PLAN_SCHEMA in author_text and "@pytest.mark.testence" in author_text
    assert VERDICT_SCHEMA in triage_text and "testence verdict validate" in triage_text
    assert all(kind in triage_text for kind in VERDICT_KINDS)
    assert "never weaken or remove a claim" in repair_text
    assert "real_bug" in repair_text and "Do not change the test" in repair_text
