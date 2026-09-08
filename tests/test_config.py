import json

import pytest

from testence.config import Settings
from testence.engine import create_engine


def test_defaults_are_inert(tmp_path):
    settings = Settings.load(tmp_path)
    assert settings.auth == "none"
    assert settings.base_url == ""
    assert settings.browser_channel == "chromium"
    assert settings.project_id == "unconfigured"


def test_project_id_is_explicit_or_derived_from_package_name(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "Acme Checkout"\nversion = "1.0"\n', encoding="utf-8"
    )
    assert Settings.load(tmp_path).project_id == "acme-checkout"
    assert Settings.load(tmp_path, project_id="owned.namespace").project_id == "owned.namespace"

    with pytest.raises(ValueError, match="project_id"):
        Settings.load(tmp_path, project_id="Not Valid")


def test_bundled_playwright_chromium_is_the_engine_default(tmp_path):
    settings = Settings.load(tmp_path)
    engine = create_engine(settings)
    assert engine.browser_channel == "chromium"
    assert engine.capture_network_bodies is False
    assert engine.capture_screenshots is False


def test_capture_policy_is_explicit_and_bounded(tmp_path):
    settings = Settings.load(tmp_path)
    settings.extra["capture_policy"] = {
        "network_bodies": True,
        "screenshots": True,
        "body_content_types": ["application/json"],
        "body_cap_bytes": 1024,
    }

    engine = create_engine(settings)

    assert engine.capture_network_bodies is True
    assert engine.capture_screenshots is True
    assert engine.body_cap_bytes == 1024

    settings.extra["capture_policy"]["body_cap_bytes"] = 65537
    with pytest.raises(ValueError, match="body_cap_bytes"):
        create_engine(settings)


def test_browser_channel_can_be_overridden(tmp_path, monkeypatch):
    monkeypatch.setenv("TESTENCE_BROWSER_CHANNEL", "chrome")
    assert Settings.load(tmp_path).browser_channel == "chrome"


def test_settings_file_and_profile_selection(tmp_path):
    (tmp_path / "testence.json").write_text(
        json.dumps(
            {
                "api_prefix": "/api/",
                "profiles": {
                    "dev1": {"base_url": "https://dev1.example.test/", "auth": "form"},
                    "local": {"base_url": "http://localhost:4200", "auth": "api-session"},
                },
            }
        ),
        encoding="utf-8",
    )

    dev1 = Settings.load(tmp_path, profile="dev1")
    assert dev1.base_url == "https://dev1.example.test"  # trailing slash normalized
    assert dev1.auth == "form" and dev1.profile == "dev1"

    local = Settings.load(tmp_path, profile="local")
    assert local.auth == "api-session"
    assert local.api_prefix == "/api/"  # top-level key still applies


def test_unknown_profile_lists_known_ones(tmp_path):
    (tmp_path / "testence.json").write_text(
        json.dumps({"profiles": {"dev1": {}, "dev2": {}}}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="dev1, dev2"):
        Settings.load(tmp_path, profile="nope")


def test_env_file_read_and_env_overrides_it(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "# shared environment\nTESTENCE_BASE_URL=http://from-dotenv\nTESTENCE_AUTH=form\n",
        encoding="utf-8",
    )
    settings = Settings.load(tmp_path)
    assert settings.base_url == "http://from-dotenv"

    monkeypatch.setenv("TESTENCE_BASE_URL", "http://from-environ")
    assert Settings.load(tmp_path).base_url == "http://from-environ"


def test_env_local_wins_over_env(tmp_path):
    (tmp_path / ".env").write_text("TESTENCE_BASE_URL=http://shared\n", encoding="utf-8")
    (tmp_path / ".env.local").write_text("TESTENCE_BASE_URL=http://mine\n", encoding="utf-8")
    assert Settings.load(tmp_path).base_url == "http://mine"


def test_explicit_override_beats_everything(tmp_path):
    (tmp_path / ".env").write_text("TESTENCE_BASE_URL=http://from-dotenv\n", encoding="utf-8")
    settings = Settings.load(tmp_path, base_url="http://explicit")
    assert settings.base_url == "http://explicit"


def test_unknown_keys_land_in_extra(tmp_path):
    (tmp_path / "testence.json").write_text(
        json.dumps(
            {
                "profiles": {"dev1": {"base_url": "http://x", "session_cookie": "session_id"}},
            }
        ),
        encoding="utf-8",
    )
    settings = Settings.load(tmp_path, profile="dev1")
    assert settings.extra["session_cookie"] == "session_id"


def test_describe_carries_no_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("TESTENCE_PASSWORD", "very-secret")
    monkeypatch.setenv("TESTENCE_USER", "u@example.test")
    settings = Settings.load(tmp_path, base_url="http://x", auth="form")
    assert "very-secret" not in str(settings.describe())
    assert settings.credentials().username == "u@example.test"


def test_from_settings_builds_each_scheme(tmp_path, monkeypatch):
    from testence.auth import from_settings

    monkeypatch.setenv("TESTENCE_USER", "u@example.test")
    monkeypatch.setenv("TESTENCE_PASSWORD", "p")
    for scheme, expected in [
        ("none", "none"),
        ("form", "form"),
        ("api-session", "api-session"),
        ("bearer", "bearer"),
        ("jwt", "bearer"),
        ("basic", "basic"),
        ("attached", "attached"),
    ]:
        settings = Settings.load(tmp_path, base_url="http://x", auth=scheme)
        assert from_settings(settings).scheme == expected


def test_from_settings_rejects_unknown_scheme(tmp_path):
    from testence.auth import from_settings

    with pytest.raises(ValueError, match="unknown auth scheme"):
        from_settings(Settings.load(tmp_path, auth="magic"))


def test_session_cache_is_opt_in_scoped_and_expiring(tmp_path, monkeypatch):
    from testence.auth import CachedSessionAuth, from_settings

    monkeypatch.setenv("TESTENCE_USER", "u@example.test")
    monkeypatch.setenv("TESTENCE_PASSWORD", "p")
    settings = Settings.load(
        tmp_path,
        base_url="https://app.example.test",
        auth="api-session",
        runs_root=str(tmp_path / "runs"),
    )
    settings.extra.update(
        {
            "session_probe_path": "/api/v1/auth/me",
            "session_cache_ttl_s": 900,
            "session_expected_role": "qa-admin",
        }
    )

    adapter = from_settings(settings)
    assert isinstance(adapter, CachedSessionAuth)
    assert adapter.cache_ttl_s == 900
    assert adapter.scope["role"] == "qa-admin"
    assert "u@example.test" not in adapter.cache_file.name


@pytest.mark.parametrize("probe", ["https://other.example/me", "//other.example/me", "me"])
def test_session_cache_probe_must_stay_on_base_origin(tmp_path, monkeypatch, probe):
    from testence.auth import from_settings

    monkeypatch.setenv("TESTENCE_USER", "u@example.test")
    monkeypatch.setenv("TESTENCE_PASSWORD", "p")
    settings = Settings.load(tmp_path, base_url="https://app.example.test", auth="api-session")
    settings.extra["session_probe_path"] = probe

    with pytest.raises(ValueError, match="root-relative"):
        from_settings(settings)
