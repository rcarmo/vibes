# API

## Public

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/sse/stream` | SSE endpoint for live updates |
| GET | `/media/{id}` | Serve media files |
| GET | `/media/{id}/thumbnail` | Serve thumbnails |
| GET | `/timeline` | Get timeline posts |
| GET | `/thread/{thread_id}` | Get thread |

## Posts

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/post` | Create new post |
| POST | `/reply` | Reply to thread |
| POST | `/media/upload` | Upload media |

## Agents

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/agents` | List agents |
| POST | `/agent/{id}/message` | Send message to agent |
