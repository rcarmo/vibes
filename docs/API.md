# API

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
| POST | `/reply` | Reply to thread |
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
| `new_post` | New post created |
| `new_reply` | New reply in thread |
| `agent_response` | Agent posted a response |
| `agent_status` | Agent status update (thinking, tool calls) |
| `agent_draft` | Agent draft text update |
| `agent_request` | Agent permission request |
| `agent_request_timeout` | Permission request timed out |
| `interaction_updated` | Post/reply metadata updated |
| `interaction_deleted` | Post/reply deleted |
