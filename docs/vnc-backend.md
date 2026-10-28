# Opt-in local VNC transport

The Python backend relays opaque RFB bytes between a browser WebSocket and one
operator-configured numeric-loopback TCP endpoint. It never interprets RFB or
stores VNC credentials. The shared UI owns protocol negotiation, authentication,
rendering and visible retry/error controls.

## Configuration and routes

Disabled by default. `VIBES_ENABLE_VNC=1` or `true` enables a validated target.
`VIBES_VNC_HOST` defaults to `127.0.0.1`; `VIBES_VNC_PORT` defaults to `5901`.
Only numeric loopback addresses are accepted. `localhost` normalises to
`127.0.0.1` before connection; DNS is never used. Invalid/nonloopback targets
leave the adapter disabled with `configured:false`. No remote-host exception,
proxy URL, user-supplied port or arbitrary direct-connect mode is provided.

GET `/vnc/session` returns `enabled`, `configured`, `direct_connect:false`,
`ws_path`, `host`, `port`, `target` and (when enabled) `connected`. It creates an
HttpOnly, SameSite Strict owner cookie, Secure on HTTPS, and returns no-store.
An optional `target` query must equal the configured canonical endpoint; other
query parameters or alternate targets are rejected.

GET `/vnc/ws` requires same Origin and the issued cookie. It uses binary frames
only; each frame/output chunk is at most 64 KiB. Upstream connection timeout is
five seconds, output/backpressure timeout 15 seconds. A failed upstream produces
WebSocket close 1011; nonbinary input closes 1003 and oversize frames close 1009.
These are transport outcomes; the UI still needs to show and test the error.

POST `/vnc/handoff` requires the same owner/Origin and a connected socket. It
returns one expiring token (30 seconds) per owner. The next `/vnc/ws?handoff=...`
consumes it and replaces the browser attachment while keeping the TCP stream.
A disconnected owner has a 15-second grace period, then TCP is closed. Ownership
is established by the cookie, never a data-frame field. At most 128 owner records
are retained; inactive page visitors can be reclaimed without evicting live
connections.

## Byte-stream and security limits

TCP reads retain at most one application chunk while detached, applying bounded
reader/TCP backpressure. An attempted WebSocket send with an uncertain result
closes the tunnel instead of replaying the chunk into a new attachment. No
exactly-once byte-delivery claim is made across a broken socket.

The runtime remains a trusted single-user application; cookies separate browser
transport ownership, not OS users or host privileges. Enabling this route grants
the authenticated local browser access to the configured VNC server. VNC's own
credentials and desktop privileges still apply. Application shutdown closes
retained streams and pending expiry timers. It sets a closing flag, cancels and
joins in-flight connects, and rejects late connection registration. A per-owner
reservation spans WebSocket preparation, TCP opening and attachment so concurrent
upgrades cannot create an orphan second tunnel. Close-handshake waiting is
bounded to one second.

Preserving a TCP stream is not sufficient to resume a new RFB parser. Browser
handoff/reconnect must preserve or deliberately rebuild client protocol state;
opaque transport continuity does not establish protocol-state handoff. A
[bounded Chromium RFB/auth probe](evidence/vnc-rfb-browser-20261028.md) now passes
with the actual candidate protocol code, password accept/reject and a synthetic
raw canvas update. Complete browser/RFB acceptance and the shared UI's
arbitrary-direct-target error scenario are not satisfied by this fixed-target
implementation. Do not expand target reachability merely to make a
fixture pass.

## Verification

Focused VNC, terminal-route and HTTP-route gate: 37 passed in 2.10s. Tests use
real loopback TCP/WebSocket sockets, synthetic RFB greetings and opaque echo,
not a real desktop or external server. Coverage includes default-disabled
behaviour, Origin/cookie rejection, numeric-loopback validation, fixed-target
restrictions, binary transfer, handoff reuse/expiry, detached transport reuse,
upstream failure, size/type rejection, uncertain-send close and cleanup. Two deterministic race tests additionally gate
TCP opening, attempt simultaneous upgrades and complete a connection during
shutdown; they require one tracked tunnel or a closed late writer, never an
orphan forwarder.

No profile capability/skips, shared UI, authentication deployment or consumer pin
changed. The bounded synthetic RFB3.8/password/framebuffer probe passed with zero channel
error; the follow-up VNC route/safety/race gate passed 16 tests in 1.58 seconds.
Real-desktop/full-pane acceptance, interactive protocol-state handoff, slow-client
soak, cross-platform behaviour and whole-application pre-release profiling remain
open. Nothing was deployed or enabled on a running host.
