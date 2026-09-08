from __future__ import annotations

import json
from urllib.parse import quote

import pytest

from testence.assurance import evaluate_attempt
from testence.cli import main
from testence.contracts import CAPABILITY_SCHEMA, SCHEMA_INVENTORY
from testence.dsl import Actions
from testence.engine import (
    Capability,
    EvidenceEngine,
    LifecycleEngine,
    Target,
    UnsupportedCapability,
    engine_capabilities,
)
from testence.engine.playwright_cdp import PlaywrightCdpEngine


class WriterProbe:
    def __init__(self) -> None:
        self.events = []

    def emit(self, kind, **payload):
        self.events.append({"kind": kind, **payload})


class PlatformFake:
    def capabilities(self):
        return frozenset({Capability.LIFECYCLE.value, Capability.EVIDENCE.value})

    def start(self):
        pass

    def stop(self, *, keep_browser=False):
        pass

    def reset_session(self):
        pass

    def network_log(self):
        return []

    def console_log(self):
        return []

    def wait_ledger(self):
        return []

    def reset_taps(self):
        pass

    def browser_manifest(self):
        return {"mode": "fake", "owns_browser": False, "owns_context": False}


def test_platform_fake_conforms_without_dom_or_playwright_types():
    fake = PlatformFake()

    assert isinstance(fake, LifecycleEngine)
    assert isinstance(fake, EvidenceEngine)
    assert engine_capabilities(fake) == {"lifecycle", "evidence"}

    actions = Actions(fake, WriterProbe(), "neutral")
    with pytest.raises(UnsupportedCapability) as caught:
        actions.click(Target("role", "button", name="Save"))
    assert caught.value.operation == "click"
    assert caught.value.required == {"browser.dom"}


def test_capability_cli_is_machine_readable_without_starting_browser(tmp_path, capsys):
    (tmp_path / "testence.json").write_text(
        '{"project_id":"capability-cli","headed":false}', encoding="utf-8"
    )

    assert main(["capabilities", "--project", str(tmp_path), "--json"]) == 0

    document = json.loads(capsys.readouterr().out)
    assert document["schema"] == CAPABILITY_SCHEMA
    assert document["schema"] == SCHEMA_INVENTORY["engine_capabilities"]
    assert document["backend"] == "playwright-cdp"
    assert document["capabilities"] == sorted(document["capabilities"])


def test_fast_actionability_is_recorded_and_downgrades_assurance():
    class LegacyEngine:
        def click(self, _target, *, fast=False):
            assert fast is True

        def element_fingerprint(self, _target):
            return {}

    writer = WriterProbe()
    Actions(LegacyEngine(), writer, "case").click(Target("role", "button", name="Save"), fast=True)
    events = [
        {
            "kind": "test.start",
            "assertions": [],
            "plan": {},
            "plan_digest": "",
            "test_digest": "",
            "policy_digest": "",
        },
        *writer.events,
    ]

    result = evaluate_attempt(events, {"status": "passed"})

    assert result["assurance"] == "unverified"
    assert result["weakenings"] == ["fast-actionability"]
    assert any("actionability weakened" in reason for reason in result["assurance_reasons"])


@pytest.fixture
def web_engine():
    engine = PlaywrightCdpEngine(headed=False)
    engine.start()
    yield engine
    engine.stop()


def _data_page(markup: str) -> str:
    return "data:text/html," + quote(markup)


def test_strict_target_rejects_ambiguous_matches(web_engine):
    web_engine.goto(_data_page("<button>Save</button><button>Save</button>"))

    with pytest.raises(Exception, match="strict mode violation"):
        web_engine.expect_visible(Target("role", "button", name="Save"), timeout_ms=500)


def test_web_capability_matrix_frame_shadow_keyboard_dialog_popup_and_files(web_engine, tmp_path):
    markup = """
    <input id='file' type='file'>
    <button id='dialog' onclick="prompt('Name?', 'x')">dialog</button>
    <button id='popup' onclick="window.open('about:blank')">popup</button>
    <a id='download' download='proof.txt' href='data:text/plain,proof'>download</a>
    <input id='focus'><div style='height:1200px'></div><button id='bottom'>bottom</button>
    <iframe id='frame' srcdoc="<button id='inside'>inside</button>"></iframe>
    <div id='host'></div>
    <script>
      const root = host.attachShadow({mode:'open'});
      root.innerHTML = '<button id="shadow">shadow</button>';
    </script>
    """
    web_engine.goto(_data_page(markup))

    source = tmp_path / "input.txt"
    source.write_text("input", encoding="utf-8")
    web_engine.upload(Target("css", "#file"), [str(source)])
    assert web_engine.eval_js("document.querySelector('#file').files[0].name") == "input.txt"

    web_engine.focus(Target("css", "#focus"))
    web_engine.press("A")
    assert web_engine.eval_js("document.querySelector('#focus').value") == "A"
    web_engine.scroll_into_view(Target("css", "#bottom"))
    assert web_engine.eval_js("document.querySelector('#bottom').getBoundingClientRect().top") < 800

    web_engine.expect_visible(Target("css", "#shadow"))
    with web_engine.frame(Target("css", "#frame")):
        web_engine.expect_visible(Target("css", "#inside"))

    assert web_engine.click_with_dialog(Target("css", "#dialog"), prompt="QA") == "Name?"
    web_engine.click_and_popup(Target("css", "#popup"))
    assert web_engine.current_url() == "about:blank"
    web_engine.switch_page(0)

    destination = tmp_path / "proof.txt"
    assert (
        web_engine.click_and_download(Target("css", "#download"), str(destination)) == "proof.txt"
    )
    assert destination.read_text(encoding="utf-8") == "proof"

    declared = web_engine.capabilities()
    for required in (
        Capability.FRAMES,
        Capability.POPUPS,
        Capability.FILES,
        Capability.DIALOGS,
        Capability.KEYBOARD,
        Capability.DOM,
    ):
        assert required.value in declared
