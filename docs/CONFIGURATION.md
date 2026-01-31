# Configuration

Vibes reads configuration from environment variables (and a `.env` file if present).

| Variable | Default | Description |
|----------|---------|-------------|
| `VIBES_HOST` | `0.0.0.0` | Server bind address |
| `VIBES_PORT` | `8080` | Server port |
| `VIBES_DB_PATH` | `data/app.db` | SQLite database path |
| `VIBES_DEBUG` | `false` | Enable debug mode |
| `VIBES_ACP_AGENT` | `vibe-acp` | ACP agent command |
| `VIBES_AGENT_NAME` | `<hostname>` | Agent display name |
