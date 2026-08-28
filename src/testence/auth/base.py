"""Authentication contracts: credentials in, a propagatable session out.

Two ideas carry the whole design:

1. **The browser is the session's home.** Whatever the scheme (cookie, bearer token,
   basic), the browser context is authenticated first; everything else — API oracles,
   seeding calls — *inherits* from it via :class:`AuthContext`. One session, two
   consumers, so an oracle can never accidentally read a different user's view than
   the UI does.
2. **Credentials are configuration, never code.** They arrive from the environment or
   an untracked local file. No credential value belongs in this repository, in a
   project's test code, or in an evidence artifact — see ``redacted()``.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from testence.engine import Engine


class MissingCredentials(RuntimeError):
    """Raised with the exact variable names to set — an error a reader can act on."""


@dataclass(frozen=True)
class Credentials:
    username: str
    password: str
    source: str = "explicit"

    @classmethod
    def from_env(
        cls,
        user_var: str = "TESTENCE_USER",
        password_var: str = "TESTENCE_PASSWORD",
        lookup: Mapping[str, str] | None = None,
    ) -> "Credentials":
        """Read credentials from the process environment, falling back to ``lookup``
        (the values Settings read from ``.env`` files) so that one file can hold the
        whole configuration — target and credentials together."""
        source = "env"
        username = os.environ.get(user_var) or (lookup or {}).get(user_var, "")
        password = os.environ.get(password_var) or (lookup or {}).get(password_var, "")
        if lookup and user_var not in os.environ and user_var in lookup:
            source = "env-file"
        if not username or not password:
            raise MissingCredentials(
                f"set {user_var} and {password_var} in the environment or in a local "
                f"untracked .env / .env.local — credentials are never stored in code"
            )
        return cls(username=username, password=password, source=f"{source}:{user_var}")

    def redacted(self) -> dict[str, str]:
        """What may appear in logs, evidence packs and reports."""
        return {"username": self.username, "password": "***", "source": self.source}

    def __repr__(self) -> str:  # keeps secrets out of tracebacks and pytest output
        return f"Credentials(username={self.username!r}, password='***')"


@dataclass
class AuthContext:
    """The authenticated session, in a form other clients can reuse."""

    cookies: list[dict[str, Any]] = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)
    storage: dict[str, str] = field(default_factory=dict)
    user: dict[str, Any] | None = None
    scheme: str = "unknown"

    def cookie_header(self) -> str:
        """``Cookie:`` header value for plain HTTP clients."""
        return "; ".join(f"{c['name']}={c['value']}" for c in self.cookies)

    def describe(self) -> dict[str, Any]:
        """Evidence-safe summary: names only, no values. A failed run must show
        *whether* it was authenticated without leaking how."""
        return {
            "scheme": self.scheme,
            "cookies": sorted(c["name"] for c in self.cookies),
            "headers": sorted(self.headers),
            "storage_keys": sorted(self.storage),
            "user": self.user,
        }


class AuthAdapter(Protocol):
    """A login strategy. Implementations must be idempotent: calling twice on an
    already-authenticated engine is allowed and must not fail."""

    scheme: str

    def authenticate(self, engine: Engine) -> AuthContext:
        """Leave ``engine``'s browser authenticated; return the reusable session."""
        ...
