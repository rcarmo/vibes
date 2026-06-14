# API

This document describes the current HTTP/SSE/WS surface of the Go implementation.

## Authentication (optional)

If `VIBES_API_TOKEN` is set, sensitive and mutating endpoints require one of:

- `X-API-Token: <token>`
- `Authorization: Bearer <token>`
- `?token=<token>` (fallback)

## Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |

## Timeline & Posts

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/timeline` | Get timeline posts (paginated) |
| GET | `/thread/{thread_id}` | Get thread by ID |
| GET | `/hashtag/{hashtag}` | Get posts by hashtag |
| GET | `/search?q={query}` | Full-text search posts |
| POST | `/post` | Create new post |
| POST | `/thread` | Reply to thread |
| DELETE | `/post/{post_id}?cascade=true` | Delete post (cascade replies when true) |

## Media

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/media/upload` | Upload media file |
| GET | `/media/{id}` | Get media file |
| GET | `/media/{id}/thumbnail` | Get media thumbnail |
| GET | `/media/{id}/info` | Get media metadata |

## Workspace

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/workspace/tree` | Get workspace file tree |
| GET | `/workspace/file?path={path}` | Get file content (text preview, base64 for binary, includes `mtime`) |
| PUT | `/workspace/file` | Update a file (supports optimistic lock via `mtime`) |
| DELETE | `/workspace/file?path={path}` | Delete a file |
| POST | `/workspace/create` | Create a new file or directory |
| POST | `/workspace/rename` | Rename a file or directory |
| POST | `/workspace/move` | Move a file or directory |
| GET | `/workspace/raw?path={path}` | Get raw file content |
| GET | `/workspace/download?path={path}` | Download file/folder (folders as ZIP) |
| POST | `/workspace/upload` | Upload a file to the workspace |
| POST | `/workspace/visibility` | Toggle hidden-files visibility |

### Workspace save conflict detection

`PUT /workspace/file` accepts optional `mtime`:

```json
{ "path": "notes/todo.md", "content": "...", "mtime": 1715112345678 }
```

If server-side mtime no longer matches, API returns `409 Conflict`.
On success, response includes refreshed `mtime`.

## Agents

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/agents` | List available agents plus persisted `user` profile metadata (includes `actions[]`) |
| GET | `/agent/status` | Get current agent status (busy, idle, queue) |
| GET | `/agent/context` | Get agent context-window usage |
| GET | `/agent/models` | List available models (Pi mode) |
| GET | `/agent/commands` | List available slash commands |
| GET | `/agent/queue` | Get queued follow-up messages |
| GET | `/agent/turn/{turn_id}` | Get turn content preview |
| POST | `/agent/turn/{turn_id}/panel` | Set panel collapse state for a turn |
| POST | `/agent/{id}/message` | Send message to agent |
| POST | `/agent/queue-remove` | Remove an item from queue |
| POST | `/agent/queue-steer` | Promote queued item to steering |
| POST | `/agent/respond` | Respond to agent permission request |
| GET | `/agent/whitelist` | Get permission whitelist |
| POST | `/agent/whitelist` | Add whitelist pattern |
| DELETE | `/agent/whitelist` | Remove whitelist pattern |

## Avatars

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/avatar/{kind}` | Get user or agent avatar (`kind` = `user` or `agent`) |

## Terminal & Profiling (optional)

| Method | Endpoint | Description |
|--------|----------|-------------|
| WS | `/terminal/ws` | PTY terminal WebSocket (only when `VIBES_ENABLE_TERMINAL=true`) |
| GET | `/debug/pprof/*` | Go pprof endpoints (only when `VIBES_ENABLE_PPROF=true`) |

## Real-time (SSE)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/sse/stream` | SSE stream for live updates |

### SSE Events

| Event | Description |
|-------|-------------|
| `connected` | Connection established |
| `new_post` | New post created |
| `new_reply` | New reply in thread |
| `agent_response` | Agent posted a response |
| `agent_status` | Agent status update |
| `agent_draft` | Agent draft text update |
| `agent_thought` | Agent thought stream update |
| `agent_plan` | Agent plan update |
| `agent_request` | Agent permission request |
| `agent_request_timeout` | Permission request timed out |
| `interaction_updated` | Post/reply metadata updated |
| `interaction_deleted` | Post/reply deleted |
| `model_changed` | Active model changed |
| `agents_changed` | Agent inventory changed |
| `workspace_update` | Workspace update event |
| `ui_theme` | UI theme/tint update |
| `extension_event` | Extension UI event payload |
