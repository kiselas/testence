from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import unquote

from testence import __version__
from testence.contracts.verdict import Verdict

ROOT = Path(__file__).parents[1]


def test_readme_verdict_example_matches_the_public_contract() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    block = re.search(
        r"A verdict is a versioned document.*?```json\n(.*?)\n```",
        readme,
        re.DOTALL,
    )
    assert block is not None

    verdict = Verdict.from_dict(json.loads(block.group(1)))

    assert verdict.plan_id == "widgets.create"
    assert verdict.claim_ids == ("widgets.create.persisted",)


def test_testops_recipes_preserve_test_exit_and_name_the_current_limit() -> None:
    for relative in ("docs/en/reporting.md", "docs/ru/reporting.md"):
        guide = (ROOT / relative).read_text(encoding="utf-8")
        assert "|| true" not in guide
        assert 'TESTENCE_RUN_ID="r-${CI_PIPELINE_ID}-${CI_JOB_ID}"' in guide
        assert "TEST_EXIT=$?" in guide
        assert 'exit "$TEST_EXIT"' in guide
        assert "ALLURE_TESTPLAN_PATH" in guide


def _current_docs() -> list[Path]:
    files = [ROOT / name for name in ("README.md", "SECURITY.md", "SUPPORT.md", "CONTRIBUTING.md")]
    for language in ("en", "ru"):
        files.extend((ROOT / "docs" / language).rglob("*.md"))
    return files


def test_current_documentation_has_no_broken_local_links() -> None:
    broken: list[str] = []
    for document in _current_docs():
        text = document.read_text(encoding="utf-8")
        for target in re.findall(r"!?\[[^]]*\]\(([^)]+)\)", text):
            target = target.strip().strip("<>").split("#", 1)[0]
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            path = (document.parent / unquote(target)).resolve()
            if not path.exists():
                broken.append(f"{document.relative_to(ROOT)} -> {target}")
    assert not broken, "\n".join(broken)


def test_current_agent_and_demo_commands_match_the_cli() -> None:
    combined = "\n".join(path.read_text(encoding="utf-8") for path in _current_docs())
    assert "testence agent init" not in combined
    assert "testence agent status" not in combined
    assert "testence agent update" not in combined
    assert "testence agent install --project . --client codex" in combined
    assert "testence agent verify --project ." in combined
    assert "testence demo run --project testence-demo --json" in combined


def test_support_manifest_matches_package_and_ci_contract() -> None:
    support = json.loads((ROOT / "support.json").read_text(encoding="utf-8"))
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert support["schema"] == "testence/support/1"
    assert f'requires-python = "{support["python"]["requires"]}"' in pyproject
    assert 'python: ["3.10", "3.12"]' in workflow
    assert set(support["platforms"]["ci"]) == {"ubuntu-latest", "windows-latest"}


def test_release_version_is_consistent_across_package_and_public_manifests() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    project_version = re.search(r'^version = "([^"]+)"$', pyproject, re.MULTILINE)
    support = json.loads((ROOT / "support.json").read_text(encoding="utf-8"))
    skill_pack = json.loads(
        (ROOT / "src/testence/agent/skill-pack.json").read_text(encoding="utf-8")
    )

    assert project_version is not None
    assert project_version.group(1) == __version__ == support["version"] == "0.1.0a1"
    assert skill_pack["minimum_testence"] == __version__
    assert support["status"] == "alpha"
    assert '"Development Status :: 3 - Alpha"' in pyproject


def test_publish_workflow_does_not_interpolate_manual_inputs_in_shell() -> None:
    workflow = (ROOT / ".github/workflows/publish.yml").read_text(encoding="utf-8")
    run_blocks = "\n".join(
        block for block in re.findall(r"(?ms)^\s+run: \|\n(.*?)(?=^\s{6}\S|\Z)", workflow)
    )

    assert "${{ inputs." not in run_blocks
    assert "CANDIDATE_SHA: ${{ inputs.candidate_sha }}" in workflow
    assert "RELEASE_TAG: ${{ inputs.tag }}" in workflow
