"""Settings: where to run, how to log in, with what timeouts.

Nothing about a target environment belongs in test code or in this repository —
base URLs, credentials and auth scheme all arrive from configuration. Layers,
highest precedence first:

1. explicit arguments (CLI flags, direct constructor args)
2. process environment (``TESTENCE_*``)
3. ``.env`` / ``.env.local`` in the project root (untracked; ``.env.local`` wins)
4. settings file: ``testence.toml`` (Python 3.11+) or ``testence.json``
5. built-in defaults

A settings file may declare **profiles** — one per environment — selected with
``TESTENCE_PROFILE``. That is what makes switching from a local target to staging a
one-word change instead of an edit::

    [profiles.staging]
    base_url = "https://staging.example.com"
    auth = "form"

Credentials never appear in a settings file that is tracked by git: keep them in
``.env.local`` (git-ignored) or the real environment. ``Settings.describe()`` is
what may be written into evidence — it carries no secret values.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ENV_PREFIX = "TESTENCE_"
SETTINGS_FILES = ("testence.toml", "testence.json")
ENV_FILES = (".env", ".env.local")


def _parse_env_file(path: Path) -> dict[str, str]:
    """Minimal KEY=VALUE parser: ``#`` comments, optional ``export``, quoted values."""
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        values[key.strip()] = value
    return values


def _load_settings_file(root: Path) -> dict[str, Any]:
    for name in SETTINGS_FILES:
        path = root / name
        if not path.exists():
            continue
        if path.suffix == ".json":
            return json.loads(path.read_text(encoding="utf-8"))
        try:
            import tomllib
        except ModuleNotFoundError:  # Python 3.10: TOML needs 3.11+
            raise RuntimeError(
                f"{name} needs Python 3.11+ for tomllib; use testence.json instead"
            ) from None
        return tomllib.loads(path.read_text(encoding="utf-8"))
    return {}


@dataclass
class Settings:
    """Resolved configuration for one run."""

    base_url: str = ""
    api_prefix: str = "/api/"
    auth: str = "none"
    login_path: str = "/login"
    api_login_path: str = ""
    cdp_url: str | None = None
    # Use the browser revision shipped with this Playwright release instead of a
    # machine-wide Chrome install. ``chromium`` also selects Playwright's regular
    # Chromium in headless mode, keeping headed and CI runs on the same engine.
    browser_channel: str = "chromium"
    headed: bool = True
    timeout_ms: int = 10_000
    #: Self-hosted targets may use a private CA that the browser trusts through the
    #: system store but Python's bundle does not. Prefer setting ca_bundle; disabling
    #: verification is an explicit last resort for isolated test environments.
    verify_tls: bool = True
    ca_bundle: str = ""
    runs_root: str = "runs"
    profile: str = ""
    user_var: str = "TESTENCE_USER"
    password_var: str = "TESTENCE_PASSWORD"
    extra: dict[str, Any] = field(default_factory=dict)
    #: Raw values read from .env files. Holds secrets, so it is excluded from
    #: describe() and must never be written to evidence.
    env_values: dict[str, str] = field(default_factory=dict, repr=False)

    @classmethod
    def load(cls, root: Path | str = ".", **overrides: Any) -> "Settings":
        root = Path(root)
        file_config = _load_settings_file(root)
        profiles = file_config.pop("profiles", {}) or {}

        file_env: dict[str, str] = {}
        for name in ENV_FILES:
            path = root / name
            if path.exists():
                file_env.update(_parse_env_file(path))
        env: dict[str, str] = dict(file_env)
        env.update({k: v for k, v in os.environ.items() if k.startswith(ENV_PREFIX)})

        profile = overrides.get("profile") or env.get(f"{ENV_PREFIX}PROFILE") or \
            file_config.get("profile", "")
        merged: dict[str, Any] = {k: v for k, v in file_config.items() if k != "profile"}
        if profile:
            if profile not in profiles:
                known = ", ".join(sorted(profiles)) or "none defined"
                raise ValueError(f"unknown profile {profile!r}; available: {known}")
            merged.update(profiles[profile])
            merged["profile"] = profile

        known_fields = {f for f in cls.__dataclass_fields__ if f != "extra"}
        extra: dict[str, Any] = dict(merged.pop("extra", {}) or {})
        for key, value in list(merged.items()):
            if key not in known_fields:
                extra[key] = merged.pop(key)

        for key, value in env.items():
            field_name = key[len(ENV_PREFIX):].lower()
            if field_name in known_fields:
                merged[field_name] = value

        merged.update({k: v for k, v in overrides.items() if v is not None})
        merged["extra"] = extra
        merged["env_values"] = file_env

        merged["headed"] = _as_bool(merged.get("headed", True))
        merged["verify_tls"] = _as_bool(merged.get("verify_tls", True))
        merged["timeout_ms"] = int(merged.get("timeout_ms", 10_000))
        if isinstance(merged.get("base_url"), str):
            merged["base_url"] = merged["base_url"].rstrip("/")
        return cls(**merged)

    def credentials(self):
        """Credentials for this profile, from the environment (never from files
        under version control)."""
        from testence.auth.base import Credentials

        return Credentials.from_env(self.user_var, self.password_var, self.env_values)

    def describe(self) -> dict[str, Any]:
        """Evidence-safe view: no credential values, ever."""
        return {
            "profile": self.profile or "(default)",
            "base_url": self.base_url,
            "auth": self.auth,
            "attach": bool(self.cdp_url),
            "browser_channel": self.browser_channel,
            "headed": self.headed,
            "verify_tls": self.verify_tls,
        }


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")
