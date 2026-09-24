"""Shape- and part-based redaction, the project policy and export-time redaction.

Every canary is unique so a leak names the rule that missed it, and none of them is
configured anywhere: the redactor has to recognize each by its field name or by its
shape (ADR-0024).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from testence.engine import NetRecord, Target
from testence.evidence import REDACTED, RUN_ID_ENV, EvidenceWriter
from testence.evidence.sanitize import RedactionPolicy, sanitize, sanitize_text
from testence.export import ExporterError, export_run
from testence.report import render_report
from testence.triage import assemble_pack

ROOT = Path(__file__).parents[1]
_JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiJzeW50aGV0aWMtdXNlciJ9."
    "c3ludGhldGljLXNpZ25hdHVyZS1ub3QtcmVhbA"
)
_BODY_SECRETS = {
    "authToken": "cnry-authtoken-01",
    "sessionToken": "cnry-sessiontoken-02",
    "apiToken": "cnry-apitoken-03",
    "csrfToken": "cnry-csrf-04",
    "x_csrf": "cnry-xcsrf-05",
    "jwt": "cnry-jwtfield-06",
    "pwd": "cnry-pwd-07",
    "pass": "cnry-pass-08",
    "passcode": "cnry-passcode-09",
    "otp": "cnry-otp-10",
    "pin": "cnry-pin-11",
    "sessionid": "cnry-sessionid-12",
    "session_id": "cnry-session-id-13",
    "sid": "cnry-sid-14",
    "X-API-Key": "cnry-xapikey-15",
    "accessKey": "cnry-accesskey-16",
    "private-key": "cnry-privatekey-17",
    "client_secret": "cnry-clientsecret-18",
    "dbPassword": "cnry-dbpassword-19",
    "credentials": "cnry-credentials-20",
    "signature": "cnry-signature-21",
    "refresh_token": "cnry-refresh-22",
    "bearerToken": "cnry-bearer-23",
    "authKey": "cnry-authkey-24",
}
_URL_SECRETS = {
    "code": "cnry-oauthcode-25",
    "session": "cnry-urlsession-26",
    "sig": "cnry-urlsig-27",
    "key": "cnry-urlkey-28",
    "X-Amz-Signature": "cnry-amzsig-29",
    "access_token": "cnry-urlaccess-30",
}
_SHAPE_SECRETS = [
    _JWT,
    "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2",
    "github_pat_" + "11ABCDEFG0123456789_abcdefgh",
    "glpat-" + "abcdefghijklmnopqrst",
    "xoxb-" + "1234567890-abcdefghij",
    "sk-" + "synthetic0123456789abcdef",
    "AKIA" + "ABCDEFGHIJKLMNOP",
    "4111 1111 1111 1111",
    "5555555555554444",
]
_TEXT_SECRETS = {
    "token=": "cnry-texttoken-31",
    "password: ": "cnry-textpassword-32",
    "X-Api-Key: ": "cnry-textapikey-33",
    "Authorization: Bearer ": "cnry-textbearer-34",
    '"session_token":"': "cnry-textsession-35",
}
# Close to a rule, but evidence: over-redaction would hide the failure itself.
_KEEP = {
    "passage": "keep-passage",
    "author": "keep-author",
    "keyboard": "keep-keyboard",
    "pinned": "keep-pinned",
    "sessions_count": "keep-count",
    "digest": "sha256:" + "4111111111111111" + "ab" * 24,
    "order_id": "4111111111111112",
    "epoch_ms": "1767268800100",
}


def _all_canaries() -> list[str]:
    values = [*_BODY_SECRETS.values(), *_URL_SECRETS.values(), *_TEXT_SECRETS.values()]
    return values + _SHAPE_SECRETS


class _ShapeEngine:
    """Network, console and ARIA evidence carrying secrets no one configured."""

    def settle(self, timeout_ms: int = 1_500) -> bool:
        return True

    def aria_snapshot(self) -> str:
        cards = "\n".join(f'- text "{value}"' for value in _SHAPE_SECRETS)
        return f'- heading "Checkout"\n{cards}\n- text "{_KEEP["passage"]}"'

    def network_log(self) -> list[NetRecord]:
        query = "&".join(f"{name}={value}" for name, value in _URL_SECRETS.items())
        body = {**_BODY_SECRETS, **_KEEP}
        return [
            NetRecord(
                "POST",
                f"https://app.example.test/api/login?{query}&page=2",
                200,
                0.0,
                5.0,
                request_body=json.dumps({"login": "synthetic", "pwd": _BODY_SECRETS["pwd"]}),
                response_body=json.dumps(body),
            ),
            NetRecord("GET", "https://app.example.test/api/me?sid=cnry-sid-14", 200, 0.0, 3.0),
        ]

    def console_log(self) -> list[dict[str, Any]]:
        lines = [f"{prefix}{value}" for prefix, value in _TEXT_SECRETS.items()]
        lines.extend(f"leaked {value} in log" for value in _SHAPE_SECRETS)
        return [{"level": "error", "text": line} for line in lines]

    def screenshot(self, path: str) -> None:
        Path(path).write_bytes(b"")

    def browser_manifest(self) -> dict[str, Any]:
        return {"cdp_endpoint": "http://127.0.0.1:9222", "page_url": "https://app.example.test"}


def test_unconfigured_secrets_are_absent_from_every_persisted_and_exported_file(tmp_path):
    writer = EvidenceWriter(tmp_path, run_id="r-shapes", worker="", redact_values=[])
    writer.emit("run.start", fingerprint={"auth": "api-session"})
    test_id = "tests/test_checkout.py::test_pay"
    writer.emit("test.start", test=test_id, file="tests/test_checkout.py")
    pack = assemble_pack(
        _ShapeEngine(),
        writer,
        test_id,
        error=f"AssertionError: token={_TEXT_SECRETS['token=']} and {_JWT}",
        oracle_diff=[{"field": "authToken", "ui": _BODY_SECRETS["authToken"], "api": "x"}],
    )
    writer.emit(
        "test.end",
        test=test_id,
        status="failed",
        error=f'"session_token":"{_TEXT_SECRETS[chr(34) + "session_token" + chr(34) + ":" + chr(34)]}"',
        pack=str(pack.relative_to(writer.run_dir)),
    )
    writer.emit("run.end", duration_ms=1.0, passed=0, failed=1)
    writer.close()

    render_report(writer.run_dir, tmp_path / "report.html")
    export_run(writer.run_dir, "allure", tmp_path / "allure")
    export_run(writer.run_dir, "ctrf", tmp_path / "ctrf")

    text_suffixes = {".json", ".jsonl", ".txt", ".md", ".html", ".properties"}
    persisted = [path for path in tmp_path.rglob("*") if path.suffix in text_suffixes]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in persisted)
    assert [value for value in _all_canaries() if value in combined] == []
    for value in _KEEP.values():
        assert value in combined, f"over-redacted: {value}"
    assert "api-session" in combined, "the auth scheme name is evidence, not a secret"


def _raw_run(tmp_path: Path, *, redaction: dict[str, Any] | None = None) -> Path:
    """A valid run whose files hold secrets in clear text, as an older release wrote.

    The ledger is produced by the real writer and edited afterwards: the writer itself
    would redact these values, which is exactly what an older release did not do.
    """
    writer = EvidenceWriter(tmp_path / "runs", run_id="r-legacy", worker="", redact_values=[])
    writer.emit("run.start", **({"redaction": redaction} if redaction is not None else {}))
    writer.emit("test.start", test="test_legacy", file="tests/test_legacy.py")
    writer.emit(
        "test.end",
        test="test_legacy",
        status="failed",
        error="expected __TOKEN_SLOT__",
        pack="packs/test_legacy",
    )
    writer.emit("run.end", duration_ms=1.0, passed=0, failed=1)
    writer.close()
    ledger = writer.run_dir / "run.jsonl"
    ledger.write_text(
        ledger.read_text(encoding="utf-8").replace(
            "__TOKEN_SLOT__", "authToken=legacy-clear-authtoken-77"
        ),
        encoding="utf-8",
    )
    pack_dir = writer.run_dir / "packs" / "test_legacy"
    pack_dir.mkdir(parents=True)
    (pack_dir / "network.jsonl").write_text(
        json.dumps({"method": "POST", "url": "https://a/api?code=legacy-code-78", "status": 500})
        + "\n"
        + json.dumps({"method": "GET", "url": "https://a/api/me", "status": 200})
        + "\n",
        encoding="utf-8",
    )
    (pack_dir / "console.txt").write_text("authToken=legacy-clear-authtoken-77\n", encoding="utf-8")
    (pack_dir / "aria.txt").write_text('- text "customer ivan@example.test"\n', encoding="utf-8")
    (pack_dir / "screenshot.png").write_bytes(b"\x89PNG synthetic")
    return writer.run_dir


def _exported_text(directory: Path) -> str:
    return "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in directory.rglob("*")
        if path.is_file()
    )


def test_export_and_report_redact_evidence_written_before_a_rule_existed(tmp_path):
    run_dir = _raw_run(tmp_path)
    export_run(run_dir, "allure", tmp_path / "allure")
    export_run(run_dir, "ctrf", tmp_path / "ctrf")
    render_report(run_dir, tmp_path / "report.html")
    for location in (tmp_path / "allure", tmp_path / "ctrf"):
        text = _exported_text(location)
        assert "legacy-clear-authtoken-77" not in text
        assert "legacy-code-78" not in text
    assert "legacy-clear-authtoken-77" not in (tmp_path / "report.html").read_text(encoding="utf-8")
    # Export redacts copies; it never rewrites the evidence of record.
    assert "legacy-clear-authtoken-77" in (run_dir / "run.jsonl").read_text(encoding="utf-8")


def test_export_applies_the_policy_the_run_recorded(tmp_path):
    policy = RedactionPolicy.from_config({"pii": ["email"]})
    run_dir = _raw_run(tmp_path / "with-policy", redaction=policy.to_json())
    export_run(run_dir, "allure", tmp_path / "allure")
    assert "ivan@example.test" not in _exported_text(tmp_path / "allure")

    plain = _raw_run(tmp_path / "plain")
    export_run(plain, "allure", tmp_path / "plain-allure")
    assert "ivan@example.test" in _exported_text(tmp_path / "plain-allure")


@pytest.mark.parametrize(
    ("policy", "shipped"),
    [
        ("full", {"network.jsonl", "console.txt", "aria.txt", "screenshot.png"}),
        ("minimal", {"console.txt"}),
        ("none", set()),
    ],
)
def test_attachment_policy_limits_what_an_export_ships(tmp_path, policy, shipped):
    out = tmp_path / "allure"
    export_run(_raw_run(tmp_path), "allure", out, attachments=policy)
    result = json.loads(next(out.glob("*-result.json")).read_text(encoding="utf-8"))
    assert {item["name"] for item in result.get("attachments", [])} == shipped
    assert len(list(out.glob("*-attachment*"))) == len(shipped)


def test_unknown_attachment_policy_is_rejected(tmp_path):
    with pytest.raises(ExporterError, match="attachment policy"):
        export_run(_raw_run(tmp_path), "allure", tmp_path / "out", attachments="some")


def test_policy_adds_keys_allows_keys_and_parameters():
    policy = RedactionPolicy.from_config(
        {
            "keys": ["tenant_ref"],
            "allow_keys": ["session_status"],
            "url_params": ["ticket"],
            "pii": ["email", "phone"],
        }
    )
    document = sanitize(
        {
            "tenantRef": "t-1",
            "session_status": "active",
            "note": "mail ivan@example.test or call +7 (999) 000-00-00",
        },
        policy=policy,
    )
    assert document["tenantRef"] == REDACTED
    assert document["session_status"] == "active"
    assert "ivan@example.test" not in document["note"]
    assert "000-00-00" not in document["note"]
    assert "ticket=" + REDACTED in sanitize_text("https://a/b?ticket=abc&page=1", policy=policy)
    assert RedactionPolicy.from_json(policy.to_json()) == policy


def test_an_assignment_does_not_hide_the_next_one():
    text = sanitize_text("console: token=abc123 status: 200")
    assert text == f"console: token={REDACTED} status: 200"


@pytest.mark.parametrize(
    ("config", "message"),
    [
        ([], "must be an object"),
        ({"keys": "token"}, "must be a list"),
        ({"pii": ["passport"]}, "supports email, phone"),
        ({"keys": [""]}, "non-empty strings"),
        ({"unknown": []}, "unknown evidence.redact field"),
    ],
)
def test_invalid_redaction_policy_is_rejected(config, message):
    with pytest.raises(ValueError, match=message):
        RedactionPolicy.from_config(config)


def test_settings_resolve_policy_values_and_masks(monkeypatch):
    from testence.config import Settings

    monkeypatch.setenv("SHOP_API_TOKEN", "value-from-environment-91")
    settings = Settings(
        extra={
            "evidence": {
                "redact": {"env": ["SHOP_API_TOKEN"], "keys": ["tenant_ref"]},
                "mask": [{"kind": "testid", "value": "card-number"}],
            }
        }
    )
    assert "value-from-environment-91" in settings.redaction_values()
    assert "tenantref" in settings.redaction_policy().keys
    (mask,) = settings.screenshot_masks()
    assert (mask.kind, mask.value) == ("testid", "card-number")
    # The policy is written into the ledger, so it carries names, never values.
    assert "value-from-environment-91" not in json.dumps(settings.redaction_policy().to_json())


@pytest.mark.parametrize(
    ("evidence", "method", "message"),
    [
        ({"mask": {"kind": "css"}}, "screenshot_masks", "must be a list"),
        ({"mask": [{"kind": "xpath", "value": "//x"}]}, "screenshot_masks", "unknown target"),
        ({"mask": [{"kind": "css", "value": "#x", "color": "red"}]}, "screenshot_masks", "kind"),
        ({"redact": {"env": "TOKEN"}}, "redaction_values", "list of variable names"),
        ({"trace": True}, "redaction_policy", "unknown evidence field"),
    ],
)
def test_invalid_evidence_settings_are_rejected(evidence, method, message):
    from testence.config import Settings

    with pytest.raises(ValueError, match=message):
        getattr(Settings(extra={"evidence": evidence}), method)()


def test_invalid_evidence_settings_fail_the_session_before_tests(tmp_path):
    project = tmp_path / "consumer"
    project.mkdir()
    (project / "testence.json").write_text(
        '{"evidence": {"redact": {"pii": ["passport"]}}}', encoding="utf-8"
    )
    (project / "test_nothing.py").write_text("def test_nothing():\n    assert True\n")
    env = os.environ.copy()
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env.pop(RUN_ID_ENV, None)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "src"), value] if (value := env.get("PYTHONPATH")) else [str(ROOT / "src")]
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "testence.pytest_plugin",
            "--rootdir",
            str(project),
            "--testence-runs-root",
            str(project / "runs"),
            "-p",
            "no:cacheprovider",
            "-q",
        ],
        cwd=project,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert "invalid Testence evidence settings" in result.stdout + result.stderr
    assert "1 passed" not in result.stdout


def test_screenshot_masks_paint_over_configured_elements(tmp_path):
    from PIL import Image

    from testence.config import Settings
    from testence.engine import create_engine

    page = (
        "data:text/html,<style>body{margin:0;background:white}"
        "div{position:absolute;left:20px;top:20px;width:120px;height:40px;background:red}"
        "</style><div data-testid='card-number'>4111</div>"
    )

    def center_pixel(masks: list[dict[str, Any]]) -> tuple[int, ...]:
        settings = Settings(
            headed=False,
            debug_port=0,
            extra={"capture_policy": {"screenshots": True}, "evidence": {"mask": masks}},
        )
        engine = create_engine(settings)
        path = tmp_path / f"shot-{len(masks)}.png"
        try:
            engine.start()
            engine.goto(page)
            engine.screenshot(str(path))
            assert engine.browser_manifest()["capture"]["screenshot_masks"] == [
                Target(**mask).describe() for mask in masks
            ]
        finally:
            engine.stop()
        with Image.open(path) as image:
            return tuple(image.convert("RGB").getpixel((80, 40)))

    assert center_pixel([]) == (255, 0, 0)
    assert center_pixel([{"kind": "testid", "value": "card-number"}]) == (0, 0, 0)


def test_a_mask_change_makes_a_visual_baseline_incompatible(tmp_path):
    from testence.config import Settings
    from testence.engine import create_engine
    from testence.visual import VisualUnavailable, capture_baseline, compare_baseline

    settings = Settings(
        headed=False,
        debug_port=0,
        extra={
            "capture_policy": {"screenshots": True},
            "evidence": {"mask": [{"kind": "testid", "value": "card-number"}]},
        },
    )
    engine = create_engine(settings)
    try:
        engine.start()
        engine.goto("data:text/html,<div data-testid='card-number'>4111</div>")
        pinned = capture_baseline(engine, tmp_path / "baseline", provenance="masked control")
        engine.screenshot_masks = ()  # type: ignore[attr-defined]
        with pytest.raises(VisualUnavailable, match="profile mismatch"):
            compare_baseline(
                engine, tmp_path / "baseline", tmp_path / "out", baseline_digest=pinned
            )
    finally:
        engine.stop()
