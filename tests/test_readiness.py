from __future__ import annotations

import json
import subprocess
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from testence.cli import main
from testence.contracts import READINESS_REPORT_SCHEMA, validate_document
from testence.readiness import ReadinessError, prepare_plan


def _write_plan(path: Path, *, oracle: str = "api") -> Path:
    document = {
        "schema": "testence/planspec/2",
        "project_id": "shop",
        "id": "shop.checkout",
        "title": "Checkout",
        "claims": [
            {
                "id": "shop.checkout.saved",
                "statement": "The order is saved.",
                "oracles": ["ui", oracle],
            }
        ],
        "assertions": [
            {
                "id": "assert.checkout.saved",
                "claim_id": "shop.checkout.saved",
                "oracle": oracle,
            }
        ],
        "scenarios": [
            {
                "id": "checkout",
                "title": "Submit an order",
                "claims": ["shop.checkout.saved"],
                "capabilities": ["browser.dom"],
            }
        ],
    }
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _write_settings(path: Path, readiness: dict) -> None:
    path.write_text(
        json.dumps(
            {
                "project_id": "shop",
                "base_url": "https://qa.example.test",
                "headed": False,
                "readiness": readiness,
            }
        ),
        encoding="utf-8",
    )


def test_prepare_reports_ready_without_starting_a_browser(tmp_path, monkeypatch):
    plan = _write_plan(tmp_path / "plan.json")
    fixture = tmp_path / "seed.ready"
    fixture.write_text("ready", encoding="utf-8")
    monkeypatch.setenv("SHOP_TEST_USER", "synthetic-user")
    _write_settings(
        tmp_path / "testence.json",
        {
            "schema": "testence/readiness/1",
            "oracle_adapters": ["api"],
            "checks": [
                {"id": "credentials", "type": "env", "variables": ["SHOP_TEST_USER"]},
                {"id": "seed", "type": "file", "path": "seed.ready"},
            ],
            "scenarios": {"checkout": ["credentials", "seed"]},
        },
    )

    result = prepare_plan(plan, tmp_path)

    assert result["schema"] == READINESS_REPORT_SCHEMA
    validate_document(result, "readiness-report.schema.json")
    assert result["status"] == "ready", json.dumps(result, indent=2)
    assert result["summary"] == {"ready": 1, "blocked": 0, "total": 1}
    assert result["scenarios"][0]["blockers"] == []
    assert result["timings"]["total_ms"] >= 0


def test_prepare_names_missing_prerequisites_without_exposing_values(tmp_path, monkeypatch):
    plan = _write_plan(tmp_path / "plan.json", oracle="a11y")
    monkeypatch.delenv("SHOP_SECRET_TOKEN", raising=False)
    _write_settings(
        tmp_path / "testence.json",
        {
            "schema": "testence/readiness/1",
            "checks": [
                {"id": "token", "type": "env", "variables": ["SHOP_SECRET_TOKEN"]},
            ],
            "scenarios": {"checkout": ["token"]},
        },
    )

    result = prepare_plan(plan, tmp_path)

    assert result["status"] == "blocked"
    blockers = result["scenarios"][0]["blockers"]
    assert [item["kind"] for item in blockers] == ["oracle", "check"]
    assert "a11y" in blockers[0]["detail"]
    assert "SHOP_SECRET_TOKEN" in blockers[1]["detail"]


def test_prepare_blocks_unmapped_scenario_by_default(tmp_path):
    plan = _write_plan(tmp_path / "plan.json")
    _write_settings(
        tmp_path / "testence.json",
        {
            "schema": "testence/readiness/1",
            "oracle_adapters": ["api"],
            "checks": [],
            "scenarios": {},
        },
    )

    result = prepare_plan(plan, tmp_path)

    assert result["scenarios"][0]["blockers"] == [
        {"kind": "configuration", "detail": "scenario has no readiness check mapping"}
    ]


def test_prepare_without_readiness_config_returns_actionable_blockers(tmp_path):
    plan = _write_plan(tmp_path / "plan.json")
    (tmp_path / "testence.json").write_text(
        json.dumps({"project_id": "shop", "headed": False}), encoding="utf-8"
    )

    result = prepare_plan(plan, tmp_path)

    assert result["status"] == "blocked"
    assert [item["kind"] for item in result["scenarios"][0]["blockers"]] == [
        "oracle",
        "configuration",
    ]


def test_prepare_rejects_unknown_check_reference(tmp_path):
    plan = _write_plan(tmp_path / "plan.json")
    _write_settings(
        tmp_path / "testence.json",
        {
            "schema": "testence/readiness/1",
            "oracle_adapters": ["api"],
            "checks": [],
            "scenarios": {"checkout": ["missing"]},
        },
    )

    with pytest.raises(ReadinessError, match="unknown check"):
        prepare_plan(plan, tmp_path)


def test_plan_prepare_cli_uses_exit_three_for_actionable_blockers(tmp_path, capsys):
    plan = _write_plan(tmp_path / "plan.json")
    _write_settings(
        tmp_path / "testence.json",
        {
            "schema": "testence/readiness/1",
            "oracle_adapters": ["api"],
            "checks": [],
            "scenarios": {},
        },
    )

    exit_code = main(["plan", "prepare", str(plan), "--project", str(tmp_path), "--json"])
    result = json.loads(capsys.readouterr().out)

    assert exit_code == 3
    assert result["status"] == "blocked"


def test_http_check_can_prove_a_json_fixture(tmp_path, monkeypatch):
    class Response(BytesIO):
        status = 200

    plan = _write_plan(tmp_path / "plan.json")
    _write_settings(
        tmp_path / "testence.json",
        {
            "schema": "testence/readiness/1",
            "oracle_adapters": ["api"],
            "checks": [
                {
                    "id": "seed",
                    "type": "http",
                    "path": "/api/seed?token=must-not-enter-report",
                    "status": 200,
                    "json_pointer": "/tenant/slug",
                    "equals": "qa-tenant",
                }
            ],
            "scenarios": {"checkout": ["seed"]},
        },
    )
    monkeypatch.setattr(
        "testence.readiness.urllib.request.urlopen",
        lambda *_args, **_kwargs: Response(b'{"tenant":{"slug":"qa-tenant"}}'),
    )

    result = prepare_plan(plan, tmp_path)

    assert result["status"] == "ready", json.dumps(result, indent=2)
    assert result["checks"][0]["detail"].endswith("returned 200")
    assert "must-not-enter-report" not in json.dumps(result)


def test_apply_fixes_runs_argv_without_shell_and_rechecks(tmp_path, monkeypatch):
    plan = _write_plan(tmp_path / "plan.json")
    _write_settings(
        tmp_path / "testence.json",
        {
            "schema": "testence/readiness/1",
            "oracle_adapters": ["api"],
            "checks": [
                {
                    "id": "seed",
                    "type": "file",
                    "path": "seed.ready",
                    "fix": {"argv": ["seed-tool", "prepare"], "timeout_ms": 5_000},
                }
            ],
            "scenarios": {"checkout": ["seed"]},
        },
    )
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        (Path(kwargs["cwd"]) / "seed.ready").write_text("ready", encoding="utf-8")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("testence.readiness.subprocess.run", run)

    blocked = prepare_plan(plan, tmp_path)
    result = prepare_plan(plan, tmp_path, apply_fixes=True)

    assert blocked["status"] == "blocked"
    assert blocked["fixes"] == []
    assert result["status"] == "ready"
    assert result["fixes"][0]["status"] == "applied"
    assert result["fixes"][0]["check_ok_after"] is True
    assert calls == [
        (
            ["seed-tool", "prepare"],
            {
                "cwd": tmp_path.resolve(),
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "check": False,
                "timeout": 5.0,
            },
        )
    ]


def test_fix_recipe_rejects_shell_command_strings(tmp_path):
    plan = _write_plan(tmp_path / "plan.json")
    _write_settings(
        tmp_path / "testence.json",
        {
            "schema": "testence/readiness/1",
            "oracle_adapters": ["api"],
            "checks": [
                {
                    "id": "seed",
                    "type": "file",
                    "path": "seed.ready",
                    "fix": {"argv": "seed-tool prepare"},
                }
            ],
            "scenarios": {"checkout": ["seed"]},
        },
    )

    with pytest.raises(ReadinessError, match="fix.argv must be an array"):
        prepare_plan(plan, tmp_path)
