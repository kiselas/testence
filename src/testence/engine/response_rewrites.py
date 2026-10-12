"""JSON response adapters at CDP response stage: never reconstruct the request."""

from __future__ import annotations

import base64
import fnmatch
import json
from contextlib import suppress
from typing import Any, Callable


class ResponseRewrites:
    def __init__(self, context: Any, record: Callable[[str, str, str], None]) -> None:
        self.context = context
        self.record = record
        self.rules: list[tuple[str, str | None, Callable[[Any], Any]]] = []
        self.clients: list[Any] = []
        self.error: Exception | None = None
        context.on("page", self._page)
        for page in context.pages:
            self._page(page)

    def _patterns(self) -> list[dict[str, str]]:
        return [{"urlPattern": pattern, "requestStage": "Response"} for pattern, _, _ in self.rules]

    def _page(self, page: Any) -> None:
        client = self.context.new_cdp_session(page)
        client.on("Fetch.requestPaused", lambda event: self._response(client, event))
        self.clients.append(client)
        if self.rules:
            client.send("Fetch.enable", {"patterns": self._patterns()})

    def add(self, pattern: str, transform: Callable[[Any], Any], method: str | None) -> None:
        if not isinstance(pattern, str) or not pattern or not callable(transform):
            raise ValueError("rewrite_response requires a URL glob and callable JSON transform")
        if method is not None and (not isinstance(method, str) or not method.isalpha()):
            raise ValueError("response adapter method must be an HTTP method string")
        method = method.upper() if method else None
        if any(rule[0] == pattern and rule[1] == method for rule in self.rules):
            raise ValueError("a response adapter already owns this pattern/method")
        self.rules.append((pattern, method, transform))
        for client in self.clients:
            client.send("Fetch.enable", {"patterns": self._patterns()})

    def _response(self, client: Any, event: dict[str, Any]) -> None:
        request_id = event["requestId"]
        request = event["request"]
        url, method = request["url"], request["method"]
        rules = [
            rule
            for rule in self.rules
            if fnmatch.fnmatchcase(url, rule[0]) and (rule[1] is None or rule[1] == method)
        ]
        if not rules or "responseStatusCode" not in event:
            client.send("Fetch.continueRequest", {"requestId": request_id})
            return
        # Record before delivery, including failed transforms, to prevent persistence false greens.
        self.record(url, method, "response-rewrite")
        try:
            if len(rules) != 1:
                raise ValueError("overlapping response adapters match this request")
            status = event["responseStatusCode"]
            if method == "HEAD" or status in (204, 304) or 300 <= status < 400:
                raise ValueError("JSON response adapters require a body, not HEAD/redirect/204/304")
            original_headers = event.get("responseHeaders", [])
            content_type = next(
                (h["value"] for h in original_headers if h["name"].lower() == "content-type"), ""
            )
            if "application/json" not in content_type and "+json" not in content_type:
                raise ValueError("response adapter expected JSON content type")
            body = client.send("Fetch.getResponseBody", {"requestId": request_id})
            raw = (
                base64.b64decode(body["body"])
                if body.get("base64Encoded")
                else body["body"].encode()
            )
            if len(raw) > 2 * 1024 * 1024:
                raise ValueError("response adapter JSON body exceeds 2 MiB")
            transformed = rules[0][2](json.loads(raw))
            encoded = json.dumps(transformed, ensure_ascii=False, allow_nan=False).encode("utf-8")
            if len(encoded) > 2 * 1024 * 1024:
                raise ValueError("transformed response exceeds 2 MiB")
            headers = [
                h
                for h in original_headers
                if h["name"].lower()
                not in {
                    "content-length",
                    "content-encoding",
                    "transfer-encoding",
                    "etag",
                    "content-type",
                }
            ]
            headers.extend(
                [
                    {"name": "content-type", "value": "application/json; charset=utf-8"},
                    {"name": "content-length", "value": str(len(encoded))},
                ]
            )
            client.send(
                "Fetch.fulfillRequest",
                {
                    "requestId": request_id,
                    "responseCode": status,
                    "responseHeaders": headers,
                    "body": base64.b64encode(encoded).decode("ascii"),
                },
            )
        except Exception as exc:
            self.error = self.error or exc
            with suppress(Exception):
                client.send("Fetch.failRequest", {"requestId": request_id, "errorReason": "Failed"})

    def check(self) -> None:
        if self.error is not None:
            raise RuntimeError(f"response adapter failed: {self.error}") from self.error

    def close(self) -> None:
        self.context.remove_listener("page", self._page)
        for client in self.clients:
            with suppress(Exception):
                client.send("Fetch.disable")
            with suppress(Exception):
                client.detach()
        self.clients.clear()
