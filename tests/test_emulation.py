"""Device, locale, time zone, geolocation and colour-scheme emulation (L12 item 4).

Settings ``emulation`` becomes options of the browser context Testence creates, so a
suite runs "as a phone in Berlin in dark mode" without a line of Playwright. Each
case reads back what the page itself sees.
"""

from __future__ import annotations

import pytest

from testence.config import Settings
from testence.engine import create_engine
from testence.engine.playwright_cdp import PlaywrightCdpEngine

from .mock_app import MockApp

BERLIN = {"latitude": 52.52, "longitude": 13.405}


@pytest.fixture(scope="module")
def app():
    with MockApp() as mock:
        yield mock.base_url


def _started(emulation: dict, base_url: str) -> PlaywrightCdpEngine:
    engine = PlaywrightCdpEngine(base_url, headed=False, emulation=emulation)
    engine.start()
    return engine


def test_locale_time_zone_and_colour_scheme_reach_the_page(app):
    engine = _started(
        {"locale": "de-DE", "timezone_id": "Europe/Berlin", "color_scheme": "dark"}, app
    )
    try:
        engine.goto("/login")
        assert engine.eval_js("navigator.language") == "de-DE"
        assert engine.eval_js("Intl.DateTimeFormat().resolvedOptions().timeZone") == (
            "Europe/Berlin"
        )
        assert engine.eval_js("matchMedia('(prefers-color-scheme: dark)').matches") is True
        # A fresh context for the next warm test keeps the same emulation.
        engine.reset_session()
        engine.goto("/login")
        assert engine.eval_js("navigator.language") == "de-DE"
    finally:
        engine.stop()


def test_a_named_device_sets_its_viewport_and_user_agent(app):
    engine = _started({"device": "iPhone 13"}, app)
    try:
        engine.goto("/login")
        assert "iPhone" in engine.eval_js("navigator.userAgent")
        # The screen, not the layout: a page without a viewport meta tag lays out at 980.
        assert engine.eval_js("screen.width") == 390
        assert engine.eval_js("navigator.maxTouchPoints") > 0
    finally:
        engine.stop()


def test_geolocation_is_granted_with_the_position(app):
    engine = _started({"geolocation": BERLIN}, app)
    try:
        engine.goto("/login")
        position = engine.eval_js(
            "new Promise((ok, fail) => navigator.geolocation.getCurrentPosition("
            "p => ok([p.coords.latitude, p.coords.longitude]), fail))"
        )
        assert position == [52.52, 13.405]
    finally:
        engine.stop()


def test_an_unknown_device_names_the_close_ones(app):
    engine = PlaywrightCdpEngine(app, headed=False, emulation={"device": "iphone 13"})
    with pytest.raises(ValueError, match="did you mean iPhone 13"):
        engine.start()
    engine.stop()


@pytest.mark.parametrize(
    ("emulation", "message"),
    [
        ({"devise": "iPhone 13"}, "unknown emulation field"),
        ({"color_scheme": "sepia"}, "color_scheme"),
        ({"geolocation": {"latitude": 91, "longitude": 0}}, "geolocation"),
        ({"geolocation": {"lat": 1, "lon": 2}}, "geolocation"),
        ({"permissions": "geolocation"}, "permissions"),
        ({"locale": ""}, "locale"),
        ("dark", "must be an object"),
    ],
)
def test_malformed_emulation_is_refused_before_a_browser_starts(emulation, message):
    with pytest.raises(ValueError, match=message):
        PlaywrightCdpEngine(emulation=emulation)


def test_an_attached_browser_is_not_emulated():
    with pytest.raises(ValueError, match="attached"):
        PlaywrightCdpEngine(cdp_url="http://127.0.0.1:9222", emulation={"locale": "de-DE"})


def test_settings_pass_emulation_to_the_engine_and_the_run_fingerprint(tmp_path):
    (tmp_path / "testence.json").write_text(
        '{"extra": {"emulation": {"locale": "fr-FR", "color_scheme": "dark"}}}',
        encoding="utf-8",
    )
    settings = Settings.load(tmp_path)
    engine = create_engine(settings)
    assert engine.emulation == {"locale": "fr-FR", "color_scheme": "dark"}  # type: ignore[attr-defined]
    assert settings.describe()["emulation"] == {"locale": "fr-FR", "color_scheme": "dark"}
