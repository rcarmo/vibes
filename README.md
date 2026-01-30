# Vibes

A single-user, mobile-friendly SPA for Twitter-like interactions with coding agents via the ACP protocol.

## Features

- Post text, links, images, and files
- Threaded conversations with ACP agents
- Rich media previews (downscaled and stored in database)
- Live updates via Server-Sent Events (SSE)
- Responsive design for mobile, tablet, and desktop
- Dark/light mode toggle

## Installation

```bash
pip install git+https://github.com/rcarmo/vibes.git
```

Or for development:

```bash
git clone https://github.com/rcarmo/vibes.git
cd vibes
pip install -e ".[dev]"
```

## Usage

```bash
# Run the server
vibes

# Or with custom options
VIBES_HOST=127.0.0.1 VIBES_PORT=3000 vibes
```

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `VIBES_HOST` | `0.0.0.0` | Server bind address |
| `VIBES_PORT` | `8080` | Server port |
| `VIBES_DB_PATH` | `data/app.db` | SQLite database path |
| `VIBES_DEBUG` | `false` | Enable debug mode |
| `VIBES_CONFIG_PATH` | `config/endpoints.json` | Custom endpoints config |

## API Endpoints

### Public

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/sse/stream` | SSE endpoint for live updates |
| GET | `/media/{id}` | Serve media files |
| GET | `/media/{id}/thumbnail` | Serve thumbnails |
| GET | `/timeline` | Get timeline posts |
| GET | `/thread/{thread_id}` | Get thread |

### Posts

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/post` | Create new post |
| POST | `/reply` | Reply to thread |
| POST | `/media/upload` | Upload media |

### Agents

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/agents` | List agents |
| POST | `/agent/{id}/message` | Send message to agent |
| POST | `/agent/{id}/action/{action}` | Trigger agent action |

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run in debug mode
VIBES_DEBUG=true vibes
```

## License

MIT
