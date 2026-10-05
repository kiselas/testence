"""Reproduce duplicate dialog controls and one-command discovery without a private target."""

from __future__ import annotations

import json
from urllib.parse import quote

import pytest

from testence.cli import main
from testence.discovery import explore
from testence.dsl import Actions
from testence.dsl.steps import StepFailed
from testence.engine import Target
from testence.engine.playwright_cdp import PlaywrightCdpEngine
from testence.evidence import EvidenceWriter
from testence.mcp import McpServer

PAGE = "data:text/html," + quote("""<!doctype html><meta charset=utf-8>
<button>Close</button><div role=status>HE-Юникод-🔐-主机模板</div>
<section role=dialog aria-label=Import>
  <button onclick="document.getElementById('result').textContent='closed'">Close</button>
  <input aria-label=Name value="suggested"><input aria-label=Empty>
</section>
<input aria-label=Name value="outside">
<table><tr data-key="synthetic-42"><td>HE-Юникод-🔐-主机模板</td></tr></table>
<p id=result>ready</p>
""")
DIALOG = Target("role", "dialog", name="Import")


@pytest.fixture
def ex(tmp_path):
    engine = PlaywrightCdpEngine(headed=False)
    writer = EvidenceWriter(tmp_path / "evidence")
    try:
        engine.start()
        engine.goto(PAGE)
        engine.timeout_ms = 500
        yield Actions(engine, writer, "authoring-friction")
    finally:
        writer.close()
        engine.stop()


def test_dialog_scope_selects_the_intended_close_and_field(ex):
    name = Target("role", "textbox", name="Name", within=DIALOG)
    ex.expect_value(name, "suggested")
    assert ex.input_value(name) == "suggested"
    ex.fill(name, "chosen")
    ex.expect_value(name, "chosen")
    ex.click(Target("role", "button", name="Close", within=DIALOG))
    ex.expect_text(Target("css", "#result"), "closed")
    ex.expect_value(Target("role", "textbox", name="Name", nth=1), "outside")


def test_unscoped_duplicates_fail_with_indexed_diagnostics(ex):
    with pytest.raises(StepFailed) as error:
        ex.click(Target("role", "button", name="Close"))
    assert "nth=0:" in str(error.value)
    assert "nth=1:" in str(error.value)
    assert "within=Target" in str(error.value)
    ex.expect_text(Target("css", "#result"), "ready")


def test_nested_scope_and_ambiguous_value_read(ex):
    name = Target(
        "role",
        "textbox",
        name="Name",
        within=Target("css", "section", within=Target("css", "body")),
    )
    assert ex.input_value(name) == "suggested"
    assert ex.input_value(Target("role", "textbox", name="Empty", within=DIALOG)) == ""
    with pytest.raises(StepFailed, match="2 elements match"):
        ex.input_value(Target("role", "textbox", name="Name"))


def test_read_value_does_not_record_the_value(ex):
    target = Target("role", "textbox", name="Name", within=DIALOG)
    # Test-only setup; no real credentials or external data.
    ex.engine.eval_js(
        "() => document.querySelector('section input').value='synthetic-private-value'"
    )
    assert ex.input_value(target) == "synthetic-private-value"
    ex.writer.close()
    assert "synthetic-private-value" not in ex.writer.path.read_text(encoding="utf-8")


def test_cli_maps_unicode_rows_and_duplicates_in_one_call(tmp_path, capsys):
    (tmp_path / "testence.json").write_text(json.dumps({"auth": "none"}), encoding="utf-8")
    assert main(["explore", PAGE, "--project", str(tmp_path), "--json"]) == 0
    text = capsys.readouterr().out
    assert text.isascii()
    payload = json.loads(text)
    assert payload["rows"] == [{"key": "synthetic-42", "text": "HE-Юникод-🔐-主机模板"}]
    close = next(e for e in payload["elements"] if e["target"].get("name") == "Close")
    assert close["matches"] == 2 and close["unique"] is False
    assert "Import" in payload["aria"]


def test_mcp_accepts_the_same_scoped_target():
    target = McpServer._target(
        {
            "kind": "role",
            "value": "button",
            "name": "Close",
            "within": {"kind": "role", "value": "dialog", "name": "Import"},
        }
    )
    assert target.within == DIALOG


def test_invalid_privacy_policy_fails_before_launch(tmp_path, monkeypatch, capsys):
    from testence import discovery

    (tmp_path / "testence.json").write_text(
        json.dumps(
            {"auth": "none", "evidence": {"redact": {"pii": ["synthetic-invalid-private"]}}}
        ),
        encoding="utf-8",
    )

    def forbidden(_settings):
        pytest.fail("invalid privacy policy launched a browser")

    monkeypatch.setattr(discovery, "create_engine", forbidden)
    assert main(["explore", "/", "--project", str(tmp_path), "--json"]) == 2
    captured = capsys.readouterr()
    assert not captured.out
    assert "redaction configuration" in captured.err
    assert "synthetic-invalid-private" not in captured.err


def test_explore_redacts_rows_and_stops_even_when_navigation_fails(tmp_path, monkeypatch):
    from testence import discovery

    monkeypatch.setenv("TESTENCE_SYNTHETIC_SECRET", "synthetic-private-value")
    (tmp_path / "testence.json").write_text(
        json.dumps(
            {"auth": "none", "evidence": {"redact": {"env": ["TESTENCE_SYNTHETIC_SECRET"]}}}
        ),
        encoding="utf-8",
    )

    class Engine:
        stopped = False
        fail = False

        def start(self):
            pass

        def goto(self, _url):
            if self.fail:
                raise RuntimeError("synthetic-private-value")

        def stop(self):
            self.stopped = True

        def settle(self, _timeout):
            pass

        def current_url(self):
            return "http://synthetic.test/"

        def aria_snapshot(self):
            return "synthetic-private-value"

        def candidate_elements(self):
            return []

        def eval_js(self, _script):
            return [{"key": "synthetic-private-value"}]

    engine = Engine()
    monkeypatch.setattr(discovery, "create_engine", lambda _settings: engine)
    assert "synthetic-private-value" not in json.dumps(explore(tmp_path, "/"))
    assert engine.stopped
    engine.stopped = False
    engine.fail = True
    with pytest.raises(ValueError) as error:
        explore(tmp_path, "/")
    assert "synthetic-private-value" not in str(error.value)
    assert engine.stopped
