# Classic conversation adapters

The Python routes expose persisted, session-scoped history, search and deletion
without changing the legacy `/timeline`, `/search` or `/post` routes.

## History and search

GET `/api/sessions/{s}/messages` supports `view=conversation`, `limit` (1–100)
and either `before` or `after` as a positive persisted row ID. Default history
returns the latest page in chronological order; `after` returns the next page
in chronological order. Responses contain `messages`, `has_more`, `before` and
`after`. Unknown, repeated or conflicting query fields return 400; nonexistent
sessions return 404. Archived sessions remain readable.

GET `/api/sessions/{s}/search` accepts nonempty `q` (at most 4,096 characters),
`limit` (1–100), `offset` (0–10,000), `view=conversation` and `scope=current|root`.
Root scope uses the existing bounded persisted ancestry/family resolver. FTS
syntax errors return 400. Results use the same projection as history and report
`has_more`. No global search is implied by an omitted or unknown scope.

Visible stored user/post/reply, assistant and system records project to stable
string `id`, numeric `display_row_id`, `session_id`, role, content, created time,
`reply_to_id` and a small payload. Tool records and system queue notices are
filtered before pagination. Semantic kind/display fields remain available to
the candidate projector. Attachments are rebuilt from persisted media metadata
only when ownership matches the message session; image/file blocks cannot bypass
this check. At most 32 attachment references per record are projected. Legacy
media lacking an explicit owner is omitted. Canonical media transport is separate.

## Deletion

DELETE `/api/sessions/{s}/messages/{m}?cascade=false|true` uses an immediate
SQLite write transaction for ownership checks, descendant discovery and deletion.
Missing/foreign IDs return 404. A reply ID addresses that reply, never its root.
Descendants require explicit cascade; nested descendants are included. Batches
over 1,000 descendants and inconsistent cross-session trees return 409.

Active turns and durable queued work in the target/ancestor subtree reject
transcript mutation. Deletion retains media and send receipts: those may still
be referenced by receipt results or native consumers. The successful result
contains a deleted count and string IDs. After commit, the server publishes
`interaction_deleted` with IDs, persisted `session_id` and `chat_jid`. Its scoped
transport targets only the owner and legacy unscoped subscribers, even though
the source rows no longer exist. The resolved-session broadcast helper is an
internal API whose callers must verify persisted ownership inside their mutation.

Candidate `0259e9a` subscribes to deletion events but its active app event handler
does not consume `interaction_deleted`. Another tab can stay stale until refresh
or reconnect. The shared frontend was not changed; cross-tab UI deletion is not
accepted by these backend tests.

## Verification

Focused history/deletion/SSE/search tests: 36 passed in 1.05 seconds. The full
Python suite passed 1,031 tests with 13 existing skips in 41.38 seconds using the
pinned optional SDK and unchanged shared assets. New route/tests pass Ruff;
diff checks pass. Tests cover visible pagination, strict queries, family search,
exact reply deletion, explicit cascade, nested descendants, active/queued guards,
foreign/corrupt ownership, media/receipt retention and post-delete SSE isolation.

The actual candidate `0259e9a` conversation projector passed against the real
HTTP routes with a disposable SQLite database: user/assistant roles, stable reply
identity, owned file attachment, search, conflict without cascade and reply-only
deletion. No browser application or model provider was started. Scratch host,
synthetic DB, copied helpers, SDK, asset link and test output are removed after
analysis. Shared UI adoption, canonical media transport, complete consumer/reconnect
acceptance and pre-release CPU/allocation profiling still require work.
