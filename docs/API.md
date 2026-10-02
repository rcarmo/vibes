# API

## Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | HTTP liveness plus selected backend readiness; FFI includes active/failed chat counts |

## Timeline & Posts

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/timeline` | Get timeline posts (paginated) |
| GET | `/thread/{thread_id}` | Get thread by ID |
| GET | `/hashtag/{hashtag}` | Get posts by hashtag |
| GET | `/search?q={query}` | Full-text search posts |
| POST | `/post` | Create new post |
| POST | `/reply` | Reply to thread |
| DELETE | `/post/{post_id}?cascade=true` | Delete post (cascade replies when true) |

## Media

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/media/upload?session_id={id}` | Upload media file into an existing non-archived conversation; defaults to `default` |
| GET | `/media/{id}` | Get media file |
| GET | `/media/{id}/thumbnail` | Get media thumbnail |
| GET | `/media/{id}/info` | Get media metadata |
| POST | `/internal/agent-tools/attach-file` | Local capability-scoped agent attachment delivery; see [agent attachments](AGENT_ATTACHMENTS.md) |

## Workspace

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/workspace/tree` | Get workspace file tree |
| GET | `/workspace/file?path={path}` | Get file content (text preview, base64 for binary) |
| PUT | `/workspace/file` | Update (save) a file |
| DELETE | `/workspace/file?path={path}` | Delete a file |
| POST | `/workspace/create` | Create a new file or directory |
| POST | `/workspace/rename` | Rename a file or directory |
| POST | `/workspace/move` | Move a file or directory |
| GET | `/workspace/raw?path={path}` | Get raw file content (served as-is) |
| GET | `/workspace/download?path={path}` | Download a file or folder (folders as ZIP) |
| POST | `/workspace/attach` | Attach a workspace file to a message |
| POST | `/workspace/upload` | Upload a file to the workspace |
| POST | `/workspace/visibility` | Toggle hidden-files visibility |

## Agents

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/agents` | List available agents |
| GET | `/agents/status` | Get current agent status (busy, idle, queue) |
| GET | `/agent/context` | Get agent context-window usage |
| GET | `/agent/models` | List available models (Pi mode) |
| GET | `/agent/commands` | List available slash commands |
| GET | `/agent/queue` | Get queued follow-up messages |
| GET | `/agent/turn/{turn_id}` | Get turn content preview |
| POST | `/agent/turn/{turn_id}/panel` | Set panel collapse state for a turn |
| POST | `/agent/{id}/message` | Send message to agent |
| POST | `/agent/{id}/action/{action_id}` | Trigger a configured custom action |
| POST | `/agent/queue-remove` | Remove an item from the queue |
| POST | `/agent/queue-steer` | Promote a queued item to steering |
| POST | `/agent/respond` | Respond to agent permission request |
| GET | `/agent/whitelist` | Get permission whitelist |
| POST | `/agent/whitelist` | Add pattern to whitelist |
| DELETE | `/agent/whitelist` | Remove pattern from whitelist |

## FFI conversations and requests

With `VIBES_DEFAULT_AGENT=copilot-ffi`, existing routes use the native SDK without an ACP/Pi fallback. Different chats run concurrently; each chat executes one turn at a time. Include `session_id` on messages and status/queue queries. A follow-up is queued only behind its own chat's turn.

| Method | Endpoint | Description |
|---|---|---|
| GET | `/sessions/{id}/model-state` | Authoritative current model/reasoning, or explicit unavailable/busy state |
| GET | `/sessions/{id}/models` | Bounded display catalogue; no raw provider configuration |
| POST | `/sessions/{id}/model` | Change `model_id`, `provider: copilot` and/or `thinking_level`; unavailable/unconfirmed changes return 409 |
| POST | `/agent/{id}/abort` | Cancel an exact `session_id` + `turn_id`; stale/mismatched ownership returns 409 |

`POST /agent/respond` accepts `request_id`, an offered `outcome`, and optional `answer` when `outcome` is `freeform`. FFI permission outcomes are `allow`/`deny`, with Allow once semantics; questions can offer `choice-N` or `freeform`. Expired, cancelled or already-used requests return 409. Do not infer IDs or issue a second approval after an ambiguous response.

`GET /agents/status?session_id={id}` includes that chat's active turns and pending requests for reconnect recovery. `agent_request_closed` carries the request/chat/turn IDs and reason; it closes that request rather than signalling completion of the whole turn. `agent_draft` snapshots and expanded `agent_draft_delta` messages are separate streams; clients must not append both.

## Session Plan

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/sessions/{id}/plan` | Read the persistent session checklist and revision |
| PUT | `/sessions/{id}/plan` | Save `markdown` with `expected_revision`; stale revisions return 409 |
| POST | `/internal/agent-tools/plan` | Local turn-owned Plan tool; same store and revision checks |

See [shared Plan](PLAN.md) for the sidebar, Pi `vibes_plan`, ACP `plan`, and conflict semantics.

## Avatars

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/avatar/{kind}` | Get user or agent avatar (`kind` = `user` or `agent`) |

## Real-time

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/sse/stream` | SSE stream for live updates |

### SSE Events

| Event | Description |
|-------|-------------|
| `connected` | Connection established |
| `plan_updated` | Shared Plan saved; session ID, Markdown and revision |
| `new_post` | New post created |
| `new_reply` | New reply in thread |
| `agent_response` | Agent posted a response |
| `agent_status` | Agent status update (thinking, tool calls) |
| `agent_draft` | Agent draft text update |
| `agent_request` | Agent permission request |
| `agent_request_timeout` | Legacy permission timeout/turn cancellation |
| `agent_request_closed` | Exact FFI request resolved or expired; does not end the whole turn |
| `interaction_updated` | Post/reply metadata updated |
| `interaction_deleted` | Post/reply deleted |
