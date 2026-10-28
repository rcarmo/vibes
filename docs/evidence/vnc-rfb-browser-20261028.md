# Bounded VNC browser/RFB probe

Headless Chromium completed RFB 3.8 negotiation, VNC password authentication and
a raw framebuffer update through the real Python VNC WebSocket/TCP adapter.
A separate browser page with an incorrect password was rejected before display
initialisation. The upstream was an isolated synthetic loopback RFB peer, not a
real desktop or external VNC server.

## Workload

Runtime `a827ea5`; actual candidate `0259e9a` `VncRemoteDisplayProtocol` and
`vnc-auth` modules copied into disposable scratch and bundled with fflate 0.8.2.
The host mounted the real `VNCAdapter`, enabled only for its ephemeral numeric
loopback TCP listener. The browser fetched the owner cookie and used the required
same-origin WebSocket connection. No shared source/build or profile claim changed.

The peer offered password authentication only. Its challenge response was checked
independently using Python cryptography's DES-compatible TripleDES implementation
with the RFB bit-reversed eight-byte key. Fixture credentials were synthetic and
never printed. Successful auth preceded ServerInit, pixel-format/encoding setup
and one 2x2 raw update. The browser decoded wire BGRX using the actual candidate
protocol module and painted Canvas RGBA. Red, green, blue and white reference
pixels had maximum per-channel error 0 (tolerance at most 1 for 8-bit channel
conversion). No generated-output hashes were used. Incorrect auth produced no
frame or connected/display-initialised state; peer counts were one accepted and
one rejected connection.

Probe development initially used incorrect harness API/event field names
(`processBytes`, `outbound`, `updates`/`rectangles`, `connected`). Inspection of
the actual module corrected these to `receive`, `outgoing`, `rects` and
`display-init`. The final fresh-host run passed; these earlier failures were
harness errors, not diagnosed backend/RFB defects.

The follow-up VNC route/safety/race gate passed 16 tests in 1.58 seconds. No backend
source change was needed. Existing tests cover fixed target, Origin/cookie,
binary transport, uncertain-send close, shutdown/concurrent upgrade ownership,
handoff expiry/reuse and TCP cleanup.

## Limits and cleanup

The harness used the real candidate protocol and authentication code, not the
complete compiled VNC pane, renderer pipeline, a real desktop, TLS deployment,
clipboard/input, nonraw encodings or six-project browser suite. Parser-state
handoff/reconnect, slow-client soak, visible pane retry controls and Windows
behaviour remain unverified. The shared fixture's arbitrary direct-target error
scenario remains outside the fixed-loopback adapter contract. This bounded probe
does not close full VNC acceptance or issue #48.

The host/browser were stopped. Copied candidate modules, fflate/node_modules,
bundle, synthetic peer, scripts and disposable logs/test scratch are removed after
analysis; only these concise conclusions remain. No provider, deployment, fixture
repin, shared UI edit or remote agent contact occurred.
