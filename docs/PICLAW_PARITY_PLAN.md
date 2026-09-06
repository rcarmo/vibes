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

### Visible speech activity and service disclosure

Active mic has explicit accent/background/outline; speech status includes deployed
status-dot structure and error styling. Narrow status titles wrap. Mic tooltip
notes browser recognition may use a remote service. Eighteen headed Chromium/
WebKit speech tests and build/lint pass, including mobile status bounds and
active accessibility state. Screenshot equivalence/live service remain open.

### Reproducible mounted picker screenshots

Added desktop 1280x844 and mobile 390x844 mounted picker captures under Playwright
test-results (Chromium/WebKit, four capture tests pass). WebKit images attached
to the working chat for review. These are current-implementation captures, not
approved visual baselines or deployed-reference diffs. Existing bounds/interaction
coverage remains separate; visual equivalence has not been established.

### Stale picker snapshot disclosure

Failed registry polling retains the last snapshot but shows an explicit warning
that activity may be stale; successful refresh clears it. Two headed Chromium/
WebKit polling failure/recovery tests and build/lint pass. Backend remains the
authority for actions; cached activity is not represented as newly confirmed.

### Picker dismissal/focus behavior

Mounted picker Escape restores trigger focus; outside pointer closes without
stealing focus from the clicked target. Outside dismissal is suspended while a
session create/rename/delete dialog is active. Trigger advertises popup type and
expanded state. Thirty headed Chromium/WebKit picker tests and build/lint pass,
including existing dialog focus tests. Visual reference equivalence remains open.

### Modal-safe terminal shortcut

Global terminal toggle respects already-prevented key events and active aria-modal
dialogs, avoiding background layout changes during confirmations. Four headed
Chromium/WebKit shortcut tests and build/lint pass, including blocked toggle in
New session dialog and restored toggle after dismissal. Launcher and final visual
parity remain open.

### Workspace terminal launcher

Moved fixed floating terminal button into WorkspaceExplorer header via deployed
onOpenTerminalTab callback. Opening terminal closes workspace drawer; keyboard
toggle remains. Added narrow/portrait workspace drawer access because previous
CSS hid workspace controls below desktop widths. 22 headed terminal tests and
build/lint pass. Initial tests exposed hidden mobile workspace toggle and an
outdated test close-toggle assumption; fixed both, without forced clicks.
Final full regression and screenshot equivalence remain pending.

### Mobile drawer default regression fix and full checkpoint

Integrated run exposed mobile workspace drawer covering composer by default after
launcher accessibility change. Unset workspace preference now defaults open only
on desktop landscape; explicit saved preference is preserved. Timed-out test
server was stopped before rerun. After fix: full headed Chromium/WebKit suite
174/174 passes with one worker; backend 484 and frontend unit 16 passed in this
checkpoint, build/lint pass. No retries/skips. Final visual comparison and external
acceptance remain open.

### Mobile drawer keyboard dismissal

Escape closes the narrow/portrait workspace drawer and restores toggle focus;
modal dialogs, composer popups and handled events retain priority. Toggle exposes
expanded state. Two headed Chromium/WebKit tests verify dismissal and real typed
composer input afterward; build/lint pass. Initial WebKit fill assertion lost
synthetic fill during focus transition; test now clicks and types through normal
keyboard events. Final visual acceptance remains open.

### Thinking lookup continuation ownership

After asynchronous thinking catalog lookup, unmounted composers no longer start
a mutation. Four headed Chromium/WebKit thinking tests and build/lint pass;
new test waits for confirmed chat switch before releasing held catalog and asserts
zero mutations. Requests already issued before switching remain server-owned and
are not rolled back. Initial test released before async chat switch completed;
corrected test synchronization rather than adding retries.

### Model-state thinking/compaction validation

Model-state reads return null for malformed/oversized/control-character thinking
levels and nonboolean compaction values. Raw nested provider data cannot pass
through these fields. 488 backend tests pass, including four malformed-state
cases. Unknown remains distinct from false/idle; visual/live-agent parity stays open.

### Installed Pi catalog contract smoke

Extended no-prompt installed-Pi smoke to inspect model and thinking catalogs after
session restoration. Actual runtime returned 33 model entries with provider/id
strings and supported thinking-level RPC with list-shaped levels. Smoke and
script lint pass. No model prompts, credentials or model labels emitted; catalog
presence is not authentication/execution acceptance. Third-party ACP remains open.

### Unified context refresh ownership

Context refresh now shares model polling cadence and uses latest-request plus
session-generation guards. Removed legacy default-only context callbacks from
reconnect/turn recovery paths; all refreshes use selected-session helper and clear
unavailable usage. Eight headed context/compaction tests and build/lint pass.
Initial test revealed legacy concurrent refresh paths, now consolidated rather
than relaxing assertions. Context remains inspection-based, not live token streaming.

### Sequential scheduled inspection

Scheduled refresh now awaits model inspection before requesting context, avoiding
self-contention on Pi's intentional single-request lock. Overlapping scheduled
refresh cycles are suppressed; disposed effects do not start context continuation.
Ten headed context/compaction tests and build/lint pass. Event-triggered refreshes
remain independently guarded by backend locks and latest-response ownership.

### Over-capacity context label

Context labels retain reported percentages above 100%; only SVG fill geometry is
clamped. Two headed Chromium/WebKit tests verify 125% label with full bounded
circle; build/lint pass. This prevents hiding over-capacity reports as exactly
100% usage. Final visual/live-agent acceptance remains open.

### Mobile workspace backdrop

Added deployed workspace-drawer-backdrop structure on narrow/portrait screens;
outside pointer dismisses drawer without activating the covered chat. Desktop
layout and popouts omit visible backdrop. Four headed Chromium/WebKit drawer
tests and build/lint pass. Final screenshot equivalence remains open.

### Drawer/editor integration and Escape timing fix

Combined run exposed visible drawer preceding its state-dependent Escape listener.
Listener is now stable for app lifetime and checks current rendered expanded
state before dismissal. After fix, 60 headed Chromium/WebKit editor/terminal tests
pass with one worker; build/lint pass. Initial run had 59 passes/one Escape failure;
no retries or assertion weakening added. Screenshot equivalence remains open.

### Long model identity mobile bounds

Added Chromium/WebKit test with a 220-character model ID at 390px. Existing styles
already keep choice geometry and scroll width within bounds; no CSS change was
needed. Two tests pass. This is targeted overflow acceptance, not full deployed
model picker screenshot equivalence.

### Shared model response sanitization

Catalog, state and mutation responses now share model identity/optional metadata
validation. Mutation thinking values are sanitized before response/broadcast and
binding persistence. 489 backend tests pass, including malformed mutation model
metadata and nested thinking value rejection. Provider URLs/credentials and
invalid optional types remain excluded consistently across response paths.

### Integrated context/drawer/model-validation checkpoint

At b46dc8d, 489 Python tests, 16 frontend unit tests, build/lint and 188/188 headed
Chromium/WebKit tests pass with one worker. Build leaves a clean working tree.
Includes mobile drawer backdrop/Escape, scoped context refresh sequencing,
over-capacity labels and shared model-response validation. No retries/skips.
Final deployed visual comparison, remaining capability presentation and external
agent/live-service acceptance remain open; no overall completion claim.

### Picker lifecycle pill nesting alignment

Moved status/queued pills inside deployed compose-session-row-content and
compose-session-row-pills wrapper beside metadata, rather than below the row.
Archived/current item classes now activate existing deployed styling; archived
pill uses the matching archived class. Thirty headed picker tests and build/lint
pass, including refreshed captures and long-name mobile bounds. No full visual
equivalence claim; remaining deviations and external acceptance stay open.

### Picker pending-action serialization

Picker gates rapid action invocation with a synchronous pending ref, exposes
aria-busy and Updating session status, and releases the gate on failure/success.
32 headed Chromium/WebKit picker tests and build/lint pass, including duplicate
Enter suppression and retry after rejection. This prevents duplicate concurrent
UI actions, not exactly-once server execution across network failures/reopens.

### Visual reference inventory and acceptance gap

Inspected saved /workspace/tmp/piclaw-classic-reference and piclaw-full-reference
artifacts. They contain Chromium/WebKit desktop/phone/tablet light/dark main-shell,
workspace and (full set) search captures, plus DOM rectangles. They do not contain
session-picker/model-picker open-state captures. Current picker screenshots cannot
therefore be called matched baselines. Deployed compose-box.ts remains the popup
DOM reference, but a rendered popup comparison is still required.

Concrete phone reference: webkit-phone-dark.json has 390x844 shell/container,
390x102 composer at y≈742, 370x50 textarea and 370x26 footer. These dimensions
are reference observations, not universal acceptance assertions: seeded content,
model/status controls and viewport state must be matched before comparing.
Next visual acceptance must capture matching deployed/current popup fixtures,
record deliberate session-ID/display-name and local lifecycle-action deviations,
and review screenshots rather than just comparing class names or viewport bounds.

### Deployed model-popup reference captured

Reused isolated classic.test route fixture against installed 2.15.3 runtime assets
(no live chat access) and opened .compose-model-hint-btn at 1280x844. Capture:
/workspace/tmp/piclaw-classic-model-desktop.png, attached to working chat. Browser
reported no page errors; only unhandled asset was favicon.ico. Fixture has one
model and no live runtime. Reference popup visibly includes SEARCH MODELS, model
count, CURRENT grouping, pin control and Open Models settings. Current Python
popup lacks those grouping/pin/settings semantics, so model visual parity remains
open rather than treating search/keyboard support as full equivalence.

### Model count/current grouping

Model picker shows filtered model count and separates the confirmed current
choice from other reported choices, retaining existing keyboard navigation and
scoped selection. Twenty-six headed model/thinking/catalog tests and build/lint
pass. Pin persistence and settings surface remain unimplemented; no unavailable
settings button exposed. Exact deployed grouping/style comparison remains open.

### Browser-local model pins

Model picker supports pin/unpin controls and Current/Pinned/Other grouping.
Only current catalog entries are rendered; stored pins never establish availability
or mutate active model. Pins are bounded to 100 browser-local identities, malformed
storage is ignored and failed writes disclosed. 17 frontend unit tests, 26 headed
model tests and build/lint pass. Server-synced preferences/settings and full visual
comparison remain open; pin persistence is explicitly browser-local.

### Model pin browser acceptance

Chromium/WebKit verify pin action makes no model mutation, survives page reload,
and does not render a stored favorite absent from the refreshed backend catalog.
Two targeted browser tests pass. Browser-local preference remains distinct from
server-synced settings and runtime model availability.

### Separate pin persistence errors

Failed browser pin storage now has its own temporary-preference warning rather
than contaminating catalog error/count/retry state. Valid choices remain usable.
Two headed Chromium/WebKit storage-denial tests and build/lint pass. Server-synced
preferences and full visual parity remain open.

### Model pin storage access guard

Pin callers now acquire localStorage inside a guarded helper, covering browsers
that throw on property access before load/save helpers run. Eighteen frontend
unit tests and build/lint pass, including SecurityError-style getter rejection.
This protects the pin feature; it is not a claim that every legacy app storage
access has been audited.

### Deployed session-popup reference captured

Isolated classic.test fixture now renders two synthetic chats through deployed
2.15.3 assets and opens session-switcher. Desktop capture at
/workspace/tmp/piclaw-classic-session-desktop.png attached to chat; no page errors,
only missing favicon. Reference shows search close control, Current/Other Sessions
sections, inline current/active pills, and New branch/New root/Rename current
footer actions. Synthetic fields do not establish backend lifecycle equivalence.
Python has per-row lifecycle actions and a single New session action; these are
remaining explicit interaction deviations, not approved screenshot equivalence.

### Deployed picker close control

Added compose-session-popup-close × button beside search, matching deployed DOM
and existing styles. Uses same focus-restoring close callback as Escape.
34 headed Chromium/WebKit picker tests and build/lint pass, including explicit
close activation. Branch/root footer semantics and final visual comparison remain
open.

### Picker child-session creation

New branch footer action creates an empty session with parent_id fixed to the
selected session when opened. Existing New session creates a root. Backend
parent support reused; no history copy or provider conversation fork implied,
with explicit action tooltip. 36 headed picker tests and build/lint pass, including
persisted parent and zero-message child verification. Deployed fork semantics and
final visual equivalence remain explicit deviations/open acceptance.

### Visible empty-branch disclosure

Branch creation dialog names its parent and visibly states that conversation
history is not copied, including touch users without tooltips. Root creation
omits that disclosure. Four headed create/branch tests and build/lint pass.
This is explicit metadata-child behavior, not provider conversation fork parity.

### Rename-current footer parity

Added deployed Rename current footer action, gated by callback/current registry
presence and targeting currentId independently of search highlight/filter.
38 headed picker tests and build/lint pass, including filtered-current dialog
identity. Existing per-row lifecycle actions remain deliberate local additions;
full visual comparison still open.

### Explicit root creation footer

Root creation footer now reads New root… with independent-root tooltip, matching
deployed distinction from New branch. Dialog retains New session title. Six headed
root/branch/modal tests and build/lint pass. Empty-child versus provider fork
semantics remain documented; visual equivalence not yet claimed.

### Deployed/current mobile popup geometry comparison

Captured deployed 2.15.3 session popup in headed WebKit at 390x844 using isolated
fixture: x=8, y=8, width=374, height=828, no page errors. Attached reference image.
Current Chromium/WebKit capture tests now assert those same popup bounds (four
capture tests pass). This verifies outer popup geometry only; differing seeded
sessions, row actions and metadata prevent pixel-equivalence claims. Internal
layout/state comparison remains open.

### Separate selected-session badge

Selected row now displays deployed Current pill separately from runtime Idle/
Running and queued counts. Forty headed picker tests and build/lint pass,
including explicit Current+Idle without active-turn badge. Selection remains UI
state, not evidence of a running backend. Final visual acceptance stays open.

### Mobile combined-status row readability

New Current+Running+123 queued fixture exposed name column shrinking to 89px.
Narrow picker now puts metadata at full row width with wrapping pills below it;
desktop inline structure remains. 42 headed picker tests and build/lint pass,
including minimum readable name area and all badge bounds. This responsive
adaptation is deliberate; exact deployed multi-badge screenshot parity is open.

### Unknown runtime status is not idle

Picker now requires explicit boolean is_running to label Running/Idle; missing
or malformed flags render Status unavailable. Archived state retains precedence.
44 headed Chromium/WebKit picker tests and build/lint pass, including missing
runtime metadata. Normal registry boolean responses are unchanged.

### Speech functional acceptance reconciliation

At e67fcfc, reran speech controller units (5 passed) and headed Chromium/WebKit
speech workflows (18 passed). Capability detection, toggle/Space/pointer hold,
permission/error handling, delayed-start release, session/manual-edit isolation,
blur/hidden/unmount cleanup, accessible active state and mobile status bounds are
implemented and locally verified. Functional speech implementation is complete.
Exact deployed visual comparison and real microphone/browser-vendor service
acceptance are still unverified and remain explicit separate checklist work.

### Mobile footer action bounds

Verified New branch, New root and Rename current footer controls remain visible
and inside mobile popup horizontally and vertically at 390x844 in Chromium and
WebKit (two tests pass). Existing styles suffice; no CSS workaround added. This
checks the complete footer after recent additions, not full pixel equivalence.

### Dialog synchronous submission guard

Name/create and deletion dialogs now use immediate pending refs, preventing
same-tick duplicate submits before busy rerender. Failed requests release the
guard; successful actions close as before. Eight headed dialog tests and build/
lint pass, including double synthetic submit with exactly one callback per dialog.
This guards UI invocation, not network-level exactly-once semantics.

### Child creation parent lifecycle guard

Parent existence/archive checks now run inside child-creation transaction.
Archived parents must be restored before adding children; rejected creation leaves
registry unchanged. 490 backend tests pass, including archive/reject/restore/create
sequence. Child creation remains metadata-only, not a provider history fork.

### Integrated pins/picker-footer/parent-guard checkpoint

At 2314dd4: 490 Python tests, 18 frontend unit tests, build/lint and 210/210 headed
Chromium/WebKit tests pass with one worker. Build leaves clean working tree.
Includes model pins/storage failures, picker lifecycle badges and mobile layout,
root/child/rename footer controls, dialog submit guards and parent lifecycle checks.
No retries/skips. Full visual acceptance, remaining settings/capability presentation,
provider fork semantics and external-agent/live-service acceptance remain open.

### Registry metadata cannot overwrite scoped model

Removed legacy loadAgents assignment of configured/default model into current
composer model state. Agent registry still supplies branding, but scoped inspection
and confirmed mutation own live model labels. Four headed registry/scoped-model
tests and build/lint pass. ACP capability presentation remains open; this closes
an identified metadata/live-state boundary rather than displaying unverified data.

### Legacy model-event inspection generation

Default-only legacy model_changed events now advance model inspection generation,
matching scoped mutation events, so pre-event polling cannot overwrite confirmed
command changes. 32 headed model/thinking/catalog regression tests and build/lint
pass. Dedicated live SSE race acceptance remains unverified; current change shares
the existing generation guard rather than inventing a second mechanism.

### Model mutation text contract

Model mutation input reuses validated text contract: whitespace-only and control-
character provider/model/thinking values return 400 before Pi RPC. 494 backend
tests pass, including four no-RPC malformed-input cases. Full external model
acceptance remains separate from input validation.

### Mounted stale-parent rejection acceptance

Chromium/WebKit test archives selected parent through API after branch dialog
opens, then verifies creation rejection, retained typed name, and no fallback root
or child insertion. Two targeted tests pass. This covers stale UI/backend lifecycle
boundary; provider history fork semantics remain out of this metadata-only action.

## Current acceptance map (supersedes historical provisional notes)

The chronological entries above intentionally retain failures and intermediate
limitations. Do not read an early provisional note as current implementation state.

- **Session picker functionality:** groups, search, keyboard navigation, pins,
  current/runtime/queued/history distinction, stale snapshot disclosure, root/
  empty-child creation, rename/delete dialogs and focus lifecycle implemented.
  Mobile popup outer geometry matches rendered deployed fixture. Still open:
  matched-content visual review and approval of local row-action/empty-child
  deviations. Provider history fork is not implemented.
- **Model controls:** all composer actions use scoped locked APIs; search/count/
  current/pinned grouping, browser-local pins, retry/errors and keyboard control
  implemented. Still open: server-synced preferences/Models settings, ACP model
  configuration controls where actually supported, final rendered comparison.
- **Context/status:** scoped inspection, periodic ordered refresh, stale-response
  rejection, validated gauge and confirmed compaction indicator implemented.
  Still open: continuous runtime/compaction telemetry beyond idle inspection and
  capability presentation. Registry declarations are not execution evidence.
- **Terminal host:** shared editor column, standalone/popout, resizing, workspace
  launcher, mobile drawer/backdrop and keyboard toggle implemented and tested.
  Still open: matched deployed/current host screenshots and remaining responsive
  layout deviations. No longer a fixed bottom overlay.
- **Speech:** functional implementation checked off separately; live microphone/
  browser service and exact visual reference acceptance remain unverified.
- **External acceptance:** no installed third-party ACP executable found. Installed
  Pi no-prompt session and catalog smoke passes; actual prompt/attachment/MCP
  consumption has not been established.

Latest full checkpoint is d01e4f5 (490 backend, 18 frontend unit, 210 browser tests).
Later targeted validations do not imply a newer full-suite total. Overall goal
remains open until unmet criteria are implemented/verified or explicitly revised
by the user—not merely because many tests pass.

### Browser-tab pin synchronization

Composer listens for model-pin storage changes/removal and refreshes local pin
state, removing listener on unmount. Two headed Chromium/WebKit tests use a second
real browser tab to update/remove pins and verify first-tab controls; build/lint
pass. This is same-browser storage synchronization, not server-synced settings.

### ACP declaration presentation

Default composer has collapsible Agent-reported capabilities for running ACP
registry entries with explicit boolean declarations. Supported/unsupported are
labelled as reported; explanatory text disclaims execution/session availability.
Hidden for other sessions, stopped agents and absent declarations; no controls
are enabled by claims. Two headed browser tests and build/lint pass. This local
read-only details UI is an explicit deviation pending visual review; registry
refresh cadence and real-agent consumption acceptance remain open.

### Capability panel unavailable-state acceptance

Four headed Chromium/WebKit capability tests pass, including rerender from
reported capability to stopped, absent and malformed declarations. Panel removes
claims in each unavailable case rather than retaining stale details. This verifies
component input handling, not agent-list refresh cadence or real capability use.

### Agent declaration refresh lifecycle

Registry refreshes every 15 seconds; latest-request guard rejects older responses.
Failed refresh clears reported capability claims while preserving branding/history
metadata. Cleanup invalidates pending refreshes. Six headed capability tests and
build/lint pass, including visible declaration removal after polling failure.
This remains sampled registry state, not real-agent capability execution evidence.

### Registry polling respects Pi stream ownership

Agent-list model resolution now uses guarded default-session inspection rather
than raw get_state RPC. Busy/mismatched contexts retain configured registry model
metadata (never assigned to composer live label). 495 backend tests pass,
including no raw RPC and explicit default inspection when unavailable. This
protects prompt stream ownership during periodic registry refresh.

### Local row-action visual consistency

Reviewed fresh current/deployed mobile picker captures. Local per-row rename/
archive/delete additions used unthemed native buttons; they now reuse deployed
compose-model-popup-btn styling, with danger treatment on delete. Fifty headed
picker tests and build/lint pass, including mobile button bounds. Extra row actions,
metadata density and fixture differences remain documented deviations; this is
not an approval of full screenshot equivalence.

### Explicit model picker close

Added labelled close control using existing popup-header/close styles and trigger
focus restoration. Two headed Chromium/WebKit close-control tests and build/lint
pass. Final rendered model comparison and settings integration remain open.

### Integrated registry/capability/picker checkpoint

At e936843: 495 Python tests, 18 frontend unit tests, build/lint and 224/224 headed
Chromium/WebKit tests pass with one worker. Build leaves clean tree. Includes
periodic agent declarations, guarded registry inspection, cross-tab pins, stale
parent UI rejection and latest picker styling/close controls. No retries/skips.
Final visual comparison, server-side model settings and external-agent/live-service
acceptance remain open; passing regression is not overall plan completion.

### Server model preference persistence foundation

Schema v7 adds a singleton instance-wide model pin preference row. Store validates
at most 100 bounded provider/model labels, deduplicates and updates transactionally;
invalid writes preserve previous values. Reconnect persistence verified. 504
backend tests pass (existing migration assertion updated from v6 to v7). No API/UI
wiring yet; browser-local pins remain current UI source until migration is designed.
Preferences store no credentials and confer no model availability.

### Instance model-pin preferences API

GET/PUT /model-preferences expose bounded persisted pins with scope=instance and
no-store responses. PUT accepts exactly pins, validates before write and emits
model_preferences_changed. No runtime mutation occurs. 505 backend tests pass,
including deduplication, malformed/oversized writes preserving prior values and
no Pi mutation. Uses existing local deployment trust boundary, not per-user auth;
UI remains browser-local until explicit migration/integration.

### Explicit instance/browser pin transfer

Model popup exposes Instance pin preferences details with Load/Save controls and
clear replacement scope. Load replaces browser pins; Save replaces instance pins;
neither happens automatically. Busy/error/success feedback and unmounted callback
guard included. Two headed Chromium/WebKit tests and build/lint pass against real
preferences API, verifying browser edits do not silently overwrite instance state.
This explicit transfer UI is not a complete deployed Models settings replacement.

### Instance pin load revision guard

Local toggles and cross-tab updates advance pin revision. Delayed instance Load
response is not applied over newer browser edits, with explicit status feedback.
Four headed instance-pin tests and build/lint pass, including held load followed
by local pin change. Save remains explicit snapshot replacement at invocation.

### Existing v6 database preference migration

Reconstructed v6 schema test upgrades through normal connect, preserving session,
message and confirmed Pi binding/model/thinking metadata. New preferences start
empty, persist after write and survive another reconnect. 506 backend tests pass.
No production database modified for this verification.

### Instance pin failure/retry acceptance

Failed load preserves browser pins and releases busy gate; successful save now
clears previous synchronization error instead of showing contradictory success
and failure. Six headed instance-pin tests and build/lint pass, including explicit
503 then successful retry. Full settings parity remains open.

### Conditional instance preference updates

Preferences responses include content ETag; PUT with If-Match compares current
pins inside transaction and rejects stale snapshot with 412 without writing.
507 backend tests pass, including competing stale update. Unconditional PUT is
retained for explicit last-write replacement compatibility; current UI does not
yet supply If-Match, so automatic conflict protection there is not claimed.

### Conditional pin saves in composer

Preference helpers retain response ETags; composer requires successful instance
load before save and supplies If-Match. Concurrent server changes produce visible
412 conflict without overwrite. Eight headed instance-pin tests and build/lint
pass, including real API concurrent change. Unconditional API writes remain for
explicit trusted clients; composer no longer uses them. Full Models settings
parity remains open.

### Integrated schema-v7/conditional-preferences checkpoint

At 085ca3f: 507 Python tests, 18 frontend unit tests, build/lint and 232/232 headed
Chromium/WebKit tests pass with one worker. Build leaves clean tree. Includes v6
migration preservation, preference API/ETags, explicit load/save, revision guards
and conflict/failure handling. No retries/skips. Full deployed Models settings,
visual acceptance and real-agent/live-service criteria remain open.

### Visible preference-save prerequisite

Save instance pins is disabled until a response supplies a usable ETag and its
tooltip explains loading first. Missing ETag cannot silently enable conditional
save. Eight headed instance-pin tests and build/lint pass, including disabled
initial Save followed by successful loaded-version update.

### Preference conflict recovery state

Fetch wrapper preserves HTTP status on errors. Instance-pin 412 invalidates loaded
ETag and disables Save until reload, preventing repeated known-stale submissions.
18 frontend unit tests, eight headed instance-pin tests and build/lint pass;
conflict test verifies disabled Save followed by re-enabled control after Load.

### Expanded preference mobile reachability

At 390x844 with 20 catalog entries, expanded instance preferences and Load/Save/
Close controls remain inside viewport in Chromium/WebKit (two tests pass). No
layout change needed. This is bounded mobile acceptance, not a full Models
settings/reference screenshot comparison.

### Current model-popup comparison capture

Added 1280x844 capture with same test/review-model catalog as deployed reference;
Current group and model choice verified in Chromium/WebKit (two tests pass).
Current Chromium image attached to working chat. Surrounding timeline fixture and
popup footer differ: explicit instance preference transfer/Next model are not the
deployed Models settings surface. Capture is review evidence, not pixel baseline
approval or full settings parity.

### Direct supported thinking selection

Model popup offers explicit thinking-level select only when catalog reports
choices. Selection re-fetches supported levels before mutation, rejects removed
choices and shares scoped mutation/unmount guard with cycling. Six headed thinking
tests and build/lint pass, including direct off-to-high selection. Native select
is a documented local interaction adaptation pending full reference styling review.

### Removed thinking choice acceptance

Eight headed Chromium/WebKit thinking tests pass, including catalog changing from
off/high to off between popup load and selection. Removed high choice produces
visible error with zero model mutation requests. This validates stale-choice
rejection, not provider execution acceptance.

### Refresh thinking choices after revalidation

Thinking preflight now updates displayed catalog/model options before validating
requested level, removing stale choices even when selection is rejected. Eight
headed thinking tests and build/lint pass; removed-high case now verifies option
removal and restoration of confirmed off selection, with no mutation.

### Reference reassessment acceptance

Reference reassessment is complete: the stale workspace checkout was rejected,
deployed 2.15.3 classic source-map extracts selected, upstream xterm direction
confirmed, and isolated rendered model/session popup references captured. Ghostty
is optional; terminal handoff/PTY assumptions were corrected and tested. This
closes reference selection/reassessment only, not remaining UI implementation or
visual-equivalence acceptance. Removed an embedded credential from the local Git
remote URL during repository inspection; remote now uses the public HTTPS URL.

### Immediate model mutation guard

Model selection and thinking changes share a synchronous pending ref, preventing
same-tick duplicate invocation before disabled state renders. Guard releases in
finally on success/failure. Ten headed duplicate/thinking tests and build/lint
pass, including two synchronous button clicks with one mutation. Backend locking
remains authoritative; this is not network-level exactly-once delivery.

### Model pin keyboard shortcut

Alt+Enter on a focused model choice toggles its browser pin without selection;
repeats ignored and pin controls advertise shortcut. Two headed Chromium/WebKit
shortcut tests and build/lint pass, verifying zero model mutations. Full settings
and visual acceptance remain open.

### Model pin regrouping focus

Keyboard pin/unpin restores focus by stable model identity after the row moves
between groups. Two headed Chromium/WebKit shortcut tests and build/lint pass,
including pin then unpin with focus retained and no model mutation.

### Failed thinking selection confirmation

Chromium/WebKit verify 409 thinking mutation leaves selector at confirmed off
level, shows Context busy error and re-enables control. Two targeted tests pass;
existing controlled-select behavior already meets this requirement, so no code
change needed. Actual provider execution acceptance remains separate.

### Native thinking selector keyboard ownership

Model popup arrow navigation no longer intercepts events from native select.
Twelve headed thinking tests and build/lint pass, including unprevented ArrowDown
and retained select focus. Model-choice arrows and Escape behavior remain intact.

### Unique selectable catalog identities

Scoped model catalog deduplicates provider/id tuples preserving first validated
entry; same model ID from different providers remains distinct. Existing 500-input
bound retained and tested with unique entries. 508 backend tests pass, including
duplicate identity handling. Prevents duplicate UI keys/count inflation without
asserting provider availability.

### Terminal host functional acceptance reconciliation

Shared editor/dock column, workspace launcher, mobile drawer/backdrop, splitter,
shortcut and popout functionality are implemented. Combined acceptance initially
had 59 passes/one WebKit missing-tab failure: editor helper opened successive files
without waiting for the requested tab. It now waits for that visible tab before
continuing. Rerun: 60 headed Chromium/WebKit editor/terminal tests pass, no retries.
Functional host implementation is complete; exact deployed/current terminal host
screenshots and approval of responsive deviations remain separate open work.

### Isolated deployed terminal host capture

Opened deployed 2.15.3 terminal host via Ctrl+Backquote in isolated classic.test
fixture at 1280x844. /terminal/session reports disabled so no PTY/live network
session is created. Screenshot /workspace/tmp/piclaw-classic-terminal-desktop.png
attached. Workspace-actions click was unavailable in this fixture; keyboard path
successfully renders TERMINAL host. This supplies disconnected host reference,
not transport acceptance or matched screenshot approval.

### Corrected terminal reference module serving

Fixed isolated capture fixture to serve .mjs as application/javascript. Recapture
loads xterm without dynamic-import failure and displays intentional Unavailable
status from disabled terminal API. No page errors; only favicon missing. Corrected
reference attached, superseding earlier import-error screenshot. No shell/live
connection used; full matched host comparison remains open.

### Measured desktop terminal column parity

Deployed isolated 1280x844 reference measures editor column x=0,w=512,h=844 and
chat x=516,w=764,h=844. Python startup overrode CSS 40vw with 280px; unset editor
width now uses 40% viewport, retaining explicit saved widths. Two headed Chromium/
WebKit geometry tests and build/lint pass against reference values. Dock interior
still differs (deployed top splitter offset 4px); full visual acceptance remains
open and editor regression must be rerun after default-width change.

### Default-column editor/terminal regression

After 40%-width default alignment, all 62 headed Chromium/WebKit editor-tab and
terminal tests pass with one worker. Covers preview/tab activation, popouts,
terminal transfer/recovery, mobile drawer and reference column geometry. No retry
or skip added. Interior dock visual comparison remains open.

### Terminal header control alignment

Terminal header uses deployed 12px/16-viewBox popout and close SVG paths/strokes;
decorative icons are aria-hidden. Added deployed header reattach action using
existing transfer handler, retaining body recovery control. 28 headed terminal
tests and build/lint pass. Full dock screenshot comparison remains open.

### Header reattach transport acceptance

Existing real-shell popout handoff test now returns through Reattach terminal
header control and verifies preserved environment state plus closed popup.
Body Reattach here remains covered by closed-popup recovery test. Four headed
Chromium/WebKit tests pass across both paths; no transport implementation change.

### Terminal transfer action serialization

Detach and both reattach controls share synchronous pending guard; visible transfer
buttons disable until completion/failure. Prevents overlapping header/body handoff
requests before busy rerender. 28 headed terminal regression tests and build/lint
pass; dedicated simultaneous-control stress acceptance remains unverified.

### Simultaneous reattach controls acceptance

Two headed Chromium/WebKit tests activate header/body reattach synchronously,
hold host handoff request, verify both disabled and exactly one host request,
then verify successful reconnect/popup closure. Initial count also included the
vendored pane's legitimate post-reconnect standby-token request; test now separates
it by x-piclaw-terminal-client header rather than suppressing that protocol work.

### Terminal transfer continuation ownership

Unmounted hosts discard reattach continuation before mount and close a pending
blank detach window instead of navigating it after disposal. Two headed Chromium/
WebKit tests and build/lint pass, closing host during held reattach while existing
popup stays connected. Server-issued unused handoff remains bounded by expiry.

### Settled handoff-response unmount assertion

Strengthened close-during-reattach test to await actual HTTP response completion
and browser frames before asserting no host/xterm remount and live popup retained.
Two headed Chromium/WebKit tests pass. Prior immediate assertion could precede
response processing; new synchronization exercises the intended continuation.

### Pending blank popout cleanup

Host tracks blank window separately while detach handoff is pending and closes it
on unmount; successfully transferred popup is not closed by host cleanup. Four
headed handoff/unmount regression tests and build/lint pass. Dedicated blocked-
detach blank-window coverage subsequently passed in Chromium/WebKit: the blank
window closes before the held handoff request is released. Consolidated terminal
suite: 34 passed (headed, one worker, both browsers). Reattach settled-response
coverage remains included. No active detached shell is intentionally terminated
by this cleanup. These functional checks do not establish visual equivalence.

### Integrated regression checkpoint — 2026-09-06

After terminal lifecycle slice 3e148b8, consolidated validation completed:

- `make check PYTHON=.venv/bin/python`: 508 passed.
- `bun test tests/frontend`: 18 passed, 73 assertions.
- `make build-frontend lint-frontend`: passed.
- `xvfb-run -a bun x playwright test --headed --workers=1`: 256 passed
  across Chromium/WebKit (5.0 minutes), including desktop/mobile fixtures.

This supersedes the earlier 232-browser-test checkpoint. No test failure was
retried in this run. Automated fixture coverage does not establish deployed
visual equivalence, live speech service, external ACP-agent discovery, or real
attachment consumption. Those acceptance gates remain open.

### Reference-sized terminal capture

Added 1280x844 terminal screenshot case alongside existing 1440x1000 desktop and
390x844 mobile cases. Two headed Chromium/WebKit tests pass. This removes viewport
mismatch against the deployed 1280x844 reference, but not fixture/state mismatch:
local terminal is Connected with shell output, deployed isolated terminal reports
Unavailable. Deployed dock starts at y=4 (height 840); local standalone host has no
top splitter and fills the column. Shared local editor/terminal does render its
4px resize splitter. Do not add a nonfunctional standalone separator merely to
hide this difference: standalone top gutter/host markup remains a visual review
item. Chat content and header controls also differ between these fixtures, so
whole-page pixel equality is not an acceptance metric yet.

### Disabled-state comparison fixture

Added 1280x844 Unavailable terminal capture (Chromium/WebKit: two passed).
Initial fixture disabled capability at startup, correctly hiding the launcher;
corrected fixture advertises launcher then simulates capability loss on mount.
This tests the real unavailable renderer rather than forcing DOM visibility.
Deployed source-map inspection confirms app-main-shell-render.ts renders a sibling
`dock-splitter` whenever dock panes are visible, even without editorOpen. Local
splitter is nested and only present with an editor. This identifies the source of
the 4px standalone offset; structural equivalence remains open, not approved.

### Deployed terminal icon geometry

Matched pop-out rounded rectangle/arrow, reattach rounded rectangle/plus, and
close line geometry to deployed app-main-shell-render.ts source-map content.
Matched detached explanatory text. Kept decorative aria-hidden attributes,
explicit reattach button type, transfer disabling, and accessible heading as
intentional local safeguards; detached wrapper class alignment remains open.
Build/lint and all 38 headed terminal tests pass across Chromium/WebKit.

### Detached terminal card markup and styling

Replaced unmatched detached wrapper/action classes with deployed editor-empty-state
body/actions/button structure and copied its editor.css card styles. Kept h3 title
semantics (zero margin), explicit button type and disabled-state feedback as
accessibility/concurrency deviations. Added DOM hierarchy assertion to live-shell
handoff test; concurrent-control test now targets the deployed button class.
Build/lint and 38 headed Chromium/WebKit terminal tests pass. Standalone splitter
placement and whole-host visual acceptance remain open.

### Session-picker boundary navigation

Deployed compose-box.ts supports Home/End in session popup navigation. Added those
keys to local active-option navigation and browser assertions. Button targets no
longer change list selection on arrow keys; native button focus remains intact.
Build/lint and 50 headed Chromium/WebKit session-picker tests pass. PageUp/Down,
Tab activation and non-search typeahead still differ from deployed behavior;
these interaction differences and visual acceptance remain open.

### Session-picker page and wrapping navigation

Matched deployed moveSessionPickerIndex rules: arrows wrap, PageUp/PageDown move
by eight and clamp, Home/End retain boundary behavior. New 12-entry browser test
checks both directions, wrapping and empty-filter safety. All 52 headed picker
tests and build/lint pass. Tab activation and non-search typeahead remain open;
page navigation is no longer a known deviation.

### Session-picker Tab selection and composition safety

Unmodified Tab in the search field now activates its highlighted match. IME
composition key events bypass picker commands. Intentional accessibility deviation:
Shift+Tab, modified Tab, action-button Tab, and empty-result Tab retain native focus
navigation rather than selecting a session. New browser coverage checks composition,
reverse Tab, selected-match Tab and empty-result focus escape. Build/lint and all
54 headed Chromium/WebKit picker tests pass. Non-search typeahead and final visual
acceptance remain open.

### Non-search session typeahead

Added focusable popup root and non-search printable-key label matching, following
deployed normalization, current-match retention, prefix-before-substring fallback,
and 700ms buffer expiry. Navigation clears the buffer; modifiers/IME bypass it.
Browser tests cover multi-character matching, navigation reset and unchanged search
text; expiry-specific timing acceptance is not separately exercised. Build/lint
and all 56 headed Chromium/WebKit picker tests pass. Visual acceptance remains open.

### Typeahead expiry boundary acceptance

Extended non-search browser test with Playwright fixed Date clock: exactly 700ms
retains the prefix; 701ms since the latest key starts a new query. Both headed
Chromium/WebKit tests pass without sleeps or retries. This closes the previously
noted expiry-specific test gap; no implementation change.

### Session-picker search header structure

Matched deployed label/close header followed by sibling search input, linked the
label, and disabled browser autocomplete. Placeholder truthfully advertises local
name/ID filtering rather than unsupported model/state search. Combobox ARIA stays.
DOM assertions verify hierarchy. Empty-result Tab follows new document order
(past search rather than back to close); test checks focus exits search without
selection. Build/lint and 56 headed Chromium/WebKit picker tests pass, including
desktop/mobile capture cases. Full visual acceptance remains open.

### Post-picker integrated acceptance checkpoint — 2026-09-06

At ab11cc9, all 266 headed Chromium/WebKit tests passed in a single-worker run
(5.1m), without retries. Backend: 508 passed; frontend: 18 passed/73 assertions.
Latest build/lint passed with the header slice. Installed Pi smoke again verified
session switching/restoration and 33 model catalog entries plus thinking RPC.
No prompt was sent; catalog availability is not provider authentication/execution.

Remaining acceptance is not resolved by these counts:
- Visual: terminal standalone sibling splitter/4px offset, and matched deployed
  model/status/settings and grouped-picker comparisons remain unapproved.
- Agent interoperability: installed-Pi RPC smoke is not third-party ACP messages
  discovery/retrieval or real attachment consumption. PATH probes for
  claude-agent-acp, codex-acp, gemini and opencode found no executable.
- Speech: mocked recognition does not verify microphone permission or a live
  browser transcription service.

Read-only delegate audit was unavailable under current model policy; this review
was performed locally, not independently validated by another model.

### Standalone terminal dock offset alignment

Added deployed sibling dock-splitter gutter for standalone main-window terminal;
flex sizing now leaves dock y=4,height=840 at 1280x844, matching reference geometry.
Gutter is aria-hidden, unfocusable and non-draggable because no editor exists to
resize: intentional interaction deviation from deployed handlers. Popout remains
full-height without gutter. Shared editor/terminal retains existing functional
nested splitter (structural deviation remains). Geometry test checks sibling
hierarchy plus offset/height. Build/lint and all 72 headed Chromium/WebKit terminal
and editor-tab tests pass, including mobile and handoff workflows. Full visual
acceptance remains separate; standalone 4px offset is no longer outstanding.

### Terminal header reference measurements

Re-ran isolated deployed classic fixture and collected computed styles: standalone
header y=4, height=27, padding=4px 16px. Added matching local unavailable-state
assertions; both headed Chromium/WebKit cases pass. Comparison narrows the known
geometry gap: column, dock and header dimensions now match at 1280x844. This does
not approve remaining typography/theme or full-page differences, nor mobile/shared
host visual equivalence. Reference probe is under /workspace/tmp and not runtime
code; no transport behavior changed.

### Mobile terminal reference comparison (390x844)

Deployed disabled-terminal fixture has no page errors (favicon 404 only): editor
column 200x844, dock y=4,height=840, chat x=204,width=186. Header padding is 4px 12px.
Local intentionally stacks the terminal above full-width chat (390px each), with
45dvh terminal column. Retain this responsive deviation for composer usability;
not a claim of exact deployed mobile equivalence or user approval. New unavailable-
state Chromium/WebKit tests verify full widths, vertical separation and visible
composer. Both pass after correcting a nonexistent textarea selector in the test;
no production behavior changed. Reference screenshot is in workspace tmp.

### Model picker composition guard

Model popup keyboard commands now ignore IME composition/keyCode 229 before
navigation, pin shortcuts or dismissal. Browser regression dispatches composing
ArrowDown/Escape and checks search retains focus, then verifies normal navigation
and dismissal. Build/lint and all 88 headed Chromium/WebKit session-switching tests
pass. Model visual matching and live execution acceptance remain open.

### Model/thinking visual fixtures

Added 1280x844 and 390x844 captures with deterministic available catalog/current
model/thinking-level capabilities. Browser checks verify model choices and thinking
selector are visible and entire popup stays within viewport. Four headed Chromium/
WebKit cases pass. These are local review artifacts, not deployed visual approval
or evidence of provider execution; no model mutation is performed.

### Model catalogue gap clarification and clear search

Direct deployed model-picker.ts inspection confirms a dedicated catalogue header,
combobox/listbox, provider grouping, capability/pricing badges and Models-settings
footer. Local menu and inline thinking/preferences are not that structure; this
is substantive remaining visual/interaction work, not just approval. Added explicit
clear-search action restoring focus and unfiltered choices, matching deployed
behavior while retaining truthful local menu roles. Styling remains local until
catalogue migration. Build/lint and 10 headed retry/capture tests pass across both
browsers; empty-query control removal and focus restoration are asserted.

### Provider subgroup migration

Current/Pinned/Other model sections now contain provider-labelled groups using
deployed catalogue group classes and heading styles. Model identities remain
unchanged; ordering preserves first-seen provider/catalog order. Desktop/mobile
capture assertions verify Current/test and Other/test subgroup contents. Found and
closed a missing brace in previously copied detached-card focus CSS, restoring
intended top-level title/disabled rules. Build/lint, 132 combined model/terminal
browser tests, then four subgroup capture checks passed. Full catalogue roles,
option metadata and Models-settings footer remain unfinished.

### Model display names and canonical keys

Picker now renders validated backend model names plus secondary canonical key,
using deployed catalogue content/name/key classes. Search includes both name and
provider/id. Accessible choice identity and mutation identity remain canonical;
missing names fall back to the key. No fabricated pricing/capability metadata.
New browser fixture verifies friendly-name search and visible canonical key.
Build/lint and all 94 headed model/session-switching tests pass. Catalogue role
migration and settings footer remain unfinished.

### Validated catalogue capability metadata

Model rows expose explicit reasoning=true and positive integer contextWindow using
catalogue badge classes. Missing fields render no badge; context size is catalogue
capacity, not measured usage or successful execution. Pricing stays absent because
backend does not supply validated pricing. Badges wrap locally for narrow widths
rather than deployed nowrap truncation. Browser checks cover populated and missing
metadata. Build/lint and eight headed name/capture cases pass across both browsers.

### Model chooser semantic migration

Search now exposes combobox/listbox linkage; canonical choices expose option and
aria-selected rather than menuitem. Arrow navigation still moves DOM focus onto
options (intentional interim difference from deployed active-descendant focus).
Updated browser queries to assert new roles, and added explicit linkage/selected
assertions. Build/lint and 94 headed session-switching tests pass; two targeted
semantic assertions also pass. Pin controls remain sibling buttons within groups;
full deployed row/focus structure and Models-settings footer remain open.

### Search-retained model navigation

Arrow navigation from model search now retains input focus and links highlighted
option by aria-activedescendant; Enter selects and Alt+Enter pins that identity.
Filtered-out highlights are omitted. Direct option focus remains supported.
Build/lint and 94 headed model/session tests pass. Two initial full runs exposed
WebKit test synchronization assumptions: reload now waits for current model label;
late-mutation test uses explicit close because disabling focused option can drop
focus, preventing Escape bubbling. No retries configured or assertions skipped.
Search focus/linkage asserted; dedicated Enter/Alt+Enter-from-search checks and
highlight visual styling remain follow-up work.

### Virtual model focus completion

Highlighted model now has visible inset focus outline while search retains DOM
focus. Dedicated Chromium/WebKit test verifies second-option highlight, Alt+Enter
pin/reorder without model mutation or focus loss, then Enter submits exactly the
canonical provider/model_id and closes picker. Both tests and build/lint pass.
This closes the prior search-action/highlight follow-up; full deployed catalogue
styling and Models-settings presentation remain open.

### Catalogue search header styling

Model search now uses deployed catalogue header/label/search-row/search/clear and
summary classes with their reference CSS. Linked label and inline clear icon retain
existing combobox focus semantics. Explicit close control remains an accessibility
convenience; summary honestly distinguishes refreshing and unavailable catalogue.
Build/lint and all 96 headed Chromium/WebKit model/session tests pass, including
viewport captures and search clear/focus behavior. Whole catalogue sizing/rows and
Models-settings footer are not yet fully migrated.

### Catalogue sizing and scroll region

Applied deployed 680px/viewport-limited catalogue width and 70vh/620px maximum
height, with flexible scrolling results bounded to 48vh/430px. Local max-width:100%
keeps it inside composer and non-results controls do not shrink. Eight initial
capture/keyboard cases passed. Full suite produced 92 passes plus four new test
failures from checking a button inside closed details; corrected test opens pin
preferences first. Four desktop/mobile cases then passed, verifying Next model
and revealed Load control stay in viewport. No automatic test retries used.
Expanded settings still local inline details rather than deployed settings page.

### Large catalogue scroll acceptance

Added 60-model fixtures at 1280x844 and 390x844. Four headed Chromium/WebKit cases
verify overflow exists, ArrowUp reaches the last model within the results clipping
rectangle, search retains focus, footer stays in viewport, and filtering removes
stale active-descendant before navigation selects the remaining result. All pass;
no production change. This verifies scrolling beyond the earlier two-model fixture.

### Post-catalogue integrated checkpoint

At 9d40492: 508 backend tests, 18 frontend tests (73 assertions), build/lint,
and all 280 headed Chromium/WebKit tests pass. Browser run used one worker and
completed in 5.3 minutes without retries. This supersedes the 266-test checkpoint.
Catalogue implementation now includes provider groups, display-name search,
validated metadata, linked combobox/listbox semantics, search-retained virtual
focus, pin/select shortcuts, deployed search-header styling and bounded scrolling.
Remaining substantive UI work includes Models-settings presentation, full deployed
row/layout comparison and final model/status/session-picker visual acceptance.
No live speech or third-party ACP/attachment acceptance is implied by this run.

### Models settings modal entry point

Added real modal Models settings view for supported browser/instance pins, reusing
ETag-safe explicit Load/Save. Native dialog provides modality and focus restoration;
keyboard events do not leak to picker. Explicit notice excludes provider credentials
and defaults. Existing inline controls remain for compatibility, not full deployed
settings parity. Initially duplicated hidden status text caused strict-locator
failures; dialog status is now only rendered while open. Subsequent full run had
101 passes and one WebKit option-focus timeout; explicit visibility synchronization
added before focus. Twelve affected modal/pin/shortcut cases then pass; build/lint
passes. Full integrated run after this correction remains due.

### Settings-modal integrated checkpoint

At 78b61ca, clean integrated run: 508 backend tests, 18 frontend tests/73 assertions,
frontend build/lint, and 282 headed Chromium/WebKit tests passed. Browser run used
one worker, completed in 5.3 minutes, and required no retries. This closes the
post-modal full-suite verification item. Modal pin preferences remain a supported
subset rather than complete deployed Models settings (no credential/default
management). Inline duplicate controls, final visual comparison, third-party ACP
messages/attachment consumption and live browser speech acceptance remain open.
