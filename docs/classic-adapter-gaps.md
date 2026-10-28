# Remaining Classic server adapter work

Bounded component probes pass, but the complete shared Classic application is
not integrated. The runtime still pins fixtures `4259e82` and serves `ui/vibes`.
Candidate `0259e9a` includes the revision fix and prior release/retirement/temp
changes; adoption requires a reviewed pin/profile transition, not copying assets
or editing shared frontend files.

## Explicit SSE subscriptions

`/sse/stream?chat_jid=gi:<session-id>` and the compatible `session_id` query now
validate the session and bind each client to it. Conflicting/invalid selectors
return 400; absent sessions return 404. Conversation event ownership is resolved
through persisted thread/message data, and inconsistent claims fail closed.
Reordered queues must have one resolved owner; mixed/ambiguous batches are
withheld. Plan/model notifications validate their persisted session. Workspace,
theme, session-list invalidation and restart notifications are global.

The legacy stream without an explicit selector stays global for the pinned old
UI. This is a compatibility feed inside the trusted single-user application,
not multi-user authorisation. Only explicitly scoped subscriptions gain the new
conversation filtering. Existing queue bounds/lossy policies and workspace
hidden-file filtering are preserved. Encoding common payloads once per broadcast
also avoids serialising identical data for every subscriber.

Focused SSE/workspace/widget/race tests: 86 passed in 2.66s, including actual HTTP
subscription validation, foreign-message rejection, inconsistent claim rejection,
missing owner handling and per-chat delivery. Full-app SSE/bootstrap/reconnect
acceptance and high-rate stream profiling remain open.

## Boot and registry

Add a dedicated server adapter module; retain existing routes. Required boot
paths include truthful `/api/auth/status`, `/api/runtime/config`, `/api/sessions`
and `/api/sessions/{s}`. Session projection maps stored `name` to `title`,
`parent_id` to `parent_session_id`, and persisted running/queued/archive state to
Classic state. Current storage has no durable arbitrary agent scope or archived
at timestamp: constrain the supported single `web` scope or add narrow fields;
do not fabricate branch/agent semantics. Serving the Classic tree requires its
actual static prefixes plus safe SPA fallback, not the current `/static` layout.

## Timeline and real prompt admission

Project persisted interactions to Classic conversation messages with stable IDs,
`display_row_id`, role/content/time and payload. Session-scoped history/search/
delete must reject foreign IDs and implement or explicitly reject pagination
options. Generic legacy `/timeline` and `/post` are not sufficient adapters.

The canonical POST `/api/sessions/{s}/prompt` now enters the existing per-chat
admission path, persists the user message/queue identity and produces a genuine
turn or queue acknowledgement. [The admission contract](canonical-prompt.md)
records durable no-replay receipts and the bounded Plan Submit probe. Map `prompt` to content and intents to current
prompt/queue/steer semantics. Validate media ownership from persisted metadata,
active parent turn against the path session, and target agent against supported
scope. Never switch process-global selection or silently drop a stale target.

A durable send-receipt protocol is required before accepting Submit. Candidate
API code reconciles a lost POST via GET
`/api/sessions/{s}/send-receipt?client_request_id=...`, with no blind POST replay.
Use a session-scoped unique request identity and atomic durable admission/result
state. A receipt inserted independently before dispatch can become a phantom;
one inserted afterward can permit duplicate dispatch. Refactor the shared
admission helper so transaction/ownership/cancellation boundaries define which
state is accepted, pending or uncertain. Interrupted admission must never restart
work automatically. The implemented schema13 pending/confirmed/rejected/uncertain
protocol passes duplicate, reconnect and cancellation-boundary tests; it never
automatically redispatches pending/uncertain work. Full consumer and live-provider
acceptance still require the other boot/control adapters below.

## Controls and media

Activity and cancellation must resolve the exact persisted session/turn owner,
then call existing abort checks. Queue adapters require stable durable IDs and an
atomic `{expected,order}` reorder contract; translating an absolute order into
several directional mutations creates races. Compaction availability must be
truthful: no regular prompt may masquerade as compaction.

Canonical model GET/PATCH needs offered model choices and authoritative readback
from the selected lane. Stale thinking/model changes need the observed revision
or token, not an echoed request. Media upload/read aliases must preserve and
verify conversation ownership; global numeric media IDs are not session grants.
Forking a session cannot simply create an empty child while claiming transcript/
backend-state branching.

Settings keychain/environment, revision-safe workspace/Plan routes, scoped widget
publication and opt-in PTY/VNC transport now have backend implementations and
bounded tests. Browser/RFB/widget bridge, complete app, live-provider, six-project
core acceptance and final profiling still need verification. No route gap is
closed by declaring an unsupported endpoint successful.
