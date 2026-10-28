# Scoped dashboard widgets

Pi and ACP can publish `send_dashboard_widget` to the current active conversation.
The backend persists a `generated_widget` block and exposes it as inert JSON. The
shared UI owns rendering, iframe sandboxing and the `piclawWidget` message bridge.
Browser rendering and bridge acceptance have not been established by these tests.

## Tool and HTTP contract

Pi tool fields: required `html`, optional `title`, `description`, `interactive`.
The bridge supplies `request_id` from the stable tool-call ID. ACP's MCP tool
accepts the same fields plus optional `request_id`; callers should reuse it when
retrying an uncertain delivery. An omitted MCP ID generates a fresh UUID and
cannot deduplicate separate tool calls automatically.

POST `/internal/agent-tools/dashboard-widget` requires loopback access, no Origin,
an attachment bearer capability and a matching active Pi/ACP turn. The payload
accepts only the tool fields and required `request_id`. HTML is nonempty and
limited to 512 KiB, title to 200 characters, description to 2,000 characters, and
new widgets to 100 per turn. Invalid input is 400; absent/stale ownership is 403.
Success is 201:

```json
{"widget_id":"32-character-hex-id","message_id":123,"session_id":"default","url":"/api/sessions/default/widgets/32-character-hex-id"}
```

A stable ID deduplicates same-payload retries within the captured turn. Reusing an
ID with different content fails. Receipts do not persist across server restarts;
callers must not replay uncertain completed work automatically.

The durable intermediate assistant row contains the session/thread/turn identity
and one block:

```json
{"type":"generated_widget","widget_id":"...","title":"Dashboard","description":"","artifact":{"kind":"html","html":"<p>...</p>"},"source":"timeline","status":"final","capabilities":["interactive"],"auto_open":true,"origin_chat_jid":"gi:default"}
```

GET `/api/sessions/{s}/widgets/{id}` returns that block as JSON with
`Cache-Control: no-store` and `X-Content-Type-Options: nosniff`. A foreign session,
invalid ID, deleted message or missing artifact returns 404. The durable message
is the artifact source; reconnect/restart does not require an in-memory cache.
Schema 11 indexes session and the first block's widget ID; publication always
writes exactly one widget block. Lookup does not scan historical HTML.
No route serves supplied HTML as a same-origin executable document.

The application remains a trusted single-user loopback preview. The session path
is data scoping, not multi-user authentication. The outer application middleware
still controls browser access; the internal publication route additionally checks
the agent capability. The artifact route does not grant tool execution.

## Cancellation and storage

Publication serialises per-turn receipts and database admission. Parent-session
ownership is checked inside the write lock. Artifact lookup uses the same lock
and cannot observe an uncommitted insert. If ownership disappears while commit is
pending, the committed insert is removed before releasing the lock or emitting
an event/receipt. Task cancellation settles that commit and performs the same
cleanup. Successful admitted messages survive later cancellation like other
already-published assistant messages.

An initial review identified the commit-boundary and shared-connection read
races. Forced tests now suspend commit, attempt concurrent lookup, cancel the
owner or publication task, and verify 404, zero assistant rows, no receipt and no
broadcast. Storage failures propagate; an uncertain failed request is not authority
to replay another turn.

## Verification

Focused storage, widget, race, MCP and attachment tests: 18 passed in 1.41s.
The final combined configuration/HTTP/workspace/agent/shell/PTY/widget gate
passed 382 tests in 26.23s. Four Bun adapter tests cover shell,
widget and Plan bridges, including omission of absent fields, stable request ID,
nonzero shell status and filtering secret-bearing preparation data.

Not yet verified: complete consumer rendering, sandbox/postMessage behaviour,
widget Submit/close/refresh end to end, live-provider tool selection, artifact
asset/module loading, restart after an ambiguous acknowledgement, concurrent/slow-client release workloads, or FFI custom-widget registration.
[Widget lookup profiling](evidence/widget-vnc-profiling-20261028.md) identified
historical JSON scanning; the index reduced CPU by 95.4% and allocated bytes by
97.8% in the documented 120-artifact workload.
The candidate shared UI advertises a different frontend revision from the current
consumer pin; no frontend files, selectors, profile claims or skips change here.
