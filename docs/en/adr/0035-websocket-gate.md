# ADR-0035: A recorded WebSocket gate for stale-tab scenarios

Status: implemented (engineering). Extends ADR-0027 and ADR-0030.

## Context

Live-update applications push changes made by other clients over a WebSocket.
A whole class of cases needs the test's own tab to miss those pushes while the
server keeps changing: a stale list, an edit of a row another client deleted,
a conflict message after an action on stale data. Browser "offline" emulation cuts HTTP too
and makes the client reconnect, which is a different scenario.

Testence only observed WebSocket frames (`wait_for_ws`). A consumer wrote the
gate by hand inside `ex.native` with `page.route_web_socket`. Measured on
Playwright 1.62 with a loopback server, that hand-written gate has three
defects the framework cannot see:

- `page.on("websocket")` reports the driver's real server connection, so a
  frame the gate dropped is still a `framereceived` event. `wait_for_ws` then
  returns a frame the page never received.
- The evidence ledger records only `native.used`; nothing says that server
  events were held back, so a stale UI reads like a product defect.
- A page-level route is lost on a new page, and a route installed after the
  socket opened silently does nothing.

The sync Playwright API dispatches route callbacks only while the test thread
is inside a Playwright call. A frame that reached the driver while the test
blocked on its own HTTP client is decided when the test next calls the browser.
A gate that flips its state without draining first decides queued frames
under the new state.

## Options compared

- Document the native recipe: keeps all three defects.
- Emulate offline on the context: cuts HTTP and forces a reconnect.
- Mock the whole socket in the test: proves nothing about the real server.
- Route the socket through the driver, forward both directions and drop only
  server frames the gate selects: chosen.

## Decision

`ex.ws_gate(pattern, protocol="socket.io" | "raw", drop=None, offline=False)`
installs a context-level route (`BrowserContext.route_web_socket`), so every
page of the session is gated. It refuses when a matching socket is already
open. It returns a handle with `offline()`, `online()`, `dropped` and
`delivered`.

- Client frames always pass. Server frames pass while online.
- While offline, `protocol="socket.io"` drops event packets (`42…`) and binary
  events (`45…`) with their attachments; engine.io open, ping, pong, close and
  socket.io connect, disconnect and acknowledgements pass, so the connection
  stays up and the tab simply goes stale. `protocol="raw"` drops every server
  frame. `drop=` replaces the rule with a predicate over the payload.
- Every transition first makes one round trip to the browser, so frames
  already queued are decided under the state they arrived in. `online(drain_ms=)`
  can wait longer for frames still in flight.
- Frames of a gated socket enter the WebSocket buffer only when delivered to
  the page; a dropped frame is invisible to `wait_for_ws`.
- `websocket.gated` events record installation, each transition with the
  frames dropped in the window, and a summary at the end of the test.
- Inside `ex.native`, a raw `route_web_socket` on the page or its context is
  observed like `route` (ADR-0030): its registration and each routed socket
  emit `websocket.gated` with `source: native`, and the frames its handler
  sends become the page's buffer.
- Playwright has no `unroute_web_socket`. Context reset discards the route
  with the context; for a kept context the gate turns into a passthrough.

## Consequences

A test reads the UI under a stale socket as UI behaviour on stale data. It
proves nothing about the server: the backend state still needs an independent
read. The round trip on each transition costs one browser call. Draining
cannot see frames still on the network between server and driver; the
documented remedy is a product signal (the other client's response, a
`drain_ms` chosen from the product's push latency), never a retry.

Socket.IO over long polling is not gated: the gate applies to the WebSocket
transport only. Service workers, shared workers and sockets opened before the
gate are outside this contract.

## Tripwire

A frame dropped by the gate must never be returned by `wait_for_ws`; ping must
reach the page and pong the server while offline; the gate must survive a new
page; a gate on an already open socket must fail loudly; context reset must
leave no active gate. No automatic reconnect, retry or assertion relaxation is
permitted.

Semantics: [Playwright WebSocketRoute](https://playwright.dev/python/docs/api/class-websocketroute),
[Socket.IO protocol](https://socket.io/docs/v4/socket-io-protocol/),
[Engine.IO protocol](https://socket.io/docs/v4/engine-io-protocol/).
