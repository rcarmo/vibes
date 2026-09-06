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

### Read-only stdio MCP transport

Added `python -m vibes.messages_mcp --database PATH --thread-id ID` (or explicit
`--workspace-access`) with initialize, ping, tools/list and tools/call. SQLite
opens mode=ro with query_only; no migrations or writable store handles. Newline
JSON framing is bounded to 64KiB. Tool schema exposes only get/search fields;
caller scope escalation is rejected. Tests include actual subprocess stdio
initialization/discovery/get and exclusion of another thread. Backend: 403 pass.
ACP injection still pending; this executable alone is not automatic integration.

### uMCP adoption

Replaced the bespoke protocol dispatcher with pinned rcarmo/umcp 0.2.2 at
30cce7dfe08c6ee63de235f7d81754ba286dafbb. Vendored async/shared modules and MIT
license; only relative imports patched. Retained bounded stdio input and read-only
SQLite scope core. uMCP supports discovery before initialization and empty resource
listing; tests now reflect library behavior rather than bespoke restrictions.
403 backend tests pass, including real subprocess MCP retrieval/scope isolation.
ACP injection remains pending.

### ACP messages injection

Set VIBES_ACP_MESSAGES_ENABLED=true before creating/restarting an ACP session to
inject the bundled uMCP stdio server in both session/new paths. Default false.
Requires an existing persistent database; in-memory stores are rejected. Uses
the running Python executable, absolute database/module paths and explicit stdio
server env. Descriptor-generated subprocess discovery is tested (404 tests pass).

Important scope: the current Python ACP backend reuses a single agent session
across threads, so enabling this integration grants read access to the configured
workspace message database. Do not claim per-thread isolation for this mode.
Standalone --thread-id remains available; per-session injection must be revisited
with the planned session model. An actual third-party ACP agent consuming the
injected descriptor is still an acceptance check, not proven by descriptor tests.

### ACP injection branch verification

Tests now exercise both fresh-process and existing-process/no-session ACP paths
and assert messages descriptors reach session/new. 406 backend tests pass.
No installed `copilot` executable was found; third-party ACP consumption remains
unverified. Earlier composer assessment correction: existing Vibes has image
clipboard paste; the pending gap is general-file clipboard intake, not all paste.

### General attachment intake

Composer picker/drop/clipboard now accepts general File objects; mixed/nonimage
uploads use Attachments labels instead of Images. Image-only messages preserve
existing formatting. Removal works for all attachment types. Chromium/WebKit
picker and synthetic clipboard tests pass. Upload endpoint already supported
binary data. Media and thumbnail-fallback downloads now force attachment plus
sandbox headers for non-raster types, preventing uploaded HTML/SVG execution on
the application origin. Backend: 411 tests pass; build/lint pass. Still pending:
agent resolution of uploaded IDs, full submission/error/cleanup flows and
Piclaw FilePill markup alignment. Intake is not end-to-end attachment parity.

### Attachment send retry

Composer remembers completed uploads by File identity while retaining a failed
send draft; retry no longer uploads the same file again. WeakMap avoids retaining
discarded File objects. Four Chromium/WebKit attachment tests pass, including
simulated failed-send -> successful-retry payload and one-upload assertion;
frontend build/lint pass. This does not yet garbage-collect server-side uploads
abandoned when a draft is discarded. Real agent attachment consumption, upload
progress/cancellation and full Piclaw pill markup remain pending.

### Upload progress and cancellation

Added optional XHR upload progress/AbortSignal support without changing existing
uploadMedia callers. Composer uses deployed inline-status/progress DOM and CSS,
with an explicit cancel button. Cancel retains draft and completed upload IDs,
clears progress, reports cancellation and prevents submission. Unmount aborts
current upload. Six Chromium/WebKit attachment tests pass; build/lint pass.
Cancellation cannot guarantee the server did not finish storing bytes before the
abort arrived; abandoned-upload garbage collection remains separate pending work.

### Message attachment references

Bounded messages get/search results now include sanitized media_ids and explicit
attachment:N references from each authorized message. IDs are deduplicated,
positive integers only, capped at 50; unrelated threads remain excluded. Malformed
metadata does not break retrieval. Backend suite: 412 passed. These references
are not binary attachment contents and do not grant out-of-scope attachment reads;
content resolution remains an outstanding integration requirement.

### Scoped attachment text resolution

Messages MCP action=attachment accepts media_id. Authorization requires a message
in the tool's configured scope to reference the upload; guessing an ID alone is
insufficient. Text/JSON/XML/YAML previews are bounded to 24,000 bytes; binary media
returns MIME/size plus an unsupported-preview notice, not fabricated text or
unbounded base64. SQL limits the fetched blob prefix. Backend suite: 413 passed,
including cross-thread rejection, truncation and binary metadata handling.
Image/PDF parsing and arbitrary binary delivery to model backends are not implied.

### Shared reference pills

Ported deployed Piclaw FilePill source unchanged (MIT); composer now uses it for
message, workspace file and upload pills with existing state handlers. Removed
three duplicate markup blocks. Six headed Chromium/WebKit attachment tests and
frontend build/lint pass. Server-side abandoned upload cleanup and broader agent
binary handling remain open; this is markup reuse, not a claim of full parity.

### Abandoned upload retention

New upload records carry source=composer-upload. Startup cleanup removes only
marked uploads older than seven days, with neither structured media_ids nor
textual attachment:N references in stored messages. Untagged historic media and
recent uploads are never swept. Conservative substring matching may retain
extra uploads; avoiding reference deletion is preferred. Tests cover referenced,
text-referenced, recent, legacy and orphan records plus idempotence. 414 backend
tests pass. Cleanup runs on startup, not a new background scheduler.

### Explicit composer steering shortcut

Enter and send button submit mode=auto (existing backend queues when busy);
Ctrl/Cmd+Enter submits mode=steer. Search and slash completion retain their own
handling. Updated misleading Send/Attach image titles. Twelve combined mode and
attachment browser tests pass across Chromium/WebKit; build/lint pass. Backend
atomic queue promotion/reordering remains separate pending work.

### Queue promotion safety

Claimed queue entries now retain their public row ID when deferred as steering.
Cancellation during Pi write restores the item; failed writes fall back to pending
steer. Idle Pi fallback is honestly marked emulated. 416 backend tests pass.
This is in-process claim/rollback, not a durable exactly-once delivery guarantee:
a transport cancellation after bytes were sent remains an ambiguous delivery case.
Queue reordering and concurrency coverage still pending.

### Concurrent promotion and reorder service

Concurrent promotion test verifies only one Pi write claims the row; a second
request gets 404 while the first is in flight. Added synchronous same-agent/thread
up/down reordering and /agent/queue-reorder with broadcast. Other scopes retain
their positions; pending steers still dispatch first. 418 backend tests pass.
Reorder buttons and structured queue previews remain to wire into the composer.

### Composer reorder wiring

Added accessible up/down queue buttons using deployed Piclaw arrow markup,
boundaries per agent/thread, reorder API handling and SSE synchronization. New
queued entries append rather than timestamp-sorting away explicit order.
Chromium/WebKit verify request payload and returned visual order; build/lint pass.
Structured attachment/reference queue previews remain pending.

### Structured queue previews

Display-only parser recognizes Vibes/Piclaw file/folder/message/attachment block
formats and renders shared FilePill components. Original queued agent payload is
unchanged; malformed list entries remain in visible text. Reference count capped
at 50. Four Chromium/WebKit reorder/preview tests pass; frontend build/lint pass.
Whole composer visual parity remains tracked separately.

### Workspace reference read contract

Optional uMCP workspace_read(path, offset, limit) resolves relative file references
against an explicit --workspace-root. Descriptor-relative O_NOFOLLOW traversal
rejects every symlink component, absolute paths, dot/traversal segments and special
files. Nonblocking open prevents FIFO hangs. Reads use byte offsets and max 24,000
bytes; NUL-bearing previews rejected. This is Unix-only, no writes or execution,
and not an OS sandbox against a malicious local process rearranging directories.

For ACP enable both VIBES_ACP_MESSAGES_ENABLED and
VIBES_ACP_WORKSPACE_READ_ENABLED; root is the server working directory. Otherwise
workspace_read is not registered. Standalone MCP accepts --workspace-root.
420 backend tests pass including confinement, FIFO, bounded reads and actual
uMCP dispatcher calls. Agent's independent filesystem tools remain outside this
service's restrictions; do not interpret the flag as sandboxing the agent itself.

### Folder reference resolution foundation

Optional workspace_list joins workspace_read under the same explicit root/gate.
It lists at most 200 entries without following symlinks or traversing upward,
reports symlink/special types without opening targets, and marks truncated results.
No recursive scan or unbounded sorting. Backend: 421 passed. Folder composer/tree
selection and pills remain to wire; bounded listing is not full directory search.

### Folder composer wiring

Selecting a workspace folder adds a deduplicated folder reference, not recursive
uploads. Shared Piclaw folder pill supports removal/clear-all and folder-only
submission as a Folders block. Agents with workspace access enabled can resolve
it through workspace_list/read. Chromium/WebKit verify tree selection, pill,
folder-only payload and clearing; build/lint pass. Parent/session-level draft
persistence remains part of the session work, not provided by this slice.

### Search filter backend

/search supports optional positive thread_id plus has_images=true and
has_attachments=true. Filters combine with FTS and select stored media references,
not filename guesses; root and direct replies define current thread scope.
422 backend tests pass, including combined scope/media cases. Composer controls
and session-bound scope are pending; no false current-session UI is exposed.

### Composer media search filters

Ported deployed checkbox label classes and CSS for Images/Attachments search
filters. API forwards both flags; Chromium/WebKit test exact URL parameters.
Frontend build/lint pass. Current-session versus all-session selection remains
pending the session registry; backend thread_id support alone is not that UI.

### Durable session metadata foundation

Schema v5 adds chat_sessions with stable IDs, names, parent links, pin/archive
flags and timestamps; seeds default without touching existing interactions.
SessionStore supports create/list/get/rename/pin/archive and protects default from
archive. Migration version rows are consolidated to avoid selecting stale versions
on subsequent starts. Persistence/reopen and validation tests pass: 424 backend
tests. This does not yet route messages, isolate model context, delete histories,
or switch running agents. Session APIs/picker/state isolation remain pending.

### Session registry API

Added GET/POST /sessions and PATCH/DELETE /sessions/{id}, validated fields and
sessions_changed events. DELETE only permits empty non-default leaf sessions;
nonempty history is never silently destroyed. Responses disclose runtime_isolation
false. 425 backend tests pass, including route create/rename/pin/delete and
nonempty/default protection. Message routing, isolated agents and picker remain
pending; the registry endpoint is not an independent runtime session launcher.

### Stored-message session boundary

New interactions record a validated session_id (default when omitted); replies
inherit their root message's session and conflicting explicit IDs are rejected.
SessionStore timeline and GET /sessions/{id}/timeline filter by session, treating
legacy records without IDs as default and providing bounded cursor pagination.
426 backend tests pass. Existing global routes/runtime still behave as before;
UI switching and session-specific model contexts are not yet implemented.

### Session-scoped composer history foundation

History storage keys now include encoded session IDs; only default inherits the
legacy unscoped history. Switching the prop resets history navigation without
mixing previous-session entries. Storage denial is nonfatal. Two Bun unit tests
and six Chromium/WebKit submission-mode tests pass; build/lint pass. The app still
uses default until session runtime/picker wiring is ready; this does not yet
preserve per-session draft attachments or claim complete composer-state isolation.

### Session-bound MCP authorization

Added mutually exclusive --session-id scope alongside thread/workspace modes.
Session scope applies to get/search and attachment authorization; legacy message
records belong to default. Call arguments cannot change scope. 427 backend tests
pass, including cross-session message and attachment rejection. Existing ACP
injection is still explicit workspace-wide until runtime session selection is
implemented; no claim that this addition alone isolates current ACP processes.

### Session search boundary

Search now accepts validated session_id and intersects it with optional thread
and media filters. Legacy messages remain default. Frontend API helper forwards
session IDs for forthcoming picker scope controls. 428 backend tests pass,
including cross-session/thread intersection; frontend build/lint pass. Scope
selector remains pending runtime/session UI integration.

### Backend conversation binding foundation

Schema v6 stores conversation IDs/model/thinking metadata by chat session and
backend identity. Binding APIs validate owning session and keep ACP/Pi mappings
separate; persistence/isolation tests pass (429 backend tests). Mappings are
internal only: runtime dispatch/resume has not yet been wired. Merely storing a
conversation ID does not imply a provider can load it or preserve live context.

### In-process ACP conversation selector

Added busy-guarded select_chat_session, caching conversation IDs per chat for the
current agent process. New conversations get session-scoped messages descriptors;
process reset/stop clears mappings rather than pretending stale IDs are loadable.
430 backend tests pass, including reuse and busy rejection. Not yet exposed to
UI/message dispatch, no restart-resume claim, and default legacy startup still
uses explicitly opted-in workspace scope until that integration is completed.

### Lock-held ACP prompt selection

Multimodal ACP dispatch accepts an explicit chat_id and selects its conversation
while retaining request_lock through session/prompt. Public selection delegates
to the same lock-held helper. Test asserts lock ownership and selected session ID
at dispatch; 431 backend tests pass. Route/session picker wiring still pending;
existing calls without chat_id preserve baseline behavior.

### Fail-closed session submission boundary

Before picker/runtime integration, agent message routes now reject supplied
non-default session IDs instead of silently sending them into default context.
Invalid IDs and cross-session thread references are rejected before persistence
or scheduling. 433 tests pass. This is a safety guard, not session dispatch
completion; replacing it requires end-to-end routing/queue/backend isolation.

### Default-conversation restoration

Legacy simple/multimodal calls now explicitly restore the cached default ACP
conversation after another chat was selected, under the prompt lock. This avoids
implicit last-selected context reuse before session-aware route rollout. Tests
exercise both call paths; 435 backend tests pass. Routing/picker remain pending.

### Thread reassignment boundary

Database thread reassignment validates that source and target belong to the same
session and rejects missing target threads. Same-session moves and self-rooting
remain supported. This closes the post-insert busy-agent reassignment path before
session-aware dispatch rollout. 436 backend tests pass, including rollback after
cross-session rejection. Runtime routing/picker work remains in progress.

### Session draft store foundation

Added ComposeDrafts: text/reference metadata persisted per encoded session key;
File objects retained only in page memory and never serialized as bytes. Bounds,
malformed/quota handling, cross-session isolation, reload and clearing tested.
Four frontend unit tests pass; build/lint pass. Store not wired into mounted
composer yet; do not claim switching/reload draft preservation until integration.

### Mounted draft persistence

Composer now saves text/reference metadata and page-local File state to the
shared draft store; default app restores file/folder/message pills on startup.
Successful sends clear drafts. Chromium/WebKit verify seeded draft load, edits,
reload, references and successful-send clearing; build/lint pass. Session switching
must key/remount composer and restore parent reference state before exposing the
picker; this slice proves default-session reload, not full switching yet.

### Session history activity metadata

Registry listings include stored message_count, last_message_id and last_message_at
using one aggregate join (not per-session queries). Empty sessions report no last
message; activity is not labeled running/idle or model context. Sorting preserves
pin priority and uses latest history activity. 437 backend tests pass. Picker and
runtime status remain unimplemented, not inferred from these metadata fields.

### Session-aware ACP worker dispatch

Response worker resolves chat identity from the persisted thread and forwards
non-default identities to lock-held ACP selection. Missing/archived chat metadata
is rejected; default retains compatible call behavior. 438 backend tests pass,
including sender argument verification and archived-session rejection. Public
non-default submission remains gated pending admission/queue and Pi runtime work.

### Pi session RPC selector foundation

Added isolated PiSessionSelector using documented get_state/new_session/
switch_session commands. Checks busy state, persistence, cancellation and final
session file before accepting a switch. Tests cover create/switch-back and
cancelled/busy/no-persistence cases; 440 backend tests pass. Caller must own Pi's
request lock. Not yet wired into client/route dispatch; confirmation failure
requires recovery before prompting. Live installed-Pi smoke still pending.

### Pi selector uncertain-state guard

A dispatched but unconfirmed Pi switch now marks the selector uncertain and
blocks subsequent selection until recovery/restart. This prevents overwriting the
old chat's path with an unexpectedly active context. Explicit extension-cancelled
switches remain usable. Failure/retry regression tests pass; 442 backend tests.
Runtime integration and live session smoke remain pending.

### Pi prompt selector integration

Pi multimodal prompts accept chat_id and select under request_lock before any
prompt write. Selection failure returns an error without sending private content;
non-default active selectors restore default for legacy calls. Process launch
resets selector state. 443 backend tests pass. Public routes still guard
non-default requests pending admission and live session switching verification.

### Live Pi session smoke

Installed Pi successfully returned distinct default/other session paths and
restored the original via real RPC, without model prompts. Added reusable
`tools/smoke-pi-sessions.py` with isolated temp cwd/session storage, extensions
disabled and bounded shutdown; ran successfully. This verifies switching protocol,
not authenticated model completions or public multi-session dispatch admission.

### Session-aware Pi worker dispatch

Pi response workers now derive chat identity from persisted thread records and
forward it to the lock-held selector; archived sessions are rejected before
prompting. Default calls preserve legacy compatibility. 444 backend tests pass.
Public non-default route guard remains until queued/active admission is made
session-safe; picker/runtime integration is still incomplete.

### Shared runtime worker serialization

Agent-response workers now acquire one dispatch lock before turn setup and retain
it through completion/follow-up scheduling. This prevents the generic three-worker
task pool from overlapping turns against the single shared ACP/Pi runtime. Test
blocks one worker and verifies the next cannot enter; 445 backend tests pass.
Admission/session UI remains pending; this is serialization, not parallel agents.
