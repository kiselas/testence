"""Minimal JSON HTTP client that shares the browser's session.

Why not ``requests``/``httpx``: a dependency the framework does not need
(ADR-0007 keeps the runtime tree at two packages). This does exactly what oracles
and seeding need — JSON in, JSON out, with the browser's cookies and headers —
and nothing else.

The point is the *sharing*: an oracle must read the API as the same user the UI is
logged in as, or a divergence it reports is meaningless.
"""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from testence.auth.base import AuthContext

_DEFAULT_TIMEOUT_S = 30.0


@dataclass
class Response:
    status: int
    headers: list[tuple[str, str]]
    body: str
    cookies: dict[str, str] = field(default_factory=dict)

    @property
    def json(self) -> Any:
        if not self.body:
            return None
        try:
            return json.loads(self.body)
        except json.JSONDecodeError:
            return None

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    def header(self, name: str) -> str | None:
        """Case-insensitive header lookup. Paged list endpoints carry their true
        total in a header (x-total-count), which is what a UI counter must match."""
        wanted = name.lower()
        for key, value in self.headers:
            if key.lower() == wanted:
                return value
        return None

    def raise_for_status(self) -> "Response":
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status}: {self.body[:500]}")
        return self


def tls_context(verify_tls: bool = True, ca_bundle: str = "") -> ssl.SSLContext | None:
    """TLS setup for a target whose certificate the browser trusts but Python may not.

    Preference order: a named private CA bundle (keeps verification on), then the
    default bundle, then — only when explicitly asked — no verification at all.
    """
    if ca_bundle:
        return ssl.create_default_context(cafile=ca_bundle)
    if verify_tls:
        return None
    return ssl._create_unverified_context()


def http_json(
    method: str,
    url: str,
    *,
    body: Any = None,
    headers: dict[str, str] | None = None,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
    verify_tls: bool = True,
    ca_bundle: str = "",
) -> Response:
    """One request, no session. Building block for the auth strategies."""
    from testence.auth.strategies import parse_set_cookie

    data = None
    request_headers = {"Accept": "application/json", **(headers or {})}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")

    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    context = tls_context(verify_tls, ca_bundle)
    try:
        with urllib.request.urlopen(request, timeout=timeout_s, context=context) as raw:
            response = Response(raw.status, list(raw.headers.items()),
                                raw.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:  # 4xx/5xx are data, not exceptions
        response = Response(exc.code, list(exc.headers.items()),
                            exc.read().decode("utf-8", "replace"))
    response.cookies = parse_set_cookie(response.headers)
    return response


class ApiClient:
    """Session-carrying client for oracles, seeding and preconditions."""

    def __init__(
        self,
        base_url: str,
        auth: AuthContext | None = None,
        *,
        verify_tls: bool = True,
        ca_bundle: str = "",
        timeout_s: float = _DEFAULT_TIMEOUT_S,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.auth = auth or AuthContext()
        self.verify_tls = verify_tls
        self.ca_bundle = ca_bundle
        self.timeout_s = timeout_s

    @classmethod
    def from_settings(cls, settings: Any, auth: AuthContext | None = None) -> "ApiClient":
        return cls(settings.base_url, auth, verify_tls=settings.verify_tls,
                   ca_bundle=settings.ca_bundle)

    def request(self, method: str, path: str, body: Any = None,
                headers: dict[str, str] | None = None) -> Response:
        merged = dict(self.auth.headers)
        cookie_header = self.auth.cookie_header()
        if cookie_header:
            merged["Cookie"] = cookie_header
        merged.update(headers or {})
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        return http_json(method, url, body=body, headers=merged,
                         timeout_s=self.timeout_s, verify_tls=self.verify_tls,
                         ca_bundle=self.ca_bundle)

    def get(self, path: str, **kw: Any) -> Response:
        return self.request("GET", path, **kw)

    def post(self, path: str, body: Any = None, **kw: Any) -> Response:
        return self.request("POST", path, body=body, **kw)

    def patch(self, path: str, body: Any = None, **kw: Any) -> Response:
        return self.request("PATCH", path, body=body, **kw)

    def delete(self, path: str, **kw: Any) -> Response:
        return self.request("DELETE", path, **kw)

    def get_list(self, path: str, **kw: Any) -> list[Any]:
        """GET a collection, insisting the response really is one.

        Guards a mistake that is easy to make and hard to see: a 404 body is a JSON
        *object*, so ``len(response.json)`` on it returns 1 and reads as "one item
        found". Discovered while writing a suite against a route that did not
        exist — the probe reported a host that was never there.
        """
        response = self.get(path, **kw)
        if not response.ok:
            raise AssertionError(
                f"GET {path} returned HTTP {response.status}, expected a collection: "
                f"{(response.body or '')[:200]}"
            )
        body = response.json
        if not isinstance(body, list):
            raise AssertionError(
                f"GET {path} returned {type(body).__name__}, expected a list "
                f"(body: {(response.body or '')[:200]})"
            )
        return body

    def assert_absent(self, path: str) -> None:
        """Cleanup verification: the entity must really be gone (404), not merely
        'delete returned 200' — the discipline that keeps shared stands clean."""
        response = self.get(path)
        if response.status != 404:
            raise AssertionError(
                f"expected 404 after delete at {path}, got {response.status}"
            )
