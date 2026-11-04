"""Minimal JSON HTTP client that shares the browser's session.

Why not ``requests``/``httpx``: a dependency the framework does not need
(ADR-0007 keeps the runtime tree at two packages). This does exactly what oracles
and seeding need — JSON in, JSON out, with the browser's cookies and headers —
and nothing else.

Connections are kept alive: one per origin in a :class:`ConnectionPool`, so a test's
calls to one host share a TCP (and TLS) connection instead of opening one each. A
kept-alive connection the server closed while it sat idle is retried once on a new
connection; a connection that fails on its first use is an error.

The point is the *sharing*: an oracle must read the API as the same user the UI is
logged in as, or a divergence it reports is meaningless.

Inside a test every call is also evidence: an ``api.request`` event with the method,
URL, status, timing and bounded bodies, so a seed or an oracle read that went wrong
is visible in the ledger, the failure pack and the Allure step tree. Headers are never
recorded; bodies pass the run's redaction before they are clipped.
"""

from __future__ import annotations

import base64
import functools
import http.client
import json
import socket
import ssl
import threading
import time
import urllib.parse
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from ipaddress import ip_address
from typing import TYPE_CHECKING, Any, Callable, Iterable

from testence.auth.base import AuthContext

if TYPE_CHECKING:
    from testence.evidence import EvidenceWriter

_DEFAULT_TIMEOUT_S = 30.0

#: Receives one call's fields (``method``, ``url``, ``status`` or ``error``, ...).
Recorder = Callable[..., None]


@dataclass
class _Poll:
    calls: int = 0
    last: tuple[Recorder, dict[str, Any]] | None = None


_POLL: ContextVar[_Poll | None] = ContextVar("testence_api_poll", default=None)


@contextmanager
def polling() -> Iterator[None]:
    """Record a polling loop's calls as its first and its last, with ``attempts``.

    The last call is recorded when the loop ends, carrying how many calls the loop
    made; a loop that called once records that one call only.
    """
    poll = _Poll()
    token = _POLL.set(poll)
    try:
        yield
    finally:
        _POLL.reset(token)
        if poll.last is not None:
            recorder, fields = poll.last
            recorder(**fields, attempts=poll.calls)


#: Characters of one recorded body, after redaction. Enough to read an error answer
#: or a seeded entity; a full listing belongs in a file the test attaches itself.
BODY_LIMIT = 4_000

_TEXT_TYPES = ("json", "text/", "xml", "x-www-form-urlencoded", "javascript", "html")


class UnsafeRequestTarget(ValueError):
    """A request or redirect would leave the authenticated client's origin."""


def _normalized_host(host: str) -> str:
    """Normalize a URL hostname without making DNS-dependent trust decisions."""
    try:
        return ip_address(host).compressed.lower()
    except ValueError:
        try:
            return host.encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise UnsafeRequestTarget(f"invalid URL hostname {host!r}") from exc


def _origin(url: str) -> tuple[str, str, int]:
    """Return the origin tuple used for credential boundaries."""
    try:
        parsed = urllib.parse.urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise UnsafeRequestTarget(f"invalid request URL {url!r}: {exc}") from exc
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeRequestTarget(f"request URL must be absolute HTTP(S): {url!r}")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeRequestTarget("credentials in request URLs are not allowed")
    return scheme, _normalized_host(parsed.hostname), port or (443 if scheme == "https" else 80)


#: Redirects followed for one call, as urllib did.
_MAX_REDIRECTS = 10
_CONTENT_HEADERS = frozenset({"content-length", "content-type"})
#: The agent string urllib sent; kept so a server that filters clients sees no change.
_USER_AGENT = f"Python-urllib/{urllib.request.__version__}"  # type: ignore[attr-defined]
#: Errors of a kept-alive connection the server closed while it sat idle.
_STALE = (
    http.client.RemoteDisconnected,
    BrokenPipeError,
    ConnectionResetError,
    ConnectionAbortedError,
)


def _same_origin_redirect(method: str, url: str, status: int, location: str | None) -> str | None:
    """The method a 3xx answer is followed with, or None to return it as data.

    The policy of urllib's redirect handler, which this client replaced: GET and HEAD
    follow every redirect; POST follows 301, 302 and 303 as a GET without its body;
    any other answer, and any other method, goes back to the caller. A redirect to
    another origin is refused before anything is sent there.
    """
    if status not in (301, 302, 303, 307, 308) or not location:
        return None
    upper = method.upper()
    if upper in ("GET", "HEAD"):
        return upper
    if upper == "POST" and status in (301, 302, 303):
        return "GET"
    return None


def _redirect_target(url: str, location: str) -> str:
    target = urllib.parse.urljoin(url, location.strip())
    if _origin(target) != _origin(url):
        raise UnsafeRequestTarget(f"refusing cross-origin redirect from {url!r} to {target!r}")
    return target


@functools.lru_cache(maxsize=None)
def _cached_tls(verify_tls: bool, ca_bundle: str) -> ssl.SSLContext:
    """One TLS context per configuration for the process.

    A default context reads the system certificate store; on Windows that costs tens
    of milliseconds, which urllib paid on every request, plain HTTP included.
    """
    return tls_context(verify_tls, ca_bundle) or ssl.create_default_context()


@functools.lru_cache(maxsize=None)
def _proxies() -> dict[str, str]:
    """The proxies urllib would have used: the environment, then the system settings."""
    return dict(urllib.request.getproxies())


@functools.lru_cache(maxsize=256)
def _proxy_for(scheme: str, host: str) -> str:
    proxy = _proxies().get(scheme, "")
    if not proxy:
        return ""
    try:
        if urllib.request.proxy_bypass(host):  # type: ignore[attr-defined]
            return ""
    except OSError:
        pass
    return proxy if "://" in proxy else f"http://{proxy}"


def _proxy_authorization(proxy: str) -> str:
    parsed = urllib.parse.urlsplit(proxy)
    user = urllib.parse.unquote(parsed.username or "")
    password = urllib.parse.unquote(parsed.password or "")
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


class ConnectionPool:
    """Kept-alive HTTP connections: at most one idle connection per origin.

    Thread-safe by checkout: a call takes the idle connection of its origin, or opens
    one, and puts it back once the answer is read, so two concurrent calls never share
    a socket. ``close()`` closes the idle connections; the pool stays usable and opens
    new ones on demand.
    """

    def __init__(self) -> None:
        self._idle: dict[tuple[Any, ...], http.client.HTTPConnection] = {}
        self._lock = threading.Lock()
        #: Connections this pool opened, for diagnostics and tests.
        self.opened = 0

    def close(self) -> None:
        with self._lock:
            idle, self._idle = list(self._idle.values()), {}
        for connection in idle:
            connection.close()

    def __enter__(self) -> ConnectionPool:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _connect(
        self, scheme: str, host: str, port: int, proxy: str, context: ssl.SSLContext | None
    ) -> http.client.HTTPConnection:
        connection: http.client.HTTPConnection
        if proxy:
            parsed = urllib.parse.urlsplit(proxy)
            proxy_host, proxy_port = parsed.hostname or "", parsed.port or 80
            if scheme == "https":
                connection = http.client.HTTPSConnection(proxy_host, proxy_port, context=context)
                tunnel = {}
                if parsed.username is not None:
                    tunnel["Proxy-Authorization"] = _proxy_authorization(proxy)
                connection.set_tunnel(host, port, headers=tunnel)
            else:
                connection = http.client.HTTPConnection(proxy_host, proxy_port)
        elif scheme == "https":
            connection = http.client.HTTPSConnection(host, port, context=context)
        else:
            connection = http.client.HTTPConnection(host, port)
        self.opened += 1
        return connection

    def send(
        self,
        method: str,
        url: str,
        *,
        data: bytes | None,
        headers: dict[str, str],
        timeout_s: float,
        verify_tls: bool = True,
        ca_bundle: str = "",
    ) -> tuple[int, list[tuple[str, str]], bytes]:
        """One exchange on a kept-alive connection; redirects are the caller's."""
        parsed = urllib.parse.urlsplit(url)
        scheme, host, port = _origin(url)
        hostname = parsed.hostname or host
        context = _cached_tls(verify_tls, ca_bundle) if scheme == "https" else None
        proxy = _proxy_for(scheme, hostname)
        key = (scheme, host, port, verify_tls, ca_bundle, proxy)
        path = parsed.path or "/"
        target = urllib.parse.urlunsplit(("", "", path, parsed.query, ""))
        request_headers = {"User-Agent": _USER_AGENT, **headers}
        if proxy and scheme == "http":
            # A plain-HTTP proxy is sent the absolute URL; HTTPS goes through a tunnel.
            target = urllib.parse.urlunsplit((scheme, parsed.netloc, path, parsed.query, ""))
            if urllib.parse.urlsplit(proxy).username is not None:
                request_headers["Proxy-Authorization"] = _proxy_authorization(proxy)
        with self._lock:
            connection = self._idle.pop(key, None)
        reused = connection is not None
        if connection is None:
            connection = self._connect(scheme, hostname, port, proxy, context)
        while True:
            try:
                connection.timeout = timeout_s
                if connection.sock is not None:
                    connection.sock.settimeout(timeout_s)
                connection.request(method, target, body=data, headers=request_headers)
                answer = connection.getresponse()
                body = answer.read()
            except _STALE:
                connection.close()
                if not reused:
                    raise
                # The server closed the connection while it was idle: the request never
                # reached the application, so it goes once more on a new connection.
                connection = self._connect(scheme, hostname, port, proxy, context)
                reused = False
                continue
            except BaseException:
                connection.close()
                raise
            break
        keep: http.client.HTTPConnection | None = None if answer.will_close else connection
        if keep is not None:
            with self._lock:
                if key not in self._idle:
                    self._idle[key] = keep
                    keep = None
        if keep is not None or answer.will_close:
            connection.close()
        return answer.status, list(answer.getheaders()), body


#: The pool of module-level calls (logins, identity probes) for the process.
_SHARED_POOL = ConnectionPool()


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
    pool: ConnectionPool | None = None,
) -> Response:
    """One request, no session. Building block for the auth strategies.

    4xx and 5xx answers are data, not exceptions. Redirects are followed only while
    they stay on the origin of ``url``. Without a ``pool`` the call uses the shared
    pool of the process.
    """
    from testence.auth.strategies import parse_set_cookie

    data = None
    request_headers = {"Accept": "application/json", **(headers or {})}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")

    _origin(url)  # reject non-HTTP targets and URL userinfo before opening a socket
    connections = pool if pool is not None else _SHARED_POOL
    current_method, current_url = method.upper(), url
    for _ in range(_MAX_REDIRECTS + 1):
        try:
            status, answer_headers, raw = connections.send(
                current_method,
                current_url,
                data=data,
                headers=request_headers,
                timeout_s=timeout_s,
                verify_tls=verify_tls,
                ca_bundle=ca_bundle,
            )
        except socket.timeout as exc:
            raise TimeoutError(
                f"{current_method} {current_url}: no answer in {timeout_s} s"
            ) from exc
        location = next((v for k, v in answer_headers if k.lower() == "location"), None)
        follow = _same_origin_redirect(current_method, current_url, status, location)
        if follow is None or location is None:
            break
        current_url = _redirect_target(current_url, location)
        if follow != current_method:
            # A POST answered with 301-303 is followed as a GET without its body.
            data = None
            request_headers = {
                k: v for k, v in request_headers.items() if k.lower() not in _CONTENT_HEADERS
            }
        current_method = follow
    else:
        raise RuntimeError(f"{method} {url}: more than {_MAX_REDIRECTS} redirects")
    response = Response(status, answer_headers, raw.decode("utf-8", "replace"))
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
        allowed_origins: Iterable[str] = (),
        recorder: Recorder | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        #: Called once per request with what to record; ``None`` outside a test.
        self.recorder = recorder
        self._allowed_origins = {_origin(self.base_url)}
        if isinstance(allowed_origins, str):
            allowed_origins = [allowed_origins]
        self._allowed_origins.update(_origin(url) for url in allowed_origins)
        self.auth = auth or AuthContext()
        self.verify_tls = verify_tls
        self.ca_bundle = ca_bundle
        self.timeout_s = timeout_s
        #: This client's kept-alive connections; ``close()`` releases them.
        self.pool = ConnectionPool()

    def close(self) -> None:
        """Close the client's connections; a later call opens new ones."""
        self.pool.close()

    def __enter__(self) -> ApiClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @classmethod
    def from_settings(
        cls, settings: Any, auth: AuthContext | None = None, *, recorder: Recorder | None = None
    ) -> "ApiClient":
        allowed_origins = (getattr(settings, "extra", {}) or {}).get("api_allowed_origins") or []
        if isinstance(allowed_origins, str):
            allowed_origins = [allowed_origins]
        return cls(
            settings.base_url,
            auth,
            verify_tls=settings.verify_tls,
            ca_bundle=settings.ca_bundle,
            allowed_origins=allowed_origins,
            recorder=recorder,
        )

    def request(
        self, method: str, path: str, body: Any = None, headers: dict[str, str] | None = None
    ) -> Response:
        url = self._resolve_url(path)
        merged = dict(self.auth.headers)
        cookie_header = self.auth.cookie_header(url)
        if cookie_header:
            merged["Cookie"] = cookie_header
        merged.update(headers or {})
        started = time.perf_counter()
        try:
            response = http_json(
                method,
                url,
                body=body,
                headers=merged,
                timeout_s=self.timeout_s,
                verify_tls=self.verify_tls,
                ca_bundle=self.ca_bundle,
                pool=self.pool,
            )
        except Exception as exc:
            # A refused connection or a timeout is the call a failed seed most needs
            # on record; the exception still reaches the test unchanged.
            self._record(method, url, body, started, error=exc)
            raise
        self._record(method, url, body, started, response=response)
        return response

    def _record(
        self,
        method: str,
        url: str,
        body: Any,
        started: float,
        *,
        response: Response | None = None,
        error: BaseException | None = None,
    ) -> None:
        if self.recorder is None:
            return
        fields: dict[str, Any] = {
            "method": method.upper(),
            "url": url,
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            "request": {"body": body},
        }
        if response is not None:
            content_type = response.header("Content-Type") or ""
            answer: dict[str, Any] = {
                "content_type": content_type,
                "bytes": len(response.body.encode("utf-8")),
            }
            if not response.body:
                answer["body"] = None
            elif any(kind in content_type.lower() for kind in _TEXT_TYPES) or not content_type:
                parsed = response.json if "json" in content_type.lower() else None
                answer["body"] = parsed if parsed is not None else response.body
            else:
                # Decoded with replacement characters, a binary body is noise that
                # only costs budget; its size and type say what came back.
                answer["body"] = None
                answer["omitted"] = "binary"
            fields["status"] = response.status
            fields["response"] = answer
        else:
            fields["error"] = f"{type(error).__name__}: {error}"
        poll = _POLL.get()
        if poll is not None:
            poll.calls += 1
            if poll.calls > 1:
                poll.last = (self.recorder, fields)
                return
        self.recorder(**fields)

    def _resolve_url(self, path: str) -> str:
        """Resolve a client path and enforce the credential-bearing origin."""
        parsed = urllib.parse.urlsplit(path)
        if parsed.scheme or parsed.netloc:
            url = path
        elif path.startswith(("?", "#")):
            url = f"{self.base_url}{path}"
        else:
            url = f"{self.base_url}/{path.lstrip('/')}"
        if _origin(url) not in self._allowed_origins:
            raise UnsafeRequestTarget(
                f"authenticated API client for {self.base_url!r} cannot request {url!r}"
            )
        return url

    def get(self, path: str, **kw: Any) -> Response:
        return self.request("GET", path, **kw)

    def get_fresh(self, path: str, **kw: Any) -> Response:
        """Make an authoritative read after a mutation, bypassing HTTP caches."""
        headers = dict(kw.pop("headers", None) or {})
        headers.update({"Cache-Control": "no-cache", "Pragma": "no-cache"})
        return self.request("GET", path, headers=headers, **kw)

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
            raise AssertionError(f"expected 404 after delete at {path}, got {response.status}")


def evidence_recorder(writer: EvidenceWriter, test_id: str, *, role: str | None = None) -> Recorder:
    """Record each call of a test's client as an ``api.request`` event.

    Bodies are redacted with the run's policy first and clipped second, so a secret
    can never survive by sitting past the cut. A body that is still structured after
    redaction stays a JSON value; one too long for ``BODY_LIMIT`` becomes clipped text.
    """

    def bounded(value: Any) -> Any:
        if value is None:
            return None
        safe = writer.sanitized(value, limit=BODY_LIMIT)
        text = safe if isinstance(safe, str) else json.dumps(safe, ensure_ascii=False)
        if len(text) <= BODY_LIMIT:
            return safe
        return writer.sanitized(text, limit=BODY_LIMIT)

    def record(**fields: Any) -> None:
        for part in ("request", "response"):
            section = fields.get(part)
            if isinstance(section, dict) and "body" in section:
                section["body"] = bounded(section["body"])
        if role:
            fields["role"] = role
        writer.emit("api.request", test=test_id, **fields)

    return record
