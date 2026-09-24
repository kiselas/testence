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
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from testence.engine.protocol import Target
    from testence.evidence.sanitize import RedactionPolicy

ENV_PREFIX = "TESTENCE_"
SETTINGS_FILES = ("testence.toml", "testence.json")
ENV_FILES = (".env", ".env.local")


def default_browser_channel() -> str:
    """Browser channel when nothing names one explicitly.

    ``TESTENCE_BROWSER_CHANNEL`` is the same variable ``Settings.load`` merges, so a
    directly constructed ``Settings(...)`` or ``PlaywrightCdpEngine(...)`` agrees with
    the loaded one. A host whose bundled Chromium cannot start can point every path at
    ``msedge`` or ``chromium-headless-shell`` here; unset or empty keeps ``chromium``.
    """
    return os.environ.get(f"{ENV_PREFIX}BROWSER_CHANNEL", "").strip() or "chromium"


class SettingsError(RuntimeError):
    """A settings file exists but cannot be read.

    ``RuntimeError`` on purpose: every caller that already reports a runtime failure
    keeps working, and the message stays the actionable part of the report.
    """


def _default_project_id(root: Path) -> str:
    """Best-effort stable namespace for projects that have not opted in explicitly."""

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            section = pyproject.read_text(encoding="utf-8").split("[project]", 1)[1]
            section = section.split("\n[", 1)[0]
            match = re.search(r'^name\s*=\s*["\']([^"\']+)["\']', section, re.MULTILINE)
            if match:
                value = re.sub(r"[^a-z0-9._-]+", "-", match.group(1).lower()).strip("-._")
                if value:
                    return value[:128]
        except (OSError, IndexError):
            pass
    return "unconfigured"


def _parse_env_file(path: Path) -> dict[str, str]:
    """Minimal KEY=VALUE parser: ``#`` comments, optional ``export``, quoted values.

    ``utf-8-sig`` because a Windows editor writes a byte-order mark by default. Read as
    plain ``utf-8`` the mark stays glued to the first key, so ``TESTENCE_USER`` silently
    never arrives and the run fails with "set TESTENCE_USER" while the file visibly
    contains it.
    """

    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
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
            try:
                return json.loads(path.read_text(encoding="utf-8-sig"))
            except json.JSONDecodeError as exc:
                # A typo in the settings file is a configuration problem, not a
                # traceback: name the file and the position the parser stopped at.
                raise SettingsError(
                    f"{path} is not valid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})"
                ) from exc
        try:
            import tomllib
        except ModuleNotFoundError:  # Python 3.10: TOML needs 3.11+
            raise RuntimeError(
                f"{name} needs Python 3.11+ for tomllib; use testence.json instead"
            ) from None
        try:
            return tomllib.loads(path.read_text(encoding="utf-8-sig"))
        except tomllib.TOMLDecodeError as exc:
            raise SettingsError(f"{path} is not valid TOML: {exc}") from exc
    return {}


@dataclass
class Settings:
    """Resolved configuration for one run."""

    base_url: str = ""
    project_id: str = ""
    api_prefix: str = "/api/"
    auth: str = "none"
    login_path: str = "/login"
    api_login_path: str = ""
    cdp_url: str | None = None
    execution_mode: str = "isolated"
    # Use the browser revision shipped with this Playwright release instead of a
    # machine-wide Chrome install. ``chromium`` also selects Playwright's regular
    # Chromium in headless mode, keeping headed and CI runs on the same engine.
    # ``TESTENCE_BROWSER_CHANNEL`` moves one host elsewhere (see default_browser_channel).
    browser_channel: str = field(default_factory=default_browser_channel)
    debug_port: int = 9222
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

        profile = (
            overrides.get("profile")
            or env.get(f"{ENV_PREFIX}PROFILE")
            or file_config.get("profile", "")
        )
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
            field_name = key[len(ENV_PREFIX) :].lower()
            if field_name in known_fields:
                merged[field_name] = value

        merged.update({k: v for k, v in overrides.items() if v is not None})
        merged["extra"] = extra
        merged["env_values"] = file_env

        merged["headed"] = _as_bool(merged.get("headed", True))
        merged["verify_tls"] = _as_bool(merged.get("verify_tls", True))
        merged["timeout_ms"] = int(merged.get("timeout_ms", 10_000))
        merged["debug_port"] = int(merged.get("debug_port", 9222))
        if merged["debug_port"] != 0 and not 1024 <= merged["debug_port"] <= 65535:
            raise ValueError("debug_port must be 0 (ephemeral) or between 1024 and 65535")
        if not str(merged.get("browser_channel") or "").strip():
            # An empty TESTENCE_BROWSER_CHANNEL means "nothing chosen here", which is
            # how a .env line left blank reads. Keep the packaged default instead of
            # handing an empty channel to the browser.
            merged["browser_channel"] = default_browser_channel()
        merged["execution_mode"] = str(merged.get("execution_mode", "isolated")).lower()
        if merged["execution_mode"] not in {"isolated", "warm", "attached"}:
            raise ValueError("execution_mode must be isolated, warm, or attached")
        if merged.get("cdp_url"):
            merged["execution_mode"] = "attached"
        if isinstance(merged.get("base_url"), str):
            merged["base_url"] = merged["base_url"].rstrip("/")
        if not str(merged.get("project_id") or "").strip():
            merged["project_id"] = _default_project_id(root.resolve())
        from testence.identity import validate_identity

        merged["project_id"] = validate_identity(str(merged["project_id"]), "project_id")
        return cls(**merged)

    def credentials(self):
        """Credentials for this profile, from the environment (never from files
        under version control)."""
        from testence.auth.base import Credentials

        return Credentials.from_env(self.user_var, self.password_var, self.env_values)

    def describe(self) -> dict[str, Any]:
        """Evidence-safe view: no credential values, ever."""
        return {
            "project_id": self.project_id,
            "profile": self.profile or "(default)",
            "base_url": self.base_url,
            "auth": self.auth,
            "attach": bool(self.cdp_url),
            "execution_mode": self.execution_mode,
            "browser_channel": self.browser_channel,
            "debug_port": self.debug_port,
            "headed": self.headed,
            "verify_tls": self.verify_tls,
            # Device, locale and the rest change what the page renders; a result is
            # only comparable with runs that emulated the same.
            **({"emulation": self.extra["emulation"]} if self.extra.get("emulation") else {}),
        }

    def evidence_config(self) -> dict[str, Any]:
        """The ``evidence`` object of the settings file (redaction, masks)."""
        value = self.extra.get("evidence", {}) or {}
        if not isinstance(value, dict):
            raise ValueError("evidence must be an object")
        unknown = sorted(set(value) - {"redact", "mask", "screenshots"})
        if unknown:
            raise ValueError("unknown evidence field(s): " + ", ".join(unknown))
        if value.get("screenshots", "on-failure") not in ("on-failure", "always"):
            raise ValueError("evidence.screenshots must be on-failure or always")
        return value

    def redaction_policy(self) -> RedactionPolicy:
        """Project additions to built-in redaction, as names only (ADR-0024)."""
        from testence.evidence.sanitize import RedactionPolicy

        return RedactionPolicy.from_config(self.evidence_config().get("redact"))

    def redaction_values(self) -> tuple[str, ...]:
        """Secret values redacted wherever they appear: the login pair plus
        ``evidence.redact.env``. Never written anywhere; only used to replace."""
        redact = self.evidence_config().get("redact") or {}
        names = redact.get("env", []) if isinstance(redact, dict) else []
        if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
            raise ValueError("evidence.redact.env must be a list of variable names")
        values: list[str] = []
        for variable in (self.user_var, self.password_var, *names):
            value = os.environ.get(variable) or self.env_values.get(variable)
            if value:
                values.append(value)
        return tuple(values)

    def screenshot_masks(self) -> tuple[Target, ...]:
        """Elements painted over in every screenshot (``evidence.mask``)."""
        from testence.engine.protocol import Target

        raw = self.evidence_config().get("mask", [])
        if not isinstance(raw, list):
            raise ValueError("evidence.mask must be a list of targets")
        masks: list[Target] = []
        for index, spec in enumerate(raw):
            if not isinstance(spec, dict) or set(spec) - {"kind", "value", "name", "nth"}:
                raise ValueError(
                    f"evidence.mask[{index}] must be an object with kind, value and "
                    "optional name, nth"
                )
            try:
                masks.append(
                    Target(
                        kind=str(spec.get("kind", "")),
                        value=str(spec.get("value", "")),
                        name=spec.get("name"),
                        nth=spec.get("nth"),
                    )
                )
            except ValueError as exc:
                raise ValueError(f"evidence.mask[{index}]: {exc}") from exc
        return tuple(masks)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")
