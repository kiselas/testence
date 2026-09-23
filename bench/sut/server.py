"""The benchmark target: one process, static bundle plus stub API.

Why a Python server in front of a React bundle, rather than a node one:

- a benchmark run must not need a node toolchain. Node builds the bundle once, at
  development time; running the corpus needs only what the framework already needs
  (ADR-0007 keeps the runtime dependency surface small on purpose);
- the *same* process serves the page and answers its API, which is what lets one
  defect flag break the client and the server at once. Sixteen of the forty corpus
  items are defined by those two disagreeing, so this is not a convenience.

**How a defect reaches both halves.** The page is opened with `?defects=D-40,D-45`.
The client parses that, applies its own halves, and echoes the same list back in an
`X-Defects` header on every API call. The server applies the halves marked
`server`. One id, two layers, one configuration — and a corpus item that seeds one
cause and expects symptoms on two screens needs nothing more.

**Unknown ids are refused, loudly.** A corpus item that misspells a flag must not
quietly run against a healthy application and report a pass: that would be a false
green manufactured by the benchmark itself, which is the one failure mode this
whole exercise exists to measure. Both the server and the client reject an id that
is not in `defects.json`.

    python bench/sut/server.py --port 8800

Threading is deliberate: two concurrent sessions on one object are a corpus item,
and a deliberately slowed response must not block the other session's requests.
"""

from __future__ import annotations

import argparse
import json
import re
import socketserver
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).parent
STATIC = ROOT / "static"
REGISTRY = json.loads((ROOT / "defects.json").read_text(encoding="utf-8"))
KNOWN: dict[str, dict] = REGISTRY["defects"]

PAGE_SIZE = 10

#: Fixed vocabulary. Row content is generated from it by index, never randomly:
#: a corpus item has to mean the same thing on every run, and `Math.random` in a
#: fixture is how a benchmark acquires its own flake rate.
_NAMES = [
    "alpha",
    "beacon",
    "cascade",
    "delta",
    "ember",
    "fathom",
    "gantry",
    "harbor",
    "indigo",
    "jetty",
    "kestrel",
    "lantern",
    "marlin",
    "nimbus",
    "onyx",
    "pillar",
    "quarry",
    "ravine",
    "summit",
    "tundra",
    "umber",
    "vessel",
    "willow",
    "xenon",
    "yarrow",
    "zephyr",
]
_OWNERS = ["ap", "bd", "cf", "dh", "ek"]
_STATUSES = ["draft", "published", "archived"]
_EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _seed_rows() -> list[dict]:
    """47 rows: enough for four pages with a ragged last one.

    Row 7 and row 23 are soft-deleted from the start. They exist so that "a deleted
    row is still listed" is a *state* the corpus can assert against, rather than
    something a test has to create first — a precondition seeded through the API is
    cheaper and, more importantly, cannot fail halfway.
    """
    rows = []
    for index in range(47):
        rows.append(
            {
                "id": f"row-{index:03d}",
                "name": f"{_NAMES[index % len(_NAMES)]}-{index:02d}",
                "owner": _OWNERS[index % len(_OWNERS)],
                "status": _STATUSES[index % len(_STATUSES)],
                "updatedAt": (_EPOCH + timedelta(hours=index * 7)).isoformat(),
                "deleted": index in (7, 23),
            }
        )
    return rows


class Store:
    """In-memory rows, reset per process. Guarded because sessions run concurrently."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._rows = _seed_rows()

    def all(self) -> list[dict]:
        with self._lock:
            return [dict(row) for row in self._rows]

    def add(self, name: str, owner: str, status: str) -> dict:
        with self._lock:
            row = {
                "id": f"row-{len(self._rows):03d}",
                "name": name,
                "owner": owner,
                "status": status,
                # Derived from position, not from the clock: a wall-clock value would
                # differ between runs and make evidence packs incomparable.
                "updatedAt": (_EPOCH + timedelta(hours=len(self._rows) * 7)).isoformat(),
                "deleted": False,
            }
            self._rows.append(row)
            return dict(row)


#: One store per run id, created on first use.
#:
#: Found by verifying the fixture rather than by design: a case that created a row
#: moved the baseline for every case after it, and five later checks failed against
#: a total that was correct a moment earlier. The synthetic target deliberately
#: reproduces this shared-state hazard: a corpus whose items contaminate each other
#: measures the order they ran in.
#:
#: Keying by run id rather than resetting between items also buys the isolation a
#: parallel run needs: sixty items times their repeats is not a serial workload.
_STORES: dict[str, Store] = {}
_STORES_LOCK = Lock()


def store_for(run: str) -> Store:
    with _STORES_LOCK:
        if run not in _STORES:
            _STORES[run] = Store()
        return _STORES[run]


class UnknownDefect(ValueError):
    pass


def parse_defects(raw: str | None) -> set[str]:
    """Parse a defect list, refusing anything not in the registry."""
    if not raw:
        return set()
    ids = {part.strip() for part in raw.split(",") if part.strip()}
    unknown = sorted(ids - set(KNOWN))
    if unknown:
        raise UnknownDefect(f"unknown defect id(s): {', '.join(unknown)}")
    return ids


def collection(store: Store, params: dict[str, list[str]], on: set[str]) -> dict:
    """The collection endpoint, with its server-half defects applied.

    Each branch below is one corpus item. They are written as the smallest possible
    departure from the correct line, because a defect that also changes the shape of
    the response is easier to spot than the real thing ever is.
    """
    rows = store.all()

    # D-17: the correct line filters soft-deleted rows out of every listing.
    if "D-17" not in on:
        rows = [row for row in rows if not row["deleted"]]

    search = (params.get("search") or [""])[0].strip().lower()
    if search:
        if "D-44" in on:
            # D-44: prefix instead of substring. Narrower than documented, and it
            # still returns results, so the failure looks like bad test data.
            rows = [row for row in rows if row["name"].lower().startswith(search)]
        else:
            rows = [row for row in rows if search in row["name"].lower()]

    status = (params.get("status") or [""])[0].strip()
    # D-45: the parameter arrives and is dropped. The request in the network log
    # carries the filter, which is what makes this one worth having.
    if status and "D-45" not in on:
        rows = [row for row in rows if row["status"] == status]

    sort = (params.get("sort") or ["name"])[0]
    reverse = sort.startswith("-")
    key = sort.lstrip("-")
    if key in ("name", "owner", "status", "updatedAt"):
        rows.sort(key=lambda row: row[key], reverse=reverse)

    total = len(rows)
    page = max(1, int((params.get("page") or ["1"])[0] or 1))
    start = (page - 1) * PAGE_SIZE
    window = rows[start : start + PAGE_SIZE]

    # D-43-short-page: one row is dropped from the window and the total still counts
    # it. An assertion on the first row passes; only comparing the window against
    # the total catches it.
    if "D-43-short-page" in on and window:
        window = window[:-1]

    # D-43-counter: the heading disagrees with what the collection actually holds.
    # The offset is 3 rather than 2 on purpose: with 2 the reported number lands
    # exactly on the count including soft-deleted rows, i.e. on D-17's observable
    # state. Two different defects that produce one identical observation are a
    # corpus defect — the set could no longer tell which one it had seeded.
    reported = total + 3 if "D-43-counter" in on else total
    return {"total": reported, "page": page, "pageSize": PAGE_SIZE, "rows": window}


class Handler(BaseHTTPRequestHandler):
    server_version = "testence-sut/0"

    def log_message(self, fmt: str, *args) -> None:  # noqa: A002 - stdlib signature
        pass  # the runner reads the browser's network log, not this one

    # -- plumbing ---------------------------------------------------------

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, doc: dict) -> None:
        self._send(code, json.dumps(doc).encode("utf-8"), "application/json")

    def _defects(self) -> set[str]:
        return parse_defects(self.headers.get("X-Defects"))

    def _store(self) -> Store:
        """The store this run owns. Absent header means the shared default."""
        return store_for(self.headers.get("X-Run") or "default")

    # -- routing ----------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 - stdlib signature
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._api_get(parsed.path, parse_qs(parsed.query))
            return
        self._static(parsed.path)

    def do_POST(self) -> None:  # noqa: N802 - stdlib signature
        parsed = urlparse(self.path)
        if parsed.path != "/api/rows":
            self._json(404, {"error": "not found"})
            return
        try:
            on = self._defects()
        except UnknownDefect as exc:
            self._json(400, {"error": str(exc)})
            return
        if "C-10" in on:
            time.sleep(0.3)
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length) or b"{}")
        name = str(payload.get("name") or "").strip()
        if not name:
            self._json(422, {"error": "NAME_REQUIRED", "field": "name"})
            return
        row = self._store().add(
            name, str(payload.get("owner") or "ap"), str(payload.get("status") or "draft")
        )
        self._json(201, row)

    def _api_get(self, path: str, params: dict[str, list[str]]) -> None:
        try:
            on = self._defects()
        except UnknownDefect as exc:
            self._json(400, {"error": str(exc)})
            return
        if "C-10" in on:
            time.sleep(0.3)
        if path == "/api/rows":
            self._json(200, collection(self._store(), params, on))
        elif path == "/api/defects":
            self._json(200, REGISTRY)
        else:
            self._json(404, {"error": "not found"})

    def _static(self, path: str) -> None:
        """Serve the bundle, falling back to index.html so client routes resolve."""
        rel = path.lstrip("/") or "index.html"
        if not re.fullmatch(r"[A-Za-z0-9._/-]*", rel) or ".." in rel:
            self._json(400, {"error": "bad path"})
            return
        candidate = STATIC / rel
        if not candidate.is_file():
            candidate = STATIC / "index.html"
        if not candidate.is_file():
            self._send(
                503,
                b"bundle not built: run `npm ci && npm run build` in bench/sut/app",
                "text/plain; charset=utf-8",
            )
            return
        types = {
            ".html": "text/html; charset=utf-8",
            ".js": "text/javascript",
            ".css": "text/css",
            ".svg": "image/svg+xml",
            ".json": "application/json",
        }
        self._send(
            200, candidate.read_bytes(), types.get(candidate.suffix, "application/octet-stream")
        )


class _UnresolvedServer(ThreadingHTTPServer):
    """Skip the reverse DNS lookup in ``HTTPServer.server_bind``.

    It only fills ``server_name`` and takes 35 s on a hosted macOS runner. The SUT stays
    independent of the framework under test, so it does not import
    ``testence.loopback``, which does the same.
    """

    def server_bind(self) -> None:
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = str(host)
        self.server_port = int(port)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8800)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    httpd = _UnresolvedServer((args.host, args.port), Handler)
    print(
        f"sut on http://{args.host}:{args.port}  ({len(KNOWN)} injectable behaviours)", flush=True
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
