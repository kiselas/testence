"""Distribution and drift checks for the portable Testence skill pack."""

from __future__ import annotations

import json
import re
from pathlib import Path

from testence import SCHEMA_VERSION
from testence.agent import (
    AGENT_INSTALL_RECEIPT_SCHEMA,
    AGENT_INSTALL_SCHEMA,
    SKILL_PACK_SCHEMA,
    bundled_files,
    bundled_skills,
    install_skills,
    load_skill_pack,
    verify_skills,
)
from testence.cli import main
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
    assert pack["version"] == "0.1.1"
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
        assert f"${name}" in metadata
        assert "allow_implicit_invocation: true" in metadata
        assert 'display_name: "Testence ' in metadata


def test_skill_references_track_runtime_contracts_and_taxonomy():
    assets = bundled_skills()
    plan_text = _read(assets["testence-plan"], "references/planspec-v2.md")
    author_text = _read(assets["testence-author"], "references/proof-gates.md")
    triage_text = _read(assets["testence-triage"], "references/verdict-v2.md")
    repair_text = _read(assets["testence-repair"], "references/repair-gates.md")

    assert PLAN_SCHEMA in plan_text and "testence plan validate" in plan_text
    assert PLAN_SCHEMA in author_text and "@pytest.mark.testence" in author_text
    assert VERDICT_SCHEMA in triage_text and "testence verdict validate" in triage_text
    assert all(kind in triage_text for kind in VERDICT_KINDS)
    assert "never weaken or remove a claim" in repair_text
    assert "real_bug" in repair_text and "Do not change the test" in repair_text


def test_skill_pack_installs_and_verifies_both_real_client_layouts(tmp_path: Path):
    receipt = install_skills(tmp_path, ["codex", "claude"])

    assert receipt["schema"] == AGENT_INSTALL_RECEIPT_SCHEMA
    assert receipt["status"] == "installed"
    assert {item["client"] for item in receipt["clients"]} == {"codex", "claude"}
    assert (tmp_path / ".agents/skills/testence-triage/SKILL.md").is_file()
    assert (tmp_path / ".claude/skills/testence-triage/SKILL.md").is_file()
    state = json.loads((tmp_path / ".testence/agents.json").read_text(encoding="utf-8"))
    assert state["schema"] == AGENT_INSTALL_SCHEMA
    assert len(state["clients"]["codex"]["files"]) == len(bundled_files())
    assert verify_skills(tmp_path, ["codex", "claude"])["status"] == "valid"


def test_skill_update_preserves_modified_files_and_reports_repeatable_drift(tmp_path: Path):
    install_skills(tmp_path, ["codex"])
    edited = tmp_path / ".agents/skills/testence-plan/SKILL.md"
    edited.write_text("local customization\n", encoding="utf-8")

    first = install_skills(tmp_path, ["codex"])
    second = install_skills(tmp_path, ["codex"])

    assert first["status"] == second["status"] == "conflict"
    assert first["clients"][0]["conflicts"][0]["path"] == "testence-plan/SKILL.md"
    assert edited.read_text(encoding="utf-8") == "local customization\n"
    check = verify_skills(tmp_path, ["codex"])
    assert check["status"] == "drift"
    assert check["clients"][0]["drift"][0]["actual"].startswith("sha256:")


def test_agent_cli_emits_machine_receipts_and_conflict_exit(tmp_path: Path, capsys):
    assert (
        main(["agent", "install", "--project", str(tmp_path), "--client", "claude", "--json"]) == 0
    )
    installed = json.loads(capsys.readouterr().out)
    assert installed["status"] == "installed"

    assert main(["agent", "verify", "--project", str(tmp_path), "--json"]) == 0
    verified = json.loads(capsys.readouterr().out)
    assert verified["status"] == "valid"

    (tmp_path / ".claude/skills/testence-author/SKILL.md").write_text("drift", encoding="utf-8")
    assert main(["agent", "verify", "--project", str(tmp_path), "--json"]) == 3
    drift = json.loads(capsys.readouterr().out)
    assert drift["status"] == "drift"
