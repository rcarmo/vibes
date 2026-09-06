# Python UI parity implementation

## Agreed scope

Target the Python branch. Preserve Piclaw markup as closely as possible: DOM,
classes, icons, controls, and accessibility attributes. Adapt server wiring, not
UI design. Chat pop-out is explicitly excluded; terminal pop-out is required.
Commit tested slices incrementally. Do not change the Go worktree.

## Implementation order and acceptance criteria

1. Terminal service and UI: default-off Python PTY with Piclaw-compatible HTTP
   session/handoff and WebSocket input/output/resize. Ownership checks, expiring
   single-use handoffs, bounded output replay, reconnect grace, resize, child
   cleanup, and pane/pop-out transfer must be tested. Moving the terminal must
   preserve the shell; closing/expiry must not leak processes. Match Piclaw DOM.
2. Agent references: ACP-accessible MCP messages search/get with bounded output,
   session access scope, and reference resolution. Workspace references must have
   a tested file-access contract. Do not imply that an ID alone supplies content.
3. Composer: arbitrary files and clipboard images/files, error handling and
   reference pills; explicit Enter/steer behavior, atomic queued promotion,
   reordering and structured attachment/reference queue previews.
4. Sessions: persistence/addressing before switcher and mentions. Isolate composer
   history/state by session; switch/create/rename/delete with keyboard navigation.
5. Search, model and status: search scope; per-session model selection, catalog
   refresh/loading/error states; thinking capability gates. Refresh model,
   provider, thinking, execution state, context usage and compaction information
   together when switching sessions. Unknown metrics remain unavailable, not zero.
6. Verification: backend tests, frontend lint/build, headed Chromium/WebKit under
   Xvfb, desktop/mobile screenshots and DOM comparisons. Document deviations and
   unsupported ACP capabilities. No disabled tests to manufacture parity.

## Refinement decisions already supplied

- Piclaw is the behavioral and markup reference, not the Go terminal prototype.
- Terminal transport confirmed from Piclaw source: GET /terminal/session,
  POST /terminal/handoff, WebSocket /terminal/ws.
- No new framework or database replacement is planned.
- Security remains local-first: terminal must be explicitly enabled; origin
  checks and session ownership are required and are not a substitute for remote
  authentication. Remote deployment still requires external authentication.
- Backend-specific capabilities must not be fabricated for visual similarity.

## Evidence and deviations

Baseline: Python audit merged at ad06c10, capture tooling at 1a9f0cf. Prior audit
reports 390 Python tests and 38 headed browser tests. Re-run before relying on
these counts for the changed tree. Implementation evidence belongs below as each
slice lands. This document is a plan, not a completion claim.

### Terminal transport slice

Python now registers the session/handoff/WebSocket endpoints, disabled unless
`VIBES_ENABLE_TERMINAL=1`. It uses an HttpOnly SameSite=Strict owner cookie (a
Python-specific adapter detail), mandatory same-origin WebSocket/POST requests,
single-use expiring handoff tokens, 15-second reconnect grace, bounded output,
and cleanup on application shutdown. No terminal UI is wired yet. Do not enable
on an unauthenticated network listener. This is a local terminal, not a sandbox.

Verification: 397 Python tests pass, including real PTY I/O/resize, handoff reuse
rejection, expired handoff rejection, reconnect preserving the same shell,
disconnect expiry, disabled routes, invalid frames and origin rejection.
Outstanding: markup/UI port, controlling-terminal/job-control verification,
browser handoff flows, and comparison with Piclaw presentation.

### Reference correction — deployed 2.15.3 classic

The initial workspace Piclaw checkout was stale (4,479 commits behind upstream
at inspection). It is NOT the UI reference. Use classic app.bundle.js.map from
the installed Piclaw 2.15.3 release; extracted reference files are temporarily
under /workspace/tmp/piclaw-2.15.3-reference. Upstream main also confirms xterm.
Ghostty is an optional add-on, not the terminal renderer to port.

Reassessment adds folder references, upload progress, search attachment/image
filters, speech/push-to-talk, and grouped searchable session-picker lifecycle
metrics to acceptance scope. These are pending, not delivered capabilities.

The deployed terminal expects nested handoff.token, session_id/created_at/
process_pid metadata, ping frames, and explicit exit events. Corrected Python
transport accordingly. Cookie ownership remains a documented adapter difference;
the deployed client anonymous-token field is not trusted as authority here.
PTY launch now establishes a controlling terminal with TIOCSCTTY in an exec
helper (no threaded-server preexec_fn). Real tests cover foreground interruption
and shell survival. Backend suite: 399 passed. UI parity is not yet verified.

### First terminal UI slice

Ported terminal-pane.js verbatim from deployed Piclaw 2.15.3 classic source-map
content (MIT), with the matching vendored xterm assets and their embedded license
notices. Vibes supplies a small mount/pop-out adapter. Inner terminal markup is
unchanged; outer fixed-bottom panel/toolbar is provisional, NOT final dock markup
parity. Fonts and host toolbar/dock integration still require alignment.

Terminal enabled browser runs require VIBES_ENABLE_TERMINAL=1. Chromium and WebKit
both verify actual terminal command output and preservation of a shell environment
variable through pop-out handoff. Backend: 399 passing tests; build/lint pass.
Full 40-test runs reached 39 passed, with different existing WebKit editor tests
failing in parallel/serial runs. Do not claim full suite green; investigate before
final acceptance. No tests skipped or retries configured.

### Terminal typography and browser verification

Vendored the deployed FiraCode Nerd Font Mono regular/bold assets, metadata,
and upstream license texts. Added matching font faces. Test server explicitly
enables terminals while production remains default-off. Corrected the editor
popout test to assert hydrated UI rather than transient URL parameters that app
startup intentionally consumes. Full headed Chromium/WebKit run with one worker:
40/40 passed; backend 399 passed; frontend build/lint passed. An earlier unrelated
WebKit pin/unpin timeout did not recur; no application fix is claimed for it.

### Dock header markup alignment

Replaced provisional text toolbar with deployed dock-panel/header/title/actions/
body structure and identical pop-out/close SVG paths. Ported deployed dock CSS.
Added browser assertions for this structure; Chromium/WebKit terminal tests pass.
Remaining host deviation: Vibes mounts it as a fixed bottom panel rather than a
shared pane layout manager; detached-placeholder/reattach and splitter behavior
remain outstanding. Do not mark complete based on header alignment alone.

### Dock resize slice

Added pointer (mouse/touch) resizing, viewport bounds, keyboard arrow resizing,
and unmount cleanup. Emits Piclaw's dock-resize event to refit xterm/PTTY size.
Four headed Chromium/WebKit terminal tests pass; frontend build/lint pass.
Splitter sits inside Vibes' fixed-panel host rather than adjacent in the shared
Piclaw layout; retain this explicit structural deviation until host integration.
Detached placeholder/reattach remains pending.

### Detached placeholder and return handoff

Dock now remains visible with Piclaw's detached-placeholder structure and a
Reattach here action. Returning requests a new single-use token and mounts the
same shell locally; failed handoff requests retain the placeholder and surface
an error. Chromium/WebKit verify a shell variable survives dock -> popup -> dock
and that the popup closes. Four terminal tests and frontend build/lint pass.
Still pending: whole-layout parity and recovery when an external popup dies or
its session expires, plus screenshot comparisons and final regression sweep.

### Popup-loss recovery

Reattach now detects a closed popup and reconnects without a handoff only when
session metadata reports no active client. Server ownership/concurrency checks
remain authoritative. Expired sessions display an explicit new-shell notice.
Eight headed terminal tests pass across Chromium/WebKit, including closed-popup
state preservation within grace and restart after actual 15-second expiry.
Frontend build/lint pass. Layout/screenshot and whole-backlog acceptance remain.

### Desktop/mobile verification

Added desktop/mobile viewport bounds and control-visibility assertions plus
screenshots. Full headed Chromium/WebKit suite: 50 tests passed with one worker,
no retries/skips. Backend remains 399 passing; frontend build/lint pass. Captured
1440x1000 desktop and 390x844 mobile terminal screenshots (attached in task chat).
This establishes renderability, not pixel-identical host layout: the fixed bottom
host, launcher placement and splitter nesting remain tracked deviations from
Piclaw's shared pane shell. Do not equate these screenshots with final parity.

### Messages query foundation

Added read-only get/search core with explicit constructor-bound thread scope or
explicit workspace access, not caller-selectable tool scope. Literal FTS phrase
search, ID pagination, 50-result cap, 4,000-character per-message and 24,000 total
content caps. Returns selected message fields, not arbitrary stored JSON metadata.
Tests prove out-of-scope IDs/search hits are excluded and limits enforced.
Backend suite: 401 passed. This is NOT yet an ACP-accessible tool: MCP transport,
initialization/tool schemas and agent session injection remain to implement.
