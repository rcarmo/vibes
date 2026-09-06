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

### Session-aware submission admission

Non-default plain-text submissions now validate registry/archive state, persist
session identity and route through serialized workers. Busy cross-session sends
(including steering) are rejected before storage; same-session busy queue behavior
is retained. Non-default slash commands remain blocked until command/model state
is session-aware. Tests cover accepted idle submissions and cross-session rejection;
447 backend tests pass. Picker, persistent backend resume and full integration
acceptance are still pending; this does not enable parallel agent execution.

### Durable non-default Pi resume

Non-default Pi workers pass SessionStore into lock-held dispatch. Selector uses
stored conversation paths with switch_session rather than new_session after a
process restart, and records the confirmed path before prompting. Failed switches
remain fail-closed. Default legacy startup behavior is unchanged; durable default
binding and ACP provider-supported restart loading remain pending. 448 backend
tests pass, including persisted-path command selection and worker store wiring.

### Capability-gated ACP restart resume

Initialization records agentCapabilities.loadSession. Non-default workers persist
conversation bindings by ACP command identity; after restart a saved conversation
uses session/load only if advertised. Unsupported resume fails before prompting
rather than replacing history with a new conversation. 449 backend tests pass,
including unsupported/supported load selection. Third-party ACP live acceptance
remains pending; provider changes intentionally create a separate binding key.

### ACP failed-load recovery

Failed/cancelled session/load discards the agent process before propagating the
failure, because the provider may already have changed active context. No target
chat binding is cached on failure. Error/cancellation tests pass; 451 backend
tests. This deliberately sacrifices process liveness for context isolation.

### Session picker component scaffold

Added standalone SessionPicker with deployed popup/results/option class structure,
search, keyboard arrows/Enter/Escape, pin and registry action callbacks. Nonempty
delete control is disabled to reflect current server policy. Not mounted in app
and not browser-accepted yet; this is a scaffold, not delivered switching UI.
Remaining visual details/grouping and all app state/routing must be completed.
Frontend build/lint pass; no browser behavior claim for this component yet.

### Picker browser behavior

Standalone picker fixture now verifies search, keyboard selection, Escape and
Rename-button Enter without accidental session switching in Chromium/WebKit.
Fixed deferred index reset racing rapid input/ArrowDown, and added stable row
keys. Build/lint pass. Fixture is not app integration or full markup parity;
main-shell state changes/grouping and registry actions still need wiring.

### Frontend session API contract

Added registry CRUD/timeline client helpers with escaped session IDs. Composer
submission explicitly forwards its sessionId prop (default remains default).
Five frontend unit tests and six browser mode tests pass; build/lint pass. Main
app still needs picker, timeline/event scoping and atomic draft/status switching.

### Race-safe session navigation coordinator

SessionNavigation commits selected ID, loaded timeline and matching draft together
only for the latest request. Stale responses/errors and disposed requests cannot
replace current UI; current-request failure leaves UI untouched. Seven frontend
unit tests pass; build/lint pass. Coordinator is not mounted yet; global timeline
loads/SSE still need session filtering before picker integration is complete.

### Session-tagged worker status events

Worker resolves chat identity once from persisted thread and includes session_id
in status/draft/thought/timeout and generated message payloads. This supplies the
frontend with a reliable filter key before picker mounting. A real-database worker
test checks emitted status scope; 452 backend tests pass. Browser event filtering
and current-session status reset still need integration.

### Live conversation event filtering foundation

Current default view rejects explicitly other-session post/status/draft/request
events; legacy untagged conversation events remain default-only. Global transport
and workspace events remain shared. Eight frontend unit and eight focused browser
tests pass; build/lint pass. Current ID is still default until picker mounting;
queue/model event ownership and global timeline loads require further integration.

### Session-filtered timeline fetch

Frontend timeline requests now explicitly select default session; backend accepts
session_id and uses scoped cursor pagination, preventing other-chat messages from
reappearing on reload after live-event filtering. Unscoped legacy API behavior is
retained for compatibility. 453 backend tests and two draft browser tests pass;
frontend build/lint pass. Picker will supply the selected ID in the next wiring.

### Mounted session picker first integration

Main app mounts picker with registry create/rename/pin/empty-delete callbacks.
Switch loads scoped history, restores per-chat refs, remounts composer by session
identity and clears previous status/context. Timeline fetches and conversation
SSE use selected ID; search defaults to selected session. Global polling/model
and queue updates are suppressed for non-default pending properly scoped status.
Chromium/WebKit verify default -> other -> default draft isolation and explicit
submission identity; build/lint pass. Native prompt/confirm action dialogs,
full deployed grouping/styles, queue ownership, selected status and stale loads
remain incomplete; this is not final UX acceptance.

### Search/session response race

Search captures session identity plus request generation; stale query success or
failure cannot overwrite a newer query or switched chat. Session switch and exit
search invalidate outstanding results. Four Chromium/WebKit switching tests pass,
including held search response released after switching; build/lint pass.

### Search scope selector

Composer exposes current/all sessions with deployed scope-select classes and CSS.
Current passes selected session_id; all omits it. Four Chromium/WebKit filter/scope
tests pass; build/lint pass. Deployed branch-family scope is not yet exposed:
requires descendant-aware filtering and remains a parity gap, not an alias.

### Branch-family search

Added actual root/descendant resolution (including siblings) and bounded family
search, excluding unrelated roots. Composer exposes Piclaw's third scope option.
Families over 500 sessions fail explicitly rather than silently truncate results.
454 backend tests and four Chromium/WebKit scope/filter tests pass; build/lint
pass. Registry parent links define family; agent context is not merged by search.

### Session picker grouping

Grouped picker now uses current/pinned/explicit-running/tree/other/archived sections
and preserves flattened keyboard navigation through filtered groups. History
activity is never used as a running-state proxy. Nine unit and six picker/switching
browser tests pass; build/lint pass. App listing still excludes archived sessions
until restore actions are wired; actual running metadata remains pending.

### Picker archive/restore

Picker includes archived entries and explicit archive/restore controls; choosing
an archived option restores it before switching. Active current chat returns to
default after successful archive. Backend rejects archive while a persisted turn
is active. 455 backend and six switching browser tests pass; build/lint pass.
Queued-but-not-started turns and final action markup parity remain to audit.

### Explicit picker runtime activity

Session listings expose boolean is_running from active_turns joined through stored
thread ownership; history timestamps do not drive it. Picker renders running/
idle/archived badges and can populate Active group. 456 backend tests plus two
picker browser tests pass; build/lint pass. Refresh is currently on picker open
or registry mutation; live status refresh and queued lifecycle remain pending.

### Corrected deployed picker CSS/classes

Re-extracted the installed source map directly and aligned picker to actual
compose-session/compose-model class names (earlier temporary reference had older
unprefixed names). Ported matching deployed CSS. Eight picker/switching browser
tests and build/lint pass. Action buttons/native dialogs and complete row markup
still differ; do not claim pixel-identical parity from class alignment alone.

### Live picker refresh

While open, picker refreshes registry/activity every three seconds, prevents
overlapping refreshes and ignores results after closure. Keyboard target clamps
to refreshed list length. Ten picker/switching browser tests pass, including
external create/rename while picker stays open; frontend build/lint pass.

### Session queue retrieval

GET /agent/queue accepts session_id, validates registry existence and resolves
queue/steer thread ownership from stored history. Unknown thread ownership is
excluded instead of defaulting into another chat. 457 backend tests pass, including
cross-session queue/steer exclusion. Frontend selected-session polling/events and
mutation scoping still need integration.

### Queued steering active-session guard

Promotion compares persisted queue-thread and active-turn session ownership before
claiming or writing Pi steering. Cross-session or unknown ownership returns 409
and retains the queued item. 458 backend tests pass, including no-write/no-removal
assertions. Selected-session queue UI refresh/mutation response scoping remains.

### Selected-chat queue polling

Non-default chats load scoped queues on selection and periodically, discard results
after unmount/switch, and refetch scoped state after mutations instead of using
unscoped reorder results. Ten switching tests pass including scoped queue display
and clearing on return to default; build/lint pass. Default global status queue
snapshot still needs full scope normalization; this slice is not final acceptance.

### All-chat queue scope normalization

Default and non-default views now load queues exclusively through session-filtered
endpoint; global queue broadcasts trigger scoped reload instead of applying raw
rows. Mutation responses likewise reload selected scope. Fourteen Chromium/WebKit
queue/switch tests and build/lint pass. Pending steer badge/status ownership still
needs dedicated scoped status normalization; no cross-chat queue rows are intended.

### Scoped status polling backend

/agents/status accepts session_id and filters active turns, queues and pending
steers using persisted thread ownership. Scoped busy flags no longer reflect
another chat's backend lock. 459 tests pass, including other-chat turn exclusion.
Frontend polling still needs to supply selected ID and handle response races;
unscoped endpoint remains compatible for existing callers.

### Selected-session status polling

Status API client now passes selected session on reconnect, active polling and
immediate selection. Late responses from prior selections are ignored; in-flight
turn state can restore on switch. Twelve switching browser tests and build/lint
pass. Context/model information remains separately guarded pending scoped backend
inspection; this is status-turn scoping, not full model/context parity.

### Correct Pi context inspection

Context endpoint now uses documented get_session_stats.contextUsage instead of
invented get_state context fields. Inspection owns request_lock, declines while
busy and rejects nonactive/uncertain chat selection so it cannot consume prompt
stream events or expose another chat's usage. 460 backend tests pass. Busy usage
currently returns unavailable; cached/live event metrics remain future work.

### Selected-chat context polling

All context fetches now carry selected session identity. Shared refresh checks
session plus switch generation before committing and clears unavailable/error
results instead of retaining stale usage. Refresh runs on switch/reconnect/turn
completion/polling. Fourteen switching tests and build/lint pass. Inactive/busy
Pi chats remain honestly unavailable until cached per-session metrics exist.

### Model-command cross-session guard

Composer model commands explicitly carry sessionId and are blocked for non-default
until backend command isolation is implemented. Buttons disable if shown there;
unknown model state remains hidden after switching. Two focused Chromium/WebKit
guard tests and build/lint pass. This prevents default-context mutation but does
not satisfy planned per-session model-picker functionality.

### Scoped model-state inspection

GET /sessions/{id}/model-state inspects only matching idle Pi context under its
request lock and reports unavailable otherwise. Returns selected model identity,
thinking and compaction state without raw provider URLs/configuration. 461 backend
tests pass, including output whitelisting. ACP metadata, cached busy state and
frontend model-state integration remain pending.

### Selected model display

Mounted app inspects selected chat model state on switch and periodically; only
matching current responses update model/thinking labels. Unavailable/errors clear
labels instead of retaining another chat's model. Non-default controls remain
disabled pending safe mutation. Eighteen switching browser tests and build/lint
pass, including scoped model display and clearing on return to default.

### Scoped Pi model mutation foundation

change_chat_model holds request_lock, requires matching active idle Pi chat, and
validates model/thinking selection against live catalogs before mutation. Rejects
busy/wrong-context and unsupported choices without sending mutation. 463 backend
tests pass. No HTTP/UI mutation route yet; inactive chat selection and durable
model preference behavior remain pending rather than falling back to default.

### Session model mutation endpoint

POST /sessions/{id}/model validates model/thinking input, requires existing
unarchived session and delegates to guarded matching-idle Pi mutation. Returns
sanitized confirmed state and session_model_changed event; busy/mismatched context
returns 409. 464 backend tests pass. ACP mutation and frontend catalog/control
integration remain pending; endpoint does not implicitly activate inactive chats.

### Scoped model/thinking catalog

GET /sessions/{id}/models returns bounded sanitized Pi model and thinking choices
only for matching idle context under the stream lock. Otherwise available=false;
no active-context switch occurs during inspection. 465 backend tests pass.
Frontend per-session mutation/catalog wiring and ACP capability handling remain.

### Non-default model picker mutation wiring

Non-default model popup loads scoped catalog and submits selection to
/sessions/{id}/model, not default slash commands. Unavailable catalogs show no
choices; errors retain current label. Six model browser tests and build/lint pass.
Default legacy model controls remain separate; thinking-cycle and full deployed
picker markup still pending.

### Scoped thinking control wiring

Non-default thinking cycle fetches supported levels and submits only the next
catalog value through session-specific model endpoint. Unavailable catalogs show
an error instead of fallback to default. Added accessible control label. Two
Chromium/WebKit thinking tests and build/lint pass. Default command path and full
Piclaw model picker/ACP options still need consolidation.

### Scoped model-change events

session_model_changed events update only owning selected chat. An inspection
started before a change event cannot overwrite newer confirmed labels; errors
from such stale polls likewise cannot clear them. Ten frontend unit tests and
eight model/thinking browser tests pass; build/lint pass. Full polling/event race
browser acceptance remains part of the final regression work.

### Preserve model metadata across rebinding

Conversation-only binding updates no longer erase confirmed model/thinking fields.
Successful scoped model mutation persists confirmed Pi sessionFile and sanitized
model label/level when supplied by RPC. 466 backend tests pass, including repeated
binding and partial metadata updates. Stored metadata is not proof of live state;
inactive-context UI still reports unavailable rather than inventing current usage.

### Integrated regression checkpoint

At 0fd4b70, re-ran all backend tests (466 passed), frontend unit tests (10 passed),
frontend build/lint and headed Chromium/WebKit suite with one worker (98 passed).
No skips or retry configuration added. Working tree remained clean after build.
This validates the implemented slices together, not the unfinished acceptance
items: mentions, speech, default model-path consolidation/ACP controls, full dock
layout, complete picker markup, and third-party agent acceptance remain open.

### Session mention autocomplete foundation

Composer @ queries active registry sessions by name/ID (max ten suggestions),
keyboard-selects a stable @session:ID reference and leaves send destination
unchanged. Archived chats excluded. Chromium/WebKit verify insertion and no
rerouting; build/lint pass. Mention resolution tooling, exact deployed suggestion
markup/styles and request coalescing remain pending; references grant no access.

### Mention interaction refinement

Uses deployed compose-box.ts suggestion DOM/classes (slash-autocomplete,
slash-item, slash-name, slash-desc), retaining explicit listbox/option semantics.
Registry fetches are coalesced per open mention interaction; disposed requests
cannot repopulate suggestions. Session/search transitions clear suggestions;
acceptance restores caret after the inserted reference and preserves suffix text.
Four headed Chromium/WebKit mention tests pass, including query reuse, Escape,
and insertion in the middle of text. Build/lint pass. Stable IDs intentionally
replace deployed agent aliases; authorized reference resolution remains pending.

### Authorized mention identity resolution

The read-only MCP `messages` tool now accepts
`{"action":"resolve_session","reference":"@session:ID"}`. It returns only
ID/name/archive state, and only for the bound session, the bound thread's owning
session, or explicitly opted-in workspace scope. Missing and unauthorized IDs
both return `{"session":null}`; no backend bindings, model metadata or history
are returned. References do not change the send destination or tool scope.
467 backend tests pass, including session/thread/workspace authorization and
invalid reference inputs. Third-party discovery/consumption acceptance remains
open; this is not cross-session messaging.

### Speech recognition lifecycle foundation

Added independently tested secure-context/API capability detection and recognition
controller: cumulative interim results replace rather than duplicate text;
permission errors remain visible after end; disposal invalidates late callbacks
before abort. Push-to-talk start predicate follows deployed empty-composer Space
behavior and rejects modifiers/repeats/search. Four new unit tests (14 total)
and build/lint pass. Controller is not yet mounted: toolbar/status markup, keyup,
blur/session/unmount wiring and browser acceptance remain pending. No live
microphone or speech-service acceptance is claimed.

### Mounted speech input

Composer now mounts capability-gated microphone toggle, deployed mic/status
classes, accessible permission/listening/error status and empty-composer Space
push-to-talk. Key release stops; window blur, session/search transitions, manual
input, submission and unmount invalidate/abort recognition. Unsupported browser
APIs render no control. Four headed Chromium/WebKit tests with mock recognition
verify transcript updates, denied permission, key release and blur; 14 frontend
unit tests and build/lint pass. Live speech-service acceptance, pointer-hold
behavior and final mobile/markup comparison remain pending. Browser recognition
may use a remote browser-vendor service; this is not local audio transcription.

### Speech pointer hold interaction

Touch/pen primary-pointer hold starts speech only in an empty composer, matching
deployed eligibility. Release stops, cancellation/lost capture aborts, and the
compatibility click is suppressed without disabling keyboard activation or the
next pointer gesture. Mouse remains click-toggle. Eight headed Chromium/WebKit
speech tests pass; pointer tests dispatch synthetic events (capture is stubbed),
not physical touch/microphone acceptance. Build/lint pass. Native pointer capture,
mobile visual comparison and live recognition remain unverified.

### Speech session/draft isolation acceptance

Twelve headed Chromium/WebKit mocked-speech tests now pass. Added explicit
session-switch and manual-edit cases that retain an old callback and invoke it
after abort: neither can overwrite the new draft. These confirm mounted cleanup,
not live microphone-service operation. Mobile/native-touch and final visual
acceptance remain open.

### Terminal viewport resize regression

Confirmed existing viewport-height clamp rather than adding duplicate behavior.
New headed Chromium/WebKit tests verify keyboard splitter increments and shrinking
from 1200x1000 to 844x390 keeps the panel and hide control in bounds (2 passed).
This does not close shared-pane host layout parity: the fixed overlay and launcher
placement remain unchanged and still require structural integration.

### Shared terminal/editor host structure

Moved TerminalPanel into deployed-style editor-pane-container alongside the
editor stack, with the horizontal editor splitter outside the shared column.
Desktop terminal now occupies workspace-side space rather than overlaying the
timeline/composer; popout stays full-window. Narrow screens stack the shared
column above chat (documented responsive adaptation). 52 headed Chromium/WebKit
terminal/editor-tab tests pass, including explicit no-composer-overlap at 1440
and 390px; build/lint pass. Launcher remains fixed, standalone resize semantics
and final screenshot comparison need refinement; host parity stays open.

### Shared dock resize semantics

Height splitter is now shown only when an editor shares the terminal column;
terminal-only columns fill their available space without a no-op height control.
Pointer sizing uses the column bottom and clamps against container height, not
viewport coordinates. Existing resize tests now open an editor to exercise real
shared-height behavior. 18 headed Chromium/WebKit terminal tests and build/lint
pass. Initial test run exposed an incorrect new workspace test selector (fixed);
its timed-out isolated server was explicitly stopped before rerunning. Launcher
placement and final screenshot parity remain open.

### Integrated speech/mentions/shared-dock regression checkpoint

At 470ca57: 467 Python tests, 14 frontend unit tests, frontend build/lint and
120/120 headed Chromium/WebKit tests pass with one browser worker. No retries or
skips added. Generated build leaves the working tree clean. Includes mounted
speech isolation, mention insertion/resolution tests, editor/popout and terminal
shared-column workflows. This does not establish deployed screenshot equivalence,
live speech service, authenticated model prompts or third-party ACP consumption;
those acceptance limitations and remaining UI gaps stay open.

### Mention MCP dispatch acceptance and fix

Protocol-level tools/list + tools/call test caught missing `reference` forwarding
in MessagesMCP.messages despite its advertised schema. Fixed handler forwarding;
protocol now verifies default identity, identical null for missing/unauthorized
references and rejection of per-call workspace scope escalation. 468 backend
tests pass. Prior query-class coverage alone did not establish working MCP
resolution. Combined with four browser mention tests, local reference addressing
is implemented; third-party agent consumption remains a separate open criterion.

### Session picker active-option accessibility

Focused search now exposes combobox/listbox ownership and active-descendant;
keyboard selection scrolls the active option into view. Empty filters clear the
active descendant rather than referencing a nonexistent node. Four headed
Chromium/WebKit picker tests and build/lint pass. Updated prior searchbox test
locator for the deliberate combobox role change. Full deployed picker actions,
metrics and dialog styling acceptance remains open.

### Session picker lifecycle action gating

Archive is disabled for running sessions; deletion is disabled for nonempty
sessions or sessions with children. Parent checks use the entire supplied registry,
not filtered search results, with explanatory titles. Backend rejection still
surfaces as an alert for stale state. Six headed Chromium/WebKit picker tests and
build/lint pass, including filtered parent, archived restore, and error feedback.
This is UI guidance, not replacement authorization; backend remains authoritative.

### Mounted session rename dialog

Replaced rename prompt with rename-branch overlay/panel/input/actions classes from
deployed reference. Accessible dialog includes initial selection, focus trapping/
restoration, Escape/backdrop cancel, busy/error feedback and backend-compatible
1–80 character validation. Eight headed Chromium/WebKit picker tests and build/
lint pass, including mounted API save and focus return. Names intentionally remain
display names rather than deployed restricted handles; CSS is a local adaptation
pending screenshot comparison. Create/delete prompts remain to migrate.

### In-page session creation

New session now reuses the accessible name dialog rather than a browser prompt.
Creation errors retain the entered name; successful creation refreshes/selects
the new session. A confirmed created ID is retained while retrying refresh/select
so a later UI failure does not intentionally issue another create. Ten headed
Chromium/WebKit picker tests and build/lint pass, including rejected POST/retry.
Delete confirmation and final visual comparison remain open; network-uncertain
POST outcomes are not claimed exactly-once.

### In-page session deletion confirmation

Replaced browser confirm with alertdialog using shared dialog classes. Initial
focus is Cancel; Escape/backdrop cancel, focus loop, busy guard, irreversible
operation description and backend-error feedback are explicit. Confirmed deletion
is not repeated while retrying refresh/switch follow-up. Twelve headed Chromium/
WebKit picker tests and build/lint pass, including cancellation/focus return,
backend rejection and successful deletion. Visual parity remains separate.

### Session composer/switcher functional acceptance

At b9bb01c, 34 headed Chromium/WebKit picker/switching tests, two persisted-draft
browser tests and 14 frontend unit tests pass. Covers scoped drafts/send identity,
late search rejection, queue/status/model/context scope, registry refresh,
archive/restore, create/rename/delete dialogs and keyboard action separation.
The session composer/switcher functional checklist item is complete. Full deployed
picker grouping/metrics/dialog visual equivalence remains a separate open item;
this does not claim external provider availability or live-agent acceptance.

### Picker persisted-message timestamp

Picker rows show last_message_at as an explicit Last message time with machine-
readable datetime; SQLite unzoned timestamps are interpreted as UTC, invalid or
missing values hidden. No running/idle inference is made from this history value.
15 frontend unit tests, 12 headed Chromium/WebKit picker tests and build/lint pass.
Runtime metrics, queued lifecycle and final visual equivalence remain open.

### Picker in-process queued-work counts

Registry now counts queued follow-ups plus pending steers by persisted thread
ownership (chunked SQLite lookup). Missing threads are ignored; legacy threads
belong to default. Picker shows a separate queued badge without inferring running
state or persistence. 469 backend tests, 12 headed picker tests and build/lint
pass. Counts are snapshots of current process memory, not durable delivery or
exactly-once guarantees; final grouped metrics/visual acceptance remains open.

### Picker metric browser acceptance

Added desktop 1280px and narrow 390px Chromium/WebKit coverage: an idle chat can
show queued work without becoming Running; running chat hides absent queue/time;
valid persisted time exposes UTC datetime and invalid time is omitted. Popup
bounds remain inside viewport. Sixteen headed picker tests pass. This bounded
layout check is not screenshot equivalence or exhaustive action-row overflow
acceptance; those visual requirements remain open.

### Picker row DOM/class alignment and action bounds

Corrected unstyled local row/pin/item classes to deployed
compose-model-popup-item-row, compose-session-row-pin and session-item structure;
added missing compose-session-row-main metadata wrapper. Local lifecycle actions
wrap below pin/item on narrow screens (chat popout remains excluded). Eighteen
headed Chromium/WebKit picker tests and build/lint pass, including all action
button horizontal bounds for long names at 390px. Initial exact row-count test
assumption was corrected for the shared test server registry. Screenshot parity
and remaining lifecycle styling are still not claimed complete.

### Picker pin shortcut and state indicator

Alt+Enter from picker search toggles highlighted active session pin without
selecting it; repeats and archived targets are ignored. Pin control advertises
shortcut, disables unavailable/archived actions, and shows filled/outline star
for pinned/unpinned state. Twenty headed Chromium/WebKit picker tests and build/
lint pass. Full screenshot equivalence remains unverified.

### Grouped picker browser acceptance

Empty search now announces No matching sessions. Browser fixture verifies all six
groups and precedence (current over pinned; pinned over running; archived over
pinned), and verifies future history timestamps do not imply active runtime.
22 headed Chromium/WebKit picker tests and build/lint pass. Grouping/search/
lifecycle behavior is covered locally; final deployed screenshot comparison
and unsupported runtime metrics remain explicit open acceptance work.

### Model catalog lifecycle isolation

Model popup clears old choices/catalog at load, keys fetching to session identity,
and discards completion/error/finally callbacks after close or dependency change.
Catalog failures render an explicit alert rather than silently looking empty.
Ten headed Chromium/WebKit model/thinking tests and build/lint pass, including
close/reopen with delayed stale response and visible newer failure. Default
command-path consolidation and complete picker markup remain open.

### Model catalog search and retry

Picker filters reported model labels case-insensitively, distinguishes no matches
from unavailable catalog, and retries failed catalog loads explicitly. Twelve
headed Chromium/WebKit model/thinking tests and build/lint pass, including retry
recovery and filtered choices. Default backend command consolidation and complete
deployed model-picker interaction/markup remain open.

### Model picker keyboard focus

Model search receives focus on opening; Up/Down moves focus through enabled model
choices with wrapping and scroll visibility. Native button Enter selects; Escape
closes and restores the trigger. Fourteen headed Chromium/WebKit model/thinking
tests and build/lint pass, including arrow focus and Escape restoration. Full
model control/default-backend and visual parity remain open.

### Scoped Next model control

Non-default Next model now cycles the confirmed available catalog through the
session mutation endpoint instead of the guarded legacy command no-op. It is
disabled while loading/switching or without available choices. Sixteen headed
Chromium/WebKit model/thinking tests and build/lint pass; new test verifies next
catalog selection and zero default message commands. Default command-path
consolidation and full deployed model picker remain open.

### Mutation callback ownership across composer unmount

Model-state callbacks are invalidated on composer unmount, preventing late scoped
mutation or legacy command results from relabeling the newly selected chat.
Eighteen headed Chromium/WebKit model/thinking tests and build/lint pass; added
held mutation response test switches chats before release and retains the new
chat's own label. Test closes popup with Escape before switching to avoid its
legitimate pointer overlay. Server mutation itself is not cancelled or rolled back.

### Full regression: owner-cap leak and mention reopen race

Full suite exposed /terminal/session owner exhaustion after 128 isolated browser
visitors. At the cap, reclaim only owners without shell, socket, grace timer or
unexpired handoff; retain the cap and active ownership. Regression exercises 140
cookie-less visitors while a live shell remains protected. Also moved mention
suggestion clearing to dismissal rather than opening, avoiding transient visible
stale options disappearing before keyboard acceptance.

Initial integrated run timed out after terminal 503 failures; isolated leftover
server was stopped. Next run had 149 passes and one mention race failure. After
both fixes: 470 backend tests, 15 frontend unit tests, build/lint and 150/150 headed
Chromium/WebKit tests pass with one worker. No retries/skips or cap increase.
Overall parity and external-agent acceptance remain open.

### Guard legacy default model catalog inspection

GET /agent/models now uses locked, context-matching Pi inspection helpers for
explicit default chat instead of raw RPC against whichever conversation is loaded.
Unavailable/busy/uncertain default returns the existing empty response; raw models
are bounded to 500. 471 backend tests pass, including explicit default helper calls
and no raw RPC when inspection is unavailable. Default mutation command-path and
full model-picker parity remain open.

### Unified composer model mutation path

Default composer now uses /sessions/default/models and /sessions/default/model
for selection, cycling and thinking changes, just like other chats. Removed UI
slash-command model mutations and string-response parsing; unavailable catalogs
disable cycling consistently. Twenty headed Chromium/WebKit model/thinking tests
and build/lint pass, including default selection/thinking with zero message
commands. Explicit user-entered slash commands remain a separate legacy surface;
ACP capabilities and complete visual picker parity remain open.

### Independent model/thinking catalog capabilities

Pi model choices remain available when optional thinking-level inspection is
unsupported, returns failure, or times out; thinking choices stay empty rather
than fabricated. Failed model inspection still fails closed and skips thinking
RPC. Existing request-lock/context guards remain intact. 476 backend tests pass,
including five capability fallback cases. Live provider acceptance remains open.

### Catalog response validation

Scoped catalog now excludes missing, non-string, empty, oversized or control-
character provider/model identities; optional names, reasoning flags and context
windows are type/bounds checked. Thinking choices are bounded valid strings and
deduplicated. Null list fields safely yield empty choices. 477 backend tests pass,
including malformed provider metadata. This validates response shape, not provider
availability or authorization to run any listed model.

### Archived model inspection gating

Archived session model-state/catalog reads return explicit unavailable responses
without inspecting Pi, consistent with existing mutation rejection. Missing IDs
remain 404. 478 backend tests pass, including archived read no-RPC assertions and
mutation rejection. Stored history/bindings remain untouched; restore is required
before live controls can become available.

### Terminal keyboard toggle

Ctrl+Backquote now toggles enabled terminal dock, matching deployed shortcut.
Extra modifiers, repeats and composition events are ignored; terminal popouts do
not install the shortcut. Launcher advertises aria-keyshortcuts. Two headed
Chromium/WebKit tests verify hide/reopen retains shell state during grace;
build/lint pass. Launcher placement and screenshot equivalence remain open.

### ACP declared-capability capture foundation

ACP initialization retains an allowlisted copy of declared loadSession, prompt
image/audio/embeddedContext and MCP http/sse booleans. Unknown fields and nonboolean
claims are discarded; reset/start/stop clear declarations. Read helper reports
None when disconnected. 479 backend tests pass. This foundation is not yet exposed
in agent-list/UI and does not prove actual capability execution; ACP UI acceptance
remains open.

### ACP reported capabilities API

Agent listing exposes reported_capabilities on ACP entries only (whether default
or secondary); disconnected/uninitialized declarations are null. Pi entries do
not inherit ACP claims. 483 backend tests pass, including both default-backend
configurations and unavailable declarations. This is descriptive initialize
metadata, not proof of image/audio/MCP consumption or live model availability;
UI capability presentation and third-party acceptance remain open.

### ACP initialize/stop declaration lifecycle test

Added startup test exercising _ensure_agent with mocked subprocess and initialize/
session-new RPC responses, then stop_agent: sanitized declarations and resume
flag are captured after initialize and removed on shutdown. 484 backend tests
pass. This is protocol-lifecycle unit coverage, not an installed third-party
agent handshake or attachment consumption acceptance.

### Installed-agent acceptance recheck

Rechecked PATH for vibe-acp, copilot, claude, codex, gemini, opencode and
agent-client-protocol: none present. Only installed Pi is available. Re-ran
`PYTHONPATH=src .venv/bin/python tools/smoke-pi-sessions.py`: distinct Pi session
creation and restoration pass without sending a model prompt. Third-party ACP
messages discovery/retrieval and real attachment consumption remain blocked on
an installed/authenticated suitable agent; Pi session switching is not substitute
evidence for those acceptance criteria. No credentials or real prompts used.

### Speech release during pending permission

Speech controller remembers stop requested before onstart and repeats stop when
delayed recognition starts, without reporting Listening. This covers browsers
that reject stop before permission/start completes. 16 frontend unit tests,
14 headed Chromium/WebKit mocked speech tests and build/lint pass, including
Space release during pending permission. Live browser microphone service remains
unverified and separate from deterministic controller acceptance.

### Speech background-page cleanup

visibilitychange to hidden now aborts recognition and invalidates callbacks, in
addition to existing blur/session/unmount cleanup. Listener is removed on cleanup.
Sixteen headed Chromium/WebKit mocked-speech tests and build/lint pass, including
synthetic hidden-page event followed by a retained late transcript callback.
Physical mobile backgrounding/live speech service acceptance remains separate.

### Honest context gauge rendering

Context gauge rejects nonnumeric/nonfinite/negative percentages instead of drawing
NaN or fabricated zero usage. Token totals are shown only with valid nonnegative
tokens and positive context window; valid gauges expose an accessible image label.
Four headed Chromium/WebKit context tests and build/lint pass. Compaction/runtime
status integration and complete visual parity remain open.

### Confirmed compaction indicator

Composer displays Compacting context only for explicit available=true,
compacting=true selected-session inspection. Selection changes and unavailable/
failed inspection clear it; no history-based activity inference. Six headed
Chromium/WebKit context/compaction tests and build/lint pass. Indicator follows
existing 15-second idle inspection polling; prompt-lock periods may make live
state unavailable, so this is not continuous compaction telemetry.

### Integrated unified-model/ACP/speech/context checkpoint

At 88a69b1: 484 Python tests, 16 frontend unit tests, build/lint and 162/162
headed Chromium/WebKit tests pass with one worker. Build leaves clean working
tree. Includes default scoped model controls, catalog validation, archived
inspection gating, ACP declaration API/lifecycle, pending/background speech
cleanup, context gauge/compaction and terminal shortcut. No retries/skips added.
External-agent/live-service acceptance and final deployed visual comparisons
remain open; this checkpoint is not overall completion.
